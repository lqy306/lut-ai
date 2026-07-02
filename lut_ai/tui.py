"""
tui.py — Textual TUI for LUT Evaluation and Ranking (ANSI C core)

Three-screen app:
  1. ConfigScreen  — paths, AI toggle, options
  2. ProcessingScreen — progress bar per LUT
  3. ResultsScreen  — rankings table, detail panel, query matching
"""

from __future__ import annotations

import asyncio
import os
import time
from pathlib import Path
from typing import Optional, ClassVar

from PIL import Image

from textual.app import App, ComposeResult
from textual.screen import Screen
from textual.widgets import (
    Header, Footer, Button, Input, Label, Static, DataTable,
    RichLog, ProgressBar, Select, Switch, Collapsible,
    SelectionList, ListView, ListItem, ContentSwitcher,
)
from textual.containers import Container, Horizontal, Vertical, ScrollableContainer
from textual.binding import Binding
from textual.message import Message
from textual import work
from textual.reactive import var
from textual.widgets.data_table import RowDoesNotExist

from rich.text import Text
from .models import AppConfig, EvalResult, RankingResult, ColorStats
from .lut_apply import scan_luts, load_lut, clear_lut_cache
from .query_match import keyword_match
from . import bindings
from . import log


# ═══════════════════════════════════════════════════════════════════════════
#  Custom messages
# ═══════════════════════════════════════════════════════════════════════════

class LutProcessed(Message):
    """Emitted each time a LUT is processed during evaluation."""
    def __init__(self, current: int, total: int, name: str,
                 stats: Optional[ColorStats] = None) -> None:
        super().__init__()
        self.current = current
        self.total   = total
        self.name    = name
        self.stats   = stats

class EvalComplete(Message):
    """Emitted when evaluation finishes (success or error)."""
    def __init__(self, result: RankingResult, error: str = "") -> None:
        super().__init__()
        self.result = result
        self.error  = error


# ═══════════════════════════════════════════════════════════════════════════
#  Screen 1 — Configuration
# ═══════════════════════════════════════════════════════════════════════════

