"""
cli.py — Rich-based CLI for LUT evaluation

Provides:
  - LUT scanning and selection
  - Image processing with LUT application
  - Color statistics extraction (via C library)
  - AI ranking or local heuristic evaluation
  - Query matching
  - Progress display and formatted output
"""

import os
import sys
import time
from typing import Optional

from PIL import Image

from .models import AppConfig, ColorStats, EvalResult, RankingResult
from .lut_apply import load_lut, scan_luts, clear_lut_cache

# Try importing rich; provide fallback if not available
try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich.progress import (
        Progress, SpinnerColumn, TextColumn, BarColumn,
        TaskProgressColumn, TimeRemainingColumn
    )
    from rich.style import Style
    from rich.text import Text
    from rich.columns import Columns
    from rich.layout import Layout
    from rich.live import Live
    from rich.syntax import Syntax
    from rich.prompt import Prompt, Confirm
    from rich import box
    HAS_RICH = True
except ImportError:
    HAS_RICH = False

from . import bindings


# ── Console ──────────────────────────────────────────────────────────────

_console = None


def get_console():
    global _console
    if _console is None:
        _console = Console() if HAS_RICH else None
    return _console


# ── Pipeline: LUT application → stats extraction ─────────────────────────

def process_lut(lut_name: str,
                lut_dir: str,
                source_img: Image.Image,
                thumbnail_size: tuple[int, int] = (256, 256)
                ) -> tuple[Optional[ColorStats], Optional[Image.Image]]:
    """Apply a LUT to the source image and extract color statistics.

    Args:
        lut_name: LUT name (without .cube extension).
        lut_dir: Directory containing .cube files.
        source_img: Source PIL image (will be thumbnailed).
        thumbnail_size: Size for processing thumbnail.

    Returns:
        Tuple of (ColorStats, processed_image) or (None, None) on error.
    """
    try:
        lut_path = os.path.join(lut_dir, lut_name + ".cube")
        if not os.path.isfile(lut_path):
            # Try with .cube extension
            lut_path = os.path.join(lut_dir, lut_name)
            if not os.path.isfile(lut_path):
                print(f"  [SKIP] LUT file not found: {lut_name}")
                return None, None

        lut = load_lut(lut_name, lut_dir)
    except Exception as e:
        print(f"  [ERROR] Loading LUT {lut_name}: {e}")
        return None, None

    # Create thumbnail for processing
    thumb = source_img.copy()
    thumb.thumbnail(thumbnail_size, Image.LANCZOS)

    try:
        processed = lut.apply_image(thumb)
    except Exception as e:
        print(f"  [ERROR] Applying LUT {lut_name}: {e}")
        return None, None

    # Extract stats using C library
    try:
        w, h = processed.size
        raw_bytes = processed.tobytes()
        stats = bindings.extract_stats(raw_bytes, w, h)
    except Exception as e:
        print(f"  [ERROR] Extracting stats for {lut_name}: {e}")
        return None, None

    return stats, processed