class ConfigScreen(Screen):
    """Screen for configuring evaluation parameters."""

    BINDINGS = [
        Binding("f5",       "start_eval",   "Start"),
        Binding("escape",   "app.quit",     "Quit"),
        Binding("tab",      "complete_path","Complete"),
        Binding("down",     "scroll_down",  "Down",  show=False),
        Binding("up",       "scroll_up",    "Up",    show=False),
        Binding("ctrl+d",   "scroll_down",  "Ctrl+D", show=False),
        Binding("ctrl+u",   "scroll_up",    "Ctrl+U", show=False),
        Binding("pagedown", "page_down",    "PgDn",  show=False),
        Binding("pageup",   "page_up",      "PgUp",  show=False),
    ]

    def compose(self) -> ComposeResult:
        yield Header()
        yield ScrollableContainer(
            Vertical(
                # ── Title ────────────────────────────────────────────
                Static("[bold cyan]LUT AI — LUT Evaluation & Ranking[/bold cyan]\n"
                       "[dim]LUT Color Grading Tool[/dim]",
                       id="screen-title"),

                # ── archinstall-style: menu left, content right ───
                Horizontal(
                    # ── Left: Menu ─────────────────────────────────
                    Vertical(
                        Label("Settings", classes="menu-heading"),
                        ListView(
                            ListItem(Label("Source Image"), id="mi-image"),
                            ListItem(Label("LUT Directory"), id="mi-lut"),
                            ListItem(Label("Options"), id="mi-options"),
                            ListItem(Label("Advanced"), id="mi-advanced"),
                            id="config-menu",
                            initial_index=0,
                        ),
                        classes="menu-column",
                    ),

                    # ── Right: Content panels ─────────────────────
                    ContentSwitcher(
                        # Panel: Source Image
                        ScrollableContainer(
                            Static("[bold]Source Image[/bold]", classes="section-title"),
                            Input(placeholder="Image path (e.g. ./photo.jpg)",
                                  id="image-path", value=self._default_image()),
                            Label("", id="image-info", classes="hint"),
                            ListView(id="image-list"),
                            id="panel-image",
                        ),
                        # Panel: LUT Directory
                        ScrollableContainer(
                            Static("[bold]LUT Directory[/bold]", classes="section-title"),
                            Input(placeholder="LUT directory (e.g. ./luts/)",
                                  id="lut-dir", value=self._default_lut_dir()),
                            Label("", id="lut-count", classes="hint"),
                            SelectionList(id="lut-select", compact=True),
                            Horizontal(
                                Button("Select All", id="lut-select-all"),
                                Button("Deselect All", id="lut-deselect-all"),
                                Label("", id="lut-select-count", classes="hint"),
                                classes="select-buttons",
                            ),
                            id="panel-lut",
                        ),
                        # Panel: Options
                        ScrollableContainer(
                            Static("[bold]Options[/bold]", classes="section-title"),
                            Horizontal(
                                Label("Use AI ranking", classes="toggle-label"),
                                Switch(id="use-ai", value=False),
                                Label("OFF", id="use-ai-label", classes="switch-label"),
                                classes="option-row",
                            ),
                            Horizontal(
                                Label("AI response language", classes="toggle-label"),
                                Input(placeholder="e.g. English, 中文, 日本語, ja...",
                                      id="lang-input", value="English",
                                      classes="option-input-wide"),
                                classes="option-row",
                            ),
                            Horizontal(
                                Label("Max LUTs (0 = all)", classes="toggle-label"),
                                Input(value="50", id="max-luts", classes="option-input"),
                                classes="option-row",
                            ),
                            id="panel-options",
                        ),
                        # Panel: Advanced
                        ScrollableContainer(
                            Static("[bold]Advanced Settings[/bold]", classes="section-title"),
                            Collapsible(
                                Input(placeholder="API Base URL (or LUTAI_BASE_URL)",
                                      id="base-url",
                                      value=os.environ.get("LUTAI_BASE_URL",
                                             "https://api.openai.com/v1")),
                                Input(password=True,
                                      placeholder="API Key (or LUTAI_API_KEY)",
                                      id="api-key",
                                      value=os.environ.get("LUTAI_API_KEY", "")),
                                Horizontal(
                                    Label("Model", classes="toggle-label"),
                                    Input(value=os.environ.get("LUTAI_MODEL", "gpt-4o"),
                                          id="model", classes="option-input"),
                                    classes="option-row",
                                ),
                                Horizontal(
                                    Label("Temperature", classes="toggle-label"),
                                    Input(value="0.3", id="temperature", classes="option-input"),
                                    classes="option-row",
                                ),
                                id="expert-settings", title="Expert Settings",
                                collapsed=True,
                            ),
                            Static("[dim]API URL, key, model etc.[/dim]", classes="hint"),
                            # ── Image compression ─────────────────────
                            Static("[bold]Image Compression[/bold]", classes="section-title"),
                            Horizontal(
                                Label("Enable pixel limit", classes="toggle-label"),
                                Switch(id="compress-pixels", value=False),
                                Label("OFF", id="compress-label", classes="switch-label"),
                                classes="option-row",
                            ),
                            Horizontal(
                                Label("Max pixels (w×h)", classes="toggle-label"),
                                Input(value="200000", id="max-pixels", classes="option-input"),
                                classes="option-row",
                            ),
                            Static("[dim]When enabled, images are resized to fit within "
                                   "the total pixel limit before processing.[/dim]",
                                   classes="hint"),
                            # ── Unprocessed reference ─────────────────
                            Static("[bold]Reference[/bold]", classes="section-title"),
                            Horizontal(
                                Label("Include unprocessed ref", classes="toggle-label"),
                                Switch(id="include-original", value=True),
                                Label("ON", id="orig-label", classes="switch-label"),
                                classes="option-row",
                            ),
                            Static("[dim]Adds the original unedited image as a baseline "
                                   "in the ranking.[/dim]", classes="hint"),
                            id="panel-advanced",
                        ),
                        id="config-panels",
                    ),
                    id="config-columns",
                ),

                # ── Buttons (full width, below both columns) ────
                Horizontal(
                    Button("Start (F5)", variant="primary", id="start-btn"),
                    Button("Quit", variant="error", id="quit-btn"),
                    classes="button-row",
                ),
            ),
            id="config-scroll",
        )
        yield Footer()

    # ── Defaults ─────────────────────────────────────────────────────

    @staticmethod
    def _default_image() -> str:
        import glob
        # Look for any image file in the current directory
        for pattern in ["./*.jpg", "./*.jpeg", "./*.png", "./*.bmp",
                        "./*.JPG", "./*.JPEG", "./*.PNG"]:
            matches = sorted(glob.glob(pattern))
            if matches:
                return matches[0]
        return ""

    @staticmethod
    def _default_lut_dir() -> str:
        # Common LUT directory names in current directory
        for d in ["./luts", "./Luts", "./lut", "./LUT",
                  "./luts/Luts", "./luts/tmp_gmic/luts/colorslide"]:
            if os.path.isdir(d):
                return d
        return ""

    # ── Reactive updates ────────────────────────────────────────────

    @staticmethod
    def _resolve_path(path: str) -> str:
        """Normalize a user-entered path.

        Strips whitespace, expands ~, and resolves to absolute.
        """
        path = path.strip()
        if not path:
            return ""
        path = os.path.expanduser(path)
        path = os.path.abspath(path)
        return path

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "image-path":
            self._update_image_info(event.value)
        elif event.input.id == "lut-dir":
            self._update_lut_count(event.value)

    def on_mount(self) -> None:
        self._update_image_info(self._default_image())
        self._update_lut_count(self._default_lut_dir())
        self._update_switch_label()
        self._update_compress_label()
        self._update_orig_label()

    # ── Menu selection ────────────────────────────────────────────

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Handle selection from any ListView — menu or image list."""
        if event.list_view.id == "config-menu":
            # Switch right panel when menu item is selected
            panel_map = {
                "mi-image":    "panel-image",
                "mi-lut":      "panel-lut",
                "mi-options":  "panel-options",
                "mi-advanced": "panel-advanced",
            }
            list_id = event.item.id if event.item else None
            if list_id and list_id in panel_map:
                sw = self.query_one("#config-panels", ContentSwitcher)
                sw.current = panel_map[list_id]
        elif event.list_view.id == "image-list" and event.item:
            # Update image path when an image is selected
            label = event.item.children[0]
            fname = label.render() if hasattr(label, 'render') else str(label)
            input_widget = self.query_one("#image-path", Input)
            img_dir = os.path.dirname(input_widget.value)
            if not img_dir or img_dir == ".":
                img_dir = os.getcwd()
            input_widget.value = os.path.join(img_dir, str(fname).strip())
            self._update_image_info(input_widget.value)

    def _update_switch_label(self) -> None:
        """Update ON/OFF label next to the AI switch."""
        sw = self.query_one("#use-ai", Switch)
        lbl = self.query_one("#use-ai-label", Label)
        lbl.update("ON" if sw.value else "OFF")

    def on_switch_changed(self, event: Switch.Changed) -> None:
        if event.switch.id == "use-ai":
            self._update_switch_label()
        elif event.switch.id == "compress-pixels":
            self._update_compress_label()
        elif event.switch.id == "include-original":
            self._update_orig_label()

    def _update_compress_label(self) -> None:
        sw = self.query_one("#compress-pixels", Switch)
        lbl = self.query_one("#compress-label", Label)
        lbl.update("ON" if sw.value else "OFF")

    def _update_orig_label(self) -> None:
        sw = self.query_one("#include-original", Switch)
        lbl = self.query_one("#orig-label", Label)
        lbl.update("ON" if sw.value else "OFF")

    def _update_image_info(self, path: str) -> None:
        info = self.query_one("#image-info", Label)
        resolved = self._resolve_path(path)
        if not resolved:
            info.update("[red]File not found[/red]")
            self._populate_image_list("")
            return
        if os.path.isdir(resolved):
            info.update(f"[blue]Directory: {resolved}[/blue]")
            self._populate_image_list(resolved)
            return
        if not os.path.isfile(resolved):
            info.update("[red]File not found[/red]")
            self._populate_image_list(os.path.dirname(resolved))
            return
        try:
            img = Image.open(resolved)
            img.load()
            info.update(
                f"[green]OK[/green]  "
                f"{img.width} × {img.height}  ·  "
                f"{Path(resolved).suffix.upper()}"
            )
            self._populate_image_list(os.path.dirname(resolved),
                                      os.path.basename(resolved))
        except Exception as e:
            info.update(f"[red]Cannot open: {e}[/red]")

    def _populate_image_list(self, directory: str,
                             highlight: str = "") -> None:
        """Fill the image list with files from a directory."""
        lst = self.query_one("#image-list", ListView)
        lst.clear()
        if not directory or not os.path.isdir(directory):
            return
        exts = {'.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.webp'}
        images = sorted(
            f for f in os.listdir(directory)
            if os.path.splitext(f)[1].lower() in exts
        )
        if not images:
            return
        for fname in images:
            item = ListItem(Label(fname))
            lst.append(item)
            if fname == highlight:
                lst.index = len(lst) - 1
                lst.index = len(lst) - 1

    def _update_lut_count(self, path: str) -> None:
        label = self.query_one("#lut-count", Label)
        resolved = self._resolve_path(path)
        if not resolved or not os.path.isdir(resolved):
            label.update("[red]Directory not found[/red]")
            return
        luts = scan_luts(resolved)
        label.update(f"[green]{len(luts)}[/green] .cube files found")
        # Populate LUT selection list
        self._populate_lut_select(luts)

    def _populate_lut_select(self, lut_names: list[str]) -> None:
        """Fill the LUT selection list."""
        sel = self.query_one("#lut-select", SelectionList)
        sel.clear_options()
        for name in lut_names:
            sel.add_option((name, name, True))
        self._update_lut_select_count()

    def _update_lut_select_count(self) -> None:
        sel = self.query_one("#lut-select", SelectionList)
        total = len(list(sel.options))
        n = len(sel.selected)
        lbl = self.query_one("#lut-select-count", Label)
        if total:
            lbl.update(f"Selected {n}/{total}")
        else:
            lbl.update("")

    # ── Button handlers ─────────────────────────────────────────────

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "start-btn":
            self.action_start_eval()
        elif event.button.id == "quit-btn":
            self.app.exit()
        elif event.button.id == "lut-select-all":
            self._lut_select_all()
        elif event.button.id == "lut-deselect-all":
            self._lut_deselect_all()

    def _lut_select_all(self) -> None:
        self.query_one("#lut-select", SelectionList).select_all()
        self._update_lut_select_count()

    def _lut_deselect_all(self) -> None:
        self.query_one("#lut-select", SelectionList).deselect_all()
        self._update_lut_select_count()

    # ── Selection change handlers ───────────────────────────────────

    def on_selection_list_selection_changed(self,
            event: SelectionList.SelectionChanged) -> None:
        if event.selection_list.id == "lut-select":
            self._update_lut_select_count()

    # ── Scroll actions ──────────────────────────────────────────────

    def action_scroll_down(self) -> None:
        self.query_one("#config-scroll", ScrollableContainer).scroll_down(1)

    def action_scroll_up(self) -> None:
        self.query_one("#config-scroll", ScrollableContainer).scroll_up(1)

    def action_page_down(self) -> None:
        self.query_one("#config-scroll", ScrollableContainer).scroll_page_down()

    def action_page_up(self) -> None:
        self.query_one("#config-scroll", ScrollableContainer).scroll_page_up()

    def action_complete_path(self) -> None:
        """Tab-complete the current path input."""
        focused = self.focused
        if not isinstance(focused, Input):
            return
        input_id = focused.id
        if input_id not in ("image-path", "lut-dir"):
            return

        raw = focused.value.strip()
        if not raw:
            return

        # Expand ~ and resolve relative to cwd
        expanded = os.path.expanduser(raw)
        if not os.path.isabs(expanded):
            expanded = os.path.join(os.getcwd(), expanded)

        dirname = os.path.dirname(expanded)
        prefix  = os.path.basename(expanded)

        if not dirname or not os.path.isdir(dirname):
            return

        # Collect matching entries
        matches = sorted(
            e for e in os.listdir(dirname)
            if e.lower().startswith(prefix.lower())
        )
        if not matches:
            return

        # Complete to longest common prefix
        common = matches[0]
        for m in matches[1:]:
            i = 0
            while i < len(common) and i < len(m) and common[i].lower() == m[i].lower():
                i += 1
            common = common[:i]

        new_val = os.path.join(dirname if dirname != "." else "", common)
        # If only one match and it's a directory, append /
        if len(matches) == 1 and os.path.isdir(new_val):
            new_val += "/"

        focused.value = new_val
        focused.cursor_position = len(new_val)

        # Trigger re-listing
        if input_id == "image-path":
            self._update_image_info(new_val)
        else:
            self._update_lut_count(new_val)

    def action_start_eval(self) -> None:
        """Collect config and switch to processing screen."""
        cfg = AppConfig()

        cfg.image_path = self._resolve_path(
            self.query_one("#image-path", Input).value)
        cfg.lut_dirs   = [self._resolve_path(
            self.query_one("#lut-dir", Input).value)]

        try:
            cfg.max_luts = int(self.query_one("#max-luts", Input).value)
        except (ValueError, TypeError):
            cfg.max_luts = 0

        use_ai = self.query_one("#use-ai", Switch).value
        cfg.use_ai = use_ai

        if use_ai:
            cfg.base_url    = self.query_one("#base-url", Input).value.strip()
            cfg.api_key     = self.query_one("#api-key", Input).value.strip()
            cfg.model       = self.query_one("#model", Input).value.strip()
            try:
                cfg.temperature = float(
                    self.query_one("#temperature", Input).value)
            except (ValueError, TypeError):
                cfg.temperature = 0.3

        # Collect selected items
        lut_sel = self.query_one("#lut-select", SelectionList)
        cfg.selected_luts = list(lut_sel.selected)

        cfg.language = self.query_one("#lang-input", Input).value.strip()
        if not cfg.language:
            cfg.language = "English"

        cfg.stream = True
        cfg.compress_pixels = self.query_one("#compress-pixels", Switch).value
        try:
            cfg.max_pixels = int(self.query_one("#max-pixels", Input).value)
        except (ValueError, TypeError):
            cfg.max_pixels = 200000
        cfg.include_original = self.query_one("#include-original", Switch).value

        # Validate
        errors = []
        if not cfg.image_path or not os.path.isfile(cfg.image_path):
            errors.append("Source image not found")
        if not cfg.lut_dirs[0] or not os.path.isdir(cfg.lut_dirs[0]):
            errors.append("LUT directory not found")
        elif not cfg.selected_luts:
            errors.append("No LUT selected")
        if cfg.use_ai and not cfg.api_key and not os.environ.get("OPENAI_API_KEY") \
                and not os.environ.get("LUTAI_API_KEY"):
            errors.append("API key required for AI ranking")

        if errors:
            self.app.notify("\n".join(errors), severity="error", timeout=8)
            return

        self.app.config = cfg
        self.app.push_screen("processing")


# ═══════════════════════════════════════════════════════════════════════════
#  Screen 2 — Processing
# ═══════════════════════════════════════════════════════════════════════════

class ProcessingScreen(Screen):
    """Screen showing LUT processing progress."""

    BINDINGS = [
        Binding("escape",   "cancel",    "Cancel"),
        Binding("down",     "scroll_down",  "Down",    show=False),
        Binding("up",       "scroll_up",    "Up",      show=False),
        Binding("ctrl+d",   "scroll_down",  "Ctrl+D",  show=False),
        Binding("ctrl+u",   "scroll_up",    "Ctrl+U",  show=False),
        Binding("pagedown", "page_down",    "PgDn",    show=False),
        Binding("pageup",   "page_up",      "PgUp",    show=False),
    ]

    def compose(self) -> ComposeResult:
        yield Header()
        yield Vertical(
            Static("[bold cyan]Processing LUTs...[/bold cyan]",
                   id="proc-title"),
            ProgressBar(total=100, id="proc-bar", show_eta=True),
            Static("Initializing...", id="proc-current"),
            RichLog(id="proc-log", highlight=True, max_lines=500, wrap=True),
            Button("Cancel", variant="error", id="cancel-btn"),
            id="proc-container",
        )
        yield Footer()

    def on_mount(self) -> None:
        self.run_evaluation()

    @work(exclusive=True, thread=True)
    async def run_evaluation(self) -> None:
        """Run the evaluation pipeline in a worker thread."""
        log.info("=== Evaluation started ===")
        app: LutEvalApp = self.app
        cfg = app.config

        try:
            # ── Use selected LUTs or scan all ─────────────────────
            if cfg.selected_luts:
                luts_all = cfg.selected_luts
            else:
                luts_all = scan_luts(cfg.lut_dirs[0])
            if cfg.max_luts > 0:
                luts_all = luts_all[:cfg.max_luts]

            if not luts_all:
                self.post_message(EvalComplete(RankingResult(),
                                  "No LUTs selected"))
                return

            log.info(f"Processing {len(luts_all)} LUTs, AI={cfg.use_ai}, "
                     f"model={cfg.model}")

            app.total_luts = len(luts_all)
            app.processed  = 0

            self.app.call_from_thread(
                self._update_progress, 0, len(luts_all), "Scanning..."
            )

            # ── Resolve actual image from selection ────────────────
            img_dir = os.path.dirname(cfg.image_path)
            if cfg.selected_images:
                img_file = cfg.selected_images[0]
                img_path = os.path.join(img_dir, img_file)
            else:
                img_path = cfg.image_path

            # ── Load source image ─────────────────────────────────
            try:
                source = Image.open(img_path).convert("RGB")
            except Exception as e:
                log.error(f"Cannot open image: {e}")
                self.post_message(EvalComplete(RankingResult(),
                                  f"Cannot open image: {e}"))
                return

            # ── Apply pixel limit if enabled ───────────────────────
            if cfg.compress_pixels and cfg.max_pixels > 0:
                w, h = source.size
                total = w * h
                if total > cfg.max_pixels:
                    ratio = (cfg.max_pixels / total) ** 0.5
                    new_w = int(w * ratio)
                    new_h = int(h * ratio)
                    source = source.resize((new_w, new_h), Image.LANCZOS)
                    log.info(f"Compressed {w}x{h} → {new_w}x{new_h} "
                             f"({total}→{new_w*new_h} px)")
                    self.app.call_from_thread(
                        self._log,
                        f"[dim]Image compressed: {w}x{h} → {new_w}x{new_h}[/dim]"
                    )
            else:
                source.thumbnail((256, 256), Image.LANCZOS)

            log.info(f"Image loaded: {img_path} ({source.size})")

            # ── Include unprocessed reference if enabled ────────────
            if cfg.include_original:
                raw_orig = source.tobytes()
                w_orig, h_orig = source.size
                try:
                    stats_orig = bindings.extract_stats(raw_orig, w_orig, h_orig)
                    stats_list: list[tuple[str, ColorStats]] = [
                        ("(original) no LUT", stats_orig)
                    ]
                    log.info("Added unprocessed reference")
                    self.app.call_from_thread(
                        self._log, "[dim]✓ (original) no LUT[/dim]"
                    )
                except Exception as e:
                    log.error(f"Original stats failed: {e}")
                    stats_list = []
            else:
                stats_list: list[tuple[str, ColorStats]] = []

            # ── Process each LUT ──────────────────────────────────
            for idx, name in enumerate(luts_all):
                if self._is_cancelled:
                    return

                self.app.call_from_thread(
                    self._update_progress,
                    idx, len(luts_all), name,
                )

                try:
                    lut = load_lut(name, cfg.lut_dirs[0])
                    processed = lut.apply_image(source)
                    w, h = processed.size
                    raw = processed.tobytes()
                    stats = bindings.extract_stats(raw, w, h)
                    stats_list.append((name, stats))
                except Exception as e:
                    self.app.call_from_thread(
                        self._log, f"[red]✗[/red] {name}: {e}"
                    )
                    continue

                self.app.call_from_thread(self._log, f"[green]✓[/green] {name}")
                self.post_message(
                    LutProcessed(idx + 1, len(luts_all), name)
                )

            if not stats_list:
                self.post_message(
                    EvalComplete(RankingResult(), "No LUTs to process")
                )
                return

            # ── Evaluate ──────────────────────────────────────────
            self.app.call_from_thread(
                self._update_progress,
                len(luts_all), len(luts_all),
                "Evaluating..."
            )

            if cfg.use_ai:
                from .ai_interface import call_ai_ranking
                try:
                    # Ensure API key is resolved (env vars might not be in thread)
                    import os as _os
                    if not cfg.api_key:
                        for var in ("LUTAI_API_KEY", "OPENAI_API_KEY"):
                            cfg.api_key = _os.environ.get(var, "")
                            if cfg.api_key:
                                break
                    if not cfg.api_key:
                        raise RuntimeError("No API key found. "
                            "Set LUTAI_API_KEY or enter in Expert Settings.")

                    stats_texts = [
                        (name, bindings.stats_serialize(stats))
                        for name, stats in stats_list
                    ]
                    log.info(f"Calling AI ranking: {cfg.model} @ {cfg.base_url}, "
                             f"stats={len(stats_texts)} LUTs")
                    log.info(f"API key: {cfg.api_key[:8]}...{cfg.api_key[-4:]}")
                    # Use non-streaming in thread for reliability
                    result = call_ai_ranking(
                        stats_texts,
                        base_url=cfg.base_url,
                        api_key=cfg.api_key,
                        model=cfg.model,
                        temperature=cfg.temperature,
                        language=cfg.language,
                        stream=False,
                    )
                    log.info(f"AI ranking OK: best={result.best_lut}, "
                             f"count={len(result.rankings)}")
                    self.app.call_from_thread(
                        self._log,
                        f"[green]✓ AI ranking complete! Best: {result.best_lut}[/green]"
                    )
                except Exception as e:
                    log.error(f"AI ranking failed: {e}")
                    self.app.call_from_thread(
                        self._log,
                        f"[red]✗ AI Error: {e}[/red]"
                    )
                    cfg.use_ai = False
                    self.app.call_from_thread(
                        self._log,
                        "[yellow]Falling back to local evaluation.[/yellow]"
                    )

            if not cfg.use_ai:
                log.info("Running local evaluation")
                rankings = []
                for name, stats in stats_list:
                    score, tags_str, desc = bindings.local_evaluate(stats)
                    tags = [t.strip() for t in tags_str.split(",") if t.strip()]
                    rankings.append(EvalResult(
                        name=name, score=score, style_tags=tags,
                        description=desc, stats=stats, eval_source="local",
                    ))
                rankings.sort(key=lambda r: r.score, reverse=True)
                for i, r in enumerate(rankings):
                    r.rank = i + 1
                result = RankingResult(
                    rankings=rankings,
                    best_lut=rankings[0].name if rankings else "",
                    best_reason=rankings[0].description if rankings else "",
                )
                log.info(f"Local eval done: best={result.best_lut}")

            log.info("=== Evaluation complete, sending results ===")
            self.post_message(EvalComplete(result))

        except Exception as e:
            log.error(f"Fatal error: {e}")
            self.post_message(EvalComplete(RankingResult(), str(e)))

    _is_cancelled: bool = False

    def action_cancel(self) -> None:
        self._is_cancelled = True
        self._log("[red]Cancelled[/red]")
        self.app.pop_screen()

    # ── Scroll actions ──────────────────────────────────────────

    def action_scroll_down(self) -> None:
        self.query_one("#proc-log", RichLog).scroll_down(1)

    def action_scroll_up(self) -> None:
        self.query_one("#proc-log", RichLog).scroll_up(1)

    def action_page_down(self) -> None:
        self.query_one("#proc-log", RichLog).scroll_page_down()

    def action_page_up(self) -> None:
        self.query_one("#proc-log", RichLog).scroll_page_up()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cancel-btn":
            self.action_cancel()

    # ── UI update helpers ──────────────────────────────────────────

    def _update_progress(self, current: int, total: int,
                         current_name: str) -> None:
        bar = self.query_one("#proc-bar", ProgressBar)
        bar.total = total
        bar.progress = current
        label = self.query_one("#proc-current", Static)
        if current == total:
            label.update(f"[bold green]Done![/bold green]   ( {total} LUTs)")
        else:
            label.update(f"[{current}/{total}]  {current_name}")

    def _log(self, msg: str) -> None:
        log = self.query_one("#proc-log", RichLog)
        log.write(Text.from_markup(msg))

    # ── Handle messages from worker ────────────────────────────────

    def on_lut_processed(self, msg: LutProcessed) -> None:
        app: LutEvalApp = self.app
        app.processed = msg.current

    def on_eval_complete(self, msg: EvalComplete) -> None:
        try:
            if msg.error:
                self._log(f"[red]ERROR: {msg.error}[/red]")
                self.app.notify(msg.error, severity="error", timeout=10)
                return

            app: LutEvalApp = self.app
            app.result = msg.result
            n = len(msg.result.rankings)
            self._log(f"\n[bold green]Evaluation complete![/bold green] "
                      f"({n} LUTs ranked)")
            if n > 0:
                self._log(f"Best LUT: {msg.result.best_lut}")
            else:
                self._log("[red]No results returned![/red]")
                return

            # Transition to results screen
            self.app.push_screen("results")
        except Exception as e:
            log.error(f"on_eval_complete crashed: {e}")
            self._log(f"[red]FATAL: {e}[/red]")


# ═══════════════════════════════════════════════════════════════════════════
#  Screen 3 — Results
# ═══════════════════════════════════════════════════════════════════════════

class ResultsScreen(Screen):
    """Screen showing rankings, details, and query matching."""

    BINDINGS = [
        Binding("f5",       "rerun",        "Re-run"),
        Binding("escape",   "back",         "Back"),
        Binding("slash",    "focus_query",  "Search"),
        Binding("down",     "scroll_down",  "Down",    show=False),
        Binding("up",       "scroll_up",    "Up",      show=False),
        Binding("ctrl+d",   "scroll_down",  "Ctrl+D",  show=False),
        Binding("ctrl+u",   "scroll_up",    "Ctrl+U",  show=False),
        Binding("pagedown", "page_down",    "PgDn",    show=False),
        Binding("pageup",   "page_up",      "PgUp",    show=False),
    ]

    def compose(self) -> ComposeResult:
        yield Header()
        yield Horizontal(
            # ── Left: Rankings table ───────────────────────────────
            Vertical(
                Static("[bold]Rankings[/bold]", classes="section-title"),
                DataTable(id="rankings-table", cursor_type="row"),
                id="rankings-panel",
                classes="panel left-panel",
            ),
            # ── Right: detail + query ──────────────────────────────
            Vertical(
                # Best LUT panel
                Static(id="best-panel", classes="result-box"),
                # Detail panel
                Static("[bold]LUT Details[/bold]", classes="section-title"),
                Static("Select a LUT from the table", id="detail-panel",
                       classes="result-box"),
                # Ask AI about LUTs
                Static("[bold]Ask AI[/bold]", classes="section-title"),
                Horizontal(
                    Input(placeholder='e.g. "which one feels most cinematic?"', id="query-input"),
                    Button("Ask", variant="primary", id="query-btn"),
                    classes="query-row",
                ),
                RichLog(id="query-response", highlight=True, max_lines=200, wrap=True),
                id="detail-column",
                classes="panel right-panel",
            ),
            id="results-layout",
        )
        yield Footer()

    def on_mount(self) -> None:
        app: LutEvalApp = self.app
        self._populate_rankings(app.result)

    # ── Rankings table ─────────────────────────────────────────────

    def _populate_rankings(self, result: RankingResult) -> None:
        table = self.query_one("#rankings-table", DataTable)
        table.clear()

        # Column widths auto-computed
        table.add_column("Rankings", width=6)
        table.add_column("LUT", width=28)
        table.add_column("Score", width=6)
        table.add_column("Tags", width=22)
        table.add_column("Description", width=50)

        for r in result.rankings:
            tags_str = ", ".join(r.style_tags[:3])
            table.add_row(
                f"#{r.rank}",
                r.name,
                f"{r.score:.0f}",
                tags_str,
                r.description[:48],
            )

        # Best LUT panel — show eval source prominently
        if result.rankings:
            best = result.rankings[0]
            tags_str = ", ".join(best.style_tags)
            source = best.eval_source
            source_badge = "[green]AI[/green]" if source == "ai" else "[yellow]Local[/yellow]"
            best_panel = self.query_one("#best-panel", Static)
            best_panel.update(
                "[bold cyan]Best LUT[/bold cyan]\n"
                f"[bold]{best.name}[/bold]\n"
                f"[yellow]Score: {best.score:.0f}/100[/yellow]\n"
                f"[green]{tags_str}[/green]\n"
                f"[dim]{best.description}[/dim]\n"
                f"[dim]Eval: {source_badge}[/dim]"
            )

        # Select first row
        if table.row_count > 0:
            table.move_cursor(row=0)
            self._show_detail(0)

    # ── Detail display ─────────────────────────────────────────────

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        try:
            row_key = event.cursor_row
            if row_key is not None:
                self._show_detail(row_key)
        except RowDoesNotExist:
            pass

    def _show_detail(self, row_index: int) -> None:
        app: LutEvalApp = self.app
        if row_index >= len(app.result.rankings):
            return
        r = app.result.rankings[row_index]
        detail = self.query_one("#detail-panel", Static)

        text = f"[bold]{r.name}[/bold]  (#{r.rank})  "
        text += f"[yellow]Score: {r.score:.0f}/100[/yellow]\n"

        if r.style_tags:
            text += f"\nTags: [green]{', '.join(r.style_tags)}[/green]\n"

        text += f"\n[r]{r.description}[/r]\n"

        if r.analysis:
            text += f"\nAnalysis:\n{r.analysis}\n"

        if r.stats:
            text += "\n[dim]── Statistics ──[/dim]\n"
            s = r.stats
            text += (f"RGB: ({s.avg_r:.0f}, {s.avg_g:.0f}, {s.avg_b:.0f})  |  "
                     f"HSV: ({s.avg_h:.0f}°, {s.avg_s:.0f}%, {s.avg_v:.0f}%)\n")
            text += (f"Contrast: {s.contrast:.1f}  |  "
                     f"Warm bias: {s.warm_bias:+.1f}\n")

        detail.update(text)

    # ── Query matching ─────────────────────────────────────────────

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "query-btn":
            self._run_query()
        elif event.button.id == "back-btn":
            self.action_back()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "query-input":
            self._run_query()

    def action_focus_query(self) -> None:
        self.query_one("#query-input", Input).focus()

    def _run_query(self) -> None:
        query = self.query_one("#query-input", Input).value.strip()
        if not query:
            return

        app: LutEvalApp = self.app
        response = self.query_one("#query-response", RichLog)
        response.write(Text.from_markup(f"\n[dim]Q: {query}[/dim]\n"))

        # Try AI first if we have API key
        cfg = app.config
        has_ai = bool(cfg.api_key or os.environ.get("LUTAI_API_KEY")
                      or os.environ.get("OPENAI_API_KEY"))

        if has_ai:
            try:
                from .ai_interface import call_ai_question
                answer = call_ai_question(
                    app.result.rankings,
                    query,
                    base_url=cfg.base_url,
                    api_key=cfg.api_key,
                    model=cfg.model,
                    language=cfg.language,
                )
                response.write(Text.from_markup(answer))
                return
            except Exception as e:
                response.write(
                    Text.from_markup(f"[yellow]AI failed, using keywords: {e}[/yellow]\n\n"))

        # Fallback: keyword matching
        matches = keyword_match(app.result.rankings, query)
        if not matches:
            response.write(Text.from_markup("[red]No matches found.[/red]"))
            return

        response.write("[bold]Top matches:[/bold]\n")
        for r, ms, reason in matches:
            response.write(
                f"  [cyan]{r.name}[/cyan] "
                f"({ms:.0f}%)  score={r.score:.0f}\n"
                f"    {reason}\n")

    # ── Navigation ─────────────────────────────────────────────────

    def action_back(self) -> None:
        """Pop back to config (skip processing screen)."""
        self.app.pop_screen()  # pop results
        # If processing screen is below, pop it too
        try:
            self.app.pop_screen()  # pop processing
        except Exception:
            pass

    def action_rerun(self) -> None:
        """Restart from config."""
        self.action_back()
        self.app.push_screen("config")


# ═══════════════════════════════════════════════════════════════════════════
#  App — defined after all screens to avoid forward-reference issues
# ═══════════════════════════════════════════════════════════════════════════

class LutEvalApp(App):
    """Main LUT evaluation TUI application."""

    TITLE      = "LUT AI — LUT Evaluation & Ranking"
    SUB_TITLE  = "LUT Color Grading Tool"
    CSS_PATH   = None  # inline styles below

    # ── Load .env on startup ────────────────────────────────────────
    def __init__(self) -> None:
        super().__init__()
        self._load_dotenv()

    @staticmethod
    def _load_dotenv() -> None:
        """Load .env file from ~/.config/lut-ai/.env or $PWD/.env"""
        candidates = [
            os.path.join(os.environ.get("HOME", ""), ".config", "lut-ai", ".env"),
            os.path.join(os.getcwd(), ".env"),
        ]
        for path in candidates:
            if not path or not os.path.isfile(path):
                continue
            try:
                with open(path) as f:
                    for line in f:
                        line = line.strip()
                        if not line or line.startswith("#"):
                            continue
                        if "=" not in line:
                            continue
                        key, _, val = line.partition("=")
                        key = key.strip()
                        val = val.strip().strip("'\"")
                        if key and not os.environ.get(key):
                            os.environ[key] = val
            except OSError:
                pass

    # Shared state between screens
    config:      AppConfig     = AppConfig()
    result:      RankingResult = RankingResult()
    eval_running: bool         = False
    total_luts:  int           = 0
    processed:   int           = 0

    def on_mount(self) -> None:
        self.install_screen(ConfigScreen(),  "config")
        self.install_screen(ProcessingScreen(), "processing")
        self.install_screen(ResultsScreen(), "results")
        self.push_screen("config")


# ═══════════════════════════════════════════════════════════════════════════
#  CSS styles
# ═══════════════════════════════════════════════════════════════════════════

LutEvalApp.CSS = """
/* archinstall-inspired minimal style — works in any terminal */