def run_evaluation(config: AppConfig) -> RankingResult:
    """Run the full evaluation pipeline.

    1. Scan LUT directories for .cube files
    2. Load source image
    3. Apply each LUT and extract stats
    4. Run AI ranking or local heuristic evaluation
    5. Return ranked results

    Args:
        config: Application configuration.

    Returns:
        RankingResult with ranked evaluations.
    """
    console = get_console()

    # ── Scan LUTs ────────────────────────────────────────────────────
    all_lut_names: list[str] = []
    for d in config.lut_dirs:
        names = scan_luts(d)
        all_lut_names.extend(names)
        if console and HAS_RICH:
            console.log(f"  [dim]{d}[/dim]: {len(names)} LUTs found")

    if not all_lut_names:
        if console and HAS_RICH:
            console.print("[red]No .cube LUT files found.[/red]")
        else:
            print("No .cube LUT files found.")
        return RankingResult()

    # Deduplicate
    all_lut_names = sorted(set(all_lut_names))

    if config.max_luts > 0:
        all_lut_names = all_lut_names[:config.max_luts]

    if console and HAS_RICH:
        console.print(f"\n[bold]LUTs found:[/bold] {len(all_lut_names)}")
    else:
        print(f"\nLUTs found: {len(all_lut_names)}")

    # ── Load source image ────────────────────────────────────────────
    if not os.path.isfile(config.image_path):
        if console and HAS_RICH:
            console.print(f"[red]Image not found: {config.image_path}[/red]")
        else:
            print(f"Image not found: {config.image_path}")
        return RankingResult()

    try:
        source_img = Image.open(config.image_path).convert("RGB")
    except Exception as e:
        if console and HAS_RICH:
            console.print(f"[red]Cannot open image: {e}[/red]")
        else:
            print(f"Cannot open image: {e}")
        return RankingResult()

    if console and HAS_RICH:
        console.print(f"Image: [cyan]{config.image_path}[/cyan] "
                      f"({source_img.width}x{source_img.height})")
    else:
        print(f"Image: {config.image_path} "
              f"({source_img.width}x{source_img.height})")

    # ── Process each LUT ─────────────────────────────────────────────
    stats_list: list[tuple[str, ColorStats]] = []
    processed_images: list[tuple[str, Image.Image]] = []

    if console and HAS_RICH:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            TimeRemainingColumn(),
            console=console,
        ) as progress:
            task = progress.add_task(
                "[yellow]Processing LUTs...[/yellow]",
                total=len(all_lut_names),
            )

            for name in all_lut_names:
                stats, proc_img = process_lut(name, config.lut_dirs[0],
                                               source_img)
                if stats is not None:
                    stats_list.append((name, stats))
                    if proc_img is not None:
                        processed_images.append((name, proc_img))
                progress.advance(task)
    else:
        print(f"\nProcessing {len(all_lut_names)} LUTs...")
        for i, name in enumerate(all_lut_names):
            stats, proc_img = process_lut(name, config.lut_dirs[0],
                                           source_img)
            if stats is not None:
                stats_list.append((name, stats))
                if proc_img is not None:
                    processed_images.append((name, proc_img))
            print(f"  [{i+1}/{len(all_lut_names)}] {name}", end="")
            print(" OK" if stats else " FAIL")

    if not stats_list:
        if console and HAS_RICH:
            console.print("[red]No LUTs could be processed.[/red]")
        else:
            print("No LUTs could be processed.")
        return RankingResult()

    # ── Evaluate ─────────────────────────────────────────────────────
    if config.use_ai:
        if console and HAS_RICH:
            console.print("\n[bold]Calling AI for ranking...[/bold]")
        else:
            print("\nCalling AI for ranking...")

        try:
            # Build stats text pairs
            stats_texts = [
                (name, bindings.stats_serialize(stats))
                for name, stats in stats_list
            ]

            result = ai_interface.call_ai_ranking(
                stats_texts,
                base_url=config.base_url,
                api_key=config.api_key,
                model=config.model,
                temperature=config.temperature,
                language=config.language,
                stream=config.stream,
            )
        except Exception as e:
            if console and HAS_RICH:
                console.print(f"[red]AI ranking failed: {e}[/red]")
                console.print("[yellow]Falling back to local evaluation.[/yellow]")
            else:
                print(f"AI ranking failed: {e}")
                print("Falling back to local evaluation.")
            config.use_ai = False

    if not config.use_ai:
        # Local heuristic evaluation
        rankings = []
        for name, stats in stats_list:
            score, tags_str, desc = bindings.local_evaluate(stats)
            tags = [t.strip() for t in tags_str.split(",") if t.strip()]
            rankings.append(EvalResult(
                name=name,
                score=score,
                style_tags=tags,
                description=desc,
                stats=stats,
                eval_source="local",
            ))

        # Sort by score descending, assign ranks
        rankings.sort(key=lambda r: r.score, reverse=True)
        for i, r in enumerate(rankings):
            r.rank = i + 1

        result = RankingResult(
            rankings=rankings,
            best_lut=rankings[0].name if rankings else "",
            best_reason=rankings[0].description if rankings else "",
        )

    return result


# ── Display helpers ──────────────────────────────────────────────────────

def print_ranking(result: RankingResult, language: str = "zh") -> None:
    """Print ranking results in a formatted table.

    Args:
        result: RankingResult to display.
        language: "zh" or "en".
    """
    console = get_console()

    if not result.rankings:
        if console and HAS_RICH:
            console.print("[red]No results to display.[/red]")
        else:
            print("No results to display.")
        return

    if console and HAS_RICH:
        # Best LUT panel
        best = result.rankings[0] if result.rankings else None
        if best:
            best_panel = Panel(
                f"[bold cyan]{best.name}[/bold cyan]\n"
                f"[yellow]Score: {best.score:.0f}/100[/yellow]\n"
                f"[green]{', '.join(best.style_tags)}[/green]\n\n"
                f"{best.description}",
                title="[bold]Best LUT[/bold]",
                border_style="cyan",
                box=box.ROUNDED,
            )
            console.print("")
            console.print(best_panel)

        if result.best_reason and result.best_lut:
            console.print(Panel(
                result.best_reason,
                title=f"[bold]Why {result.best_lut} won[/bold]",
                border_style="blue",
            ))

        # Rankings table
        table = Table(
            title="LUT Rankings",
            box=box.SIMPLE,
            header_style="bold magenta",
        )
        table.add_column("Rank", style="dim", width=6)
        table.add_column("LUT", style="cyan")
        table.add_column("Score", justify="right")
        table.add_column("Tags")
        table.add_column("Description", width=50)

        for r in result.rankings:
            score_style = "green" if r.score >= 80 else \
                          "yellow" if r.score >= 60 else "red"
            tags_str = ", ".join(r.style_tags[:4])
            if len(r.style_tags) > 4:
                tags_str += "..."

            table.add_row(
                f"#{r.rank}",
                r.name,
                f"[{score_style}]{r.score:.0f}[/{score_style}]",
                tags_str,
                r.description[:48],
            )

        console.print("")
        console.print(table)
        console.print("")

        # Source indicator
        source = result.rankings[0].eval_source if result.rankings else "?"
        console.print(f"[dim]Evaluation source: {source}[/dim]")

    else:
        # Plain text fallback
        print(f"\n{'='*60}")
        print(f"LUT RANKINGS  (source: {result.rankings[0].eval_source})")
        print(f"{'='*60}")
        print(f"\nBest LUT: {result.best_lut}")
        if result.best_reason:
            print(f"Reason: {result.best_reason}")
        print(f"\n{'Rank':<6} {'LUT':<30} {'Score':<8} Tags")
        print(f"{'-'*60}")
        for r in result.rankings:
            tags_str = ", ".join(r.style_tags[:4])
            print(f"#{r.rank:<4} {r.name:<30} {r.score:<8.0f} {tags_str}")


def print_query_results(
    matches: list[tuple[EvalResult, float, str]],
) -> None:
    """Print query matching results.

    Args:
        matches: List of (result, match_score, reason) tuples.
    """
    console = get_console()

    if not matches:
        if console and HAS_RICH:
            console.print("[yellow]No matches found.[/yellow]")
        else:
            print("No matches found.")
        return

    if console and HAS_RICH:
        table = Table(
            title="Query Matches",
            box=box.SIMPLE,
            header_style="bold blue",
        )
        table.add_column("LUT", style="cyan")
        table.add_column("Match %", justify="right")
        table.add_column("Score", justify="right")
        table.add_column("Reason")

        for r, match_score, reason in matches:
            table.add_row(
                r.name,
                f"{match_score:.0f}%",
                f"{r.score:.0f}",
                reason[:60],
            )

        console.print("\n")
        console.print(table)
    else:
        print(f"\nQuery Matches:")
        print(f"{'LUT':<30} {'Match%':<10} {'Score':<8} Reason")
        print(f"{'-'*60}")
        for r, ms, reason in matches:
            print(f"{r.name:<30} {ms:<10.0f} {r.score:<8.0f} {reason[:60]}")


# ── Main CLI entry point ─────────────────────────────────────────────────

def run_cli() -> None:
    """Main CLI entry point."""
    # Check for --tui flag before argparse consumes it
    if "--tui" in sys.argv:
        try:
            from .tui import run_tui
            run_tui()
        except ImportError as e:
            print(f"TUI not available: {e}")
            print("Install textual: pip install textual")
        return

    config = _parse_args()

    if not HAS_RICH:
        print("Note: Install 'rich' for prettier output: pip install rich")
        print()

    if config.image_path and config.lut_dirs:
        result = run_evaluation(config)
        print_ranking(result, config.language)

        # Query mode
        if config.query:
            _handle_query(result.rankings, config)

    elif config.query and config.results_file:
        # Load saved results and query
        _handle_query_from_file(config)
    else:
        _print_usage()