Screen {
    background: $surface;
}

.section-title {
    padding: 1 0 0 0;
    text-style: bold;
    color: $accent;
}

.hint {
    padding: 0 0 0 1;
    color: $text-muted;
}

/* ── Config Screen ─────────────────────────────────────────────────────── */

#screen-title {
    padding: 1 0;
    text-align: center;
}

#config-columns {
    height: 1fr;
}

#config-columns {
    height: 1fr;
}

.menu-column {
    width: 22;
    min-width: 18;
    padding: 0 1 0 0;
    height: 1fr;
}

.menu-heading {
    padding: 0 0 0 1;
    text-style: bold;
    color: $accent;
}

#config-menu {
    height: 1fr;
}

#config-menu ListItem {
    padding: 1 1;
}

#config-menu ListItem:hover {
    background: $primary 20%;
}

#config-menu > ListItem.--highlight {
    background: $primary 40%;
}

#config-panels {
    width: 1fr;
    height: 1fr;
    padding: 0 0 0 1;
}

.switch-label {
    padding: 0 0 0 1;
    color: $text-muted;
    text-style: bold;
}

#config-scroll {
    overflow-y: scroll;
    height: 1fr;
}

Scrollbar {
    scrollbar-color: $primary 30%;
}

Scrollbar:focus {
    scrollbar-color: $accent 50%;
}