def _parse_args() -> AppConfig:
    """Parse command-line arguments.

    Returns AppConfig with parsed values.
    """
    import argparse

    parser = argparse.ArgumentParser(
        description="LUT Evaluation & Ranking Tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Local evaluation
  lut-ai -i photo.jpg -l luts/

  # AI ranking
  lut-ai -i photo.jpg -l luts/ --use-ai --api-key sk-xxx

  # AI ranking with custom API (e.g., Ollama, vLLM)
  lut-ai -i photo.jpg -l luts/ --use-ai \\
    --base-url http://localhost:8000/v1 --model qwen2.5:14b

  # Query matching (after evaluation)
  lut-ai -i photo.jpg -l luts/ --query "德味/电影感"

  # Limit number of LUTs to evaluate
  lut-ai -i photo.jpg -l luts/ --max-luts 20
        """,
    )

    parser.add_argument("-i", "--image", dest="image_path",
                        default="", help="Source image path")
    parser.add_argument("-l", "--lut-dir", dest="lut_dirs",
                        action="append", default=[],
                        help="LUT directory (repeatable)")
    parser.add_argument("--max-luts", type=int, default=0,
                        help="Max LUTs to evaluate (0 = all)")
    parser.add_argument("--use-ai", action="store_true",
                        help="Use AI for ranking")
    parser.add_argument("--api-key", default="",
                        help="OpenAI API key")
    parser.add_argument("--base-url",
                        default="https://api.openai.com/v1",
                        help="API base URL")
    parser.add_argument("--model", default="gpt-4o",
                        help="Model name")
    parser.add_argument("--temperature", type=float, default=0.3)
    parser.add_argument("--lang", default="en",
                        choices=["zh", "en"],
                        help="Output language")
    parser.add_argument("--no-stream", action="store_true",
                        help="Disable streaming")
    parser.add_argument("--query", default="",
                        help="Query to match LUTs against")
    parser.add_argument("--results", dest="results_file",
                        default="",
                        help="Load saved results file for query matching")
    parser.add_argument("--save-results", default="",
                        help="Save evaluation results to JSON file")
    parser.add_argument("--tui", action="store_true",
                        help="Launch Textual TUI interface")

    args = parser.parse_args()

    # Auto-discover LUT dirs
    lut_dirs = args.lut_dirs
    if not lut_dirs:
        # Check common locations
        candidates = [
            "./luts",
            "./Luts",
            "./lut",
            "./luts/tmp_gmic/luts",
            "./Luts/电影风格",
            "./Luts/风格化",
        ]
        for c in candidates:
            if os.path.isdir(c):
                lut_dirs.append(c)

    return AppConfig(
        base_url=args.base_url,
        api_key=args.api_key,
        model=args.model,
        temperature=args.temperature,
        language=args.lang,
        lut_dirs=lut_dirs,
        image_path=args.image_path,
        use_ai=args.use_ai,
        stream=not args.no_stream,
        max_luts=args.max_luts,
        query=args.query,
        results_file=args.results_file,
        save_results=args.save_results,
    )


def _handle_query(rankings: list[EvalResult], config: AppConfig) -> None:
    """Handle query matching mode."""
    if not config.query.strip():
        return

    if config.use_ai and config.api_key:
        try:
            from . import ai_interface
            matches = ai_interface.call_ai_query_match(
                rankings,
                config.query,
                base_url=config.base_url,
                api_key=config.api_key,
                model=config.model,
                temperature=config.temperature,
                language=config.language,
                stream=config.stream,
            )
        except Exception as e:
            console = get_console()
            if console and HAS_RICH:
                console.print(f"[yellow]AI query match failed, "
                              f"falling back to keyword: {e}[/yellow]")
            else:
                print(f"AI query match failed, falling back to keyword: {e}")
            from .query_match import keyword_match
            matches = keyword_match(rankings, config.query)
    else:
        from .query_match import keyword_match
        matches = keyword_match(rankings, config.query)

    print_query_results(matches)


def _handle_query_from_file(config: AppConfig) -> None:
    """Load saved results and run query matching."""
    import json

    try:
        with open(config.results_file, "r") as f:
            data = json.load(f)
        rankings = [EvalResult(**item) for item in data.get("rankings", [])]
    except Exception as e:
        console = get_console()
        if console and HAS_RICH:
            console.print(f"[red]Cannot load results: {e}[/red]")
        else:
            print(f"Cannot load results: {e}")
        return

    _handle_query(rankings, config)


def _print_usage() -> None:
    """Print usage information."""
    if HAS_RICH:
        console = get_console()
        console.print(Panel(
            "LUT Evaluation & Ranking Tool\n\n"
            "Usage:\n"
            "  lut-ai -i <image> -l <lut_dir> [options]\n\n"
            "Examples:\n"
            "  lut-ai -i photo.jpg -l luts/\n"
            "  lut-ai -i photo.jpg -l luts/ --use-ai --api-key sk-xxx\n"
            "  lut-ai -i photo.jpg -l luts/ --query \"德味/电影感\"\n\n"
            "Options:\n"
            "  -i, --image       Source image path\n"
            "  -l, --lut-dir     LUT directory (repeatable)\n"
            "  --use-ai          Use AI for ranking\n"
            "  --api-key         OpenAI API key\n"
            "  --base-url        API base URL\n"
            "  --model           Model name (default: gpt-4o)\n"
            "  --lang            Output language (zh/en)\n"
            "  --query           Query to match LUTs against\n"
            "  --max-luts        Max LUTs to evaluate (0=all)\n"
            "  --no-stream       Disable streaming\n"
            "  --save-results    Save results to JSON file",
            title="[bold]LUT AI[/bold]",
            border_style="green",
        ))
    else:
        print(__doc__)


# ── For testing / debugging ──────────────────────────────────────────────

if __name__ == "__main__":
    run_cli()