SelectionList {
    height: 8;
    max-height: 10;
}

.select-buttons {
    height: 3;
    align: left middle;
}

.select-buttons Button {
    width: 12;
    margin: 0 1 0 0;
}

.option-row {
    height: 3;
    align: left middle;
}

.toggle-label {
    width: 20;
}

.option-input {
    width: 14;
}

.option-input-wide {
    width: 30;
}

.option-select {
    width: 18;
}

.button-row {
    height: 5;
    align: center middle;
    padding: 1 0;
}

.button-row Button {
    margin: 0 1;
    min-width: 20;
}

#expert-settings {
    margin: 1 0;
}

#expert-hint {
    padding: 0 0 1 1;
}

/* ── Processing Screen ─────────────────────────────────────────────────── */

#proc-container {
    padding: 1 2;
    height: 100%;
}

#proc-title {
    text-align: center;
    padding: 0 0 1 0;
}

#proc-bar {
    margin: 0 0 1 0;
}

#proc-current {
    padding: 0 0 1 0;
    text-align: center;
}

#proc-log {
    height: 1fr;
    margin: 0 0 1 0;
}

#cancel-btn {
    align: center bottom;
    width: 20;
}

/* ── Results Screen ────────────────────────────────────────────────────── */

#results-layout {
    height: 1fr;
}

.panel {
    height: 100%;
}

.left-panel {
    width: 60%;
    min-width: 40;
}

.right-panel {
    width: 40%;
    min-width: 35;
    padding: 0 1;
}

.result-box {
    padding: 0 0 1 0;
    min-height: 4;
}

#rankings-table {
    height: 1fr;
}

#detail-panel {
    min-height: 6;
    width: 100%;
    overflow-y: auto;
}

.query-row {
    height: 3;
}

.query-row Input {
    width: 1fr;
}

.query-row Button {
    width: 10;
    margin: 0 0 0 1;
}

#query-response {
    height: 1fr;
    width: 100%;
    border: none;
    overflow-y: auto;
}
"""


# ═══════════════════════════════════════════════════════════════════════════
#  Entry point
# ═══════════════════════════════════════════════════════════════════════════

def _wrap(text: str, width: int) -> str:
    """Simple word wrap for detail text."""
    words = text.split()
    lines = []
    line = ""
    for w in words:
        if len(line) + len(w) + 1 > width:
            lines.append(line)
            line = w
        else:
            line = f"{line} {w}" if line else w
    if line:
        lines.append(line)
    return "\n".join(lines)


def run_tui() -> None:
    """Launch the TUI application."""
    app = LutEvalApp()
    app.run()


if __name__ == "__main__":
    run_tui()
