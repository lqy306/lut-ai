# Makefile — lut_ai: build C core, run TUI, package AppImage
.POSIX:

CC      = gcc
CFLAGS  = -std=c99 -O2 -fPIC -Wall -Wextra -Wno-unused-function -pedantic
LDFLAGS = -shared
LIBS    = -lm

APPNAME = lut-ai
COREDIR = core
LUTAIDIR = lut_ai

.PHONY: all lib run tui cli clean appimage

# ── Default ──────────────────────────────────────────────────────────────

all: lib
	@echo "lut-ai — LUT Evaluation & Ranking"
	@echo ""
	@echo "  Usage:"
	@echo "    make tui          # Start Textual TUI"
	@echo "    make cli          # CLI mode"
	@echo "    make appimage     # Package as AppImage"
	@echo ""

# ── Build C core library ─────────────────────────────────────────────────

lib: $(COREDIR)/liblut_eval_core.so

$(COREDIR)/liblut_eval_core.so: $(COREDIR)/stats.o $(COREDIR)/local_eval.o
	$(CC) $(LDFLAGS) -o $@ $^ $(LIBS)

$(COREDIR)/stats.o: $(COREDIR)/stats.c $(COREDIR)/lut_eval.h
	$(CC) $(CFLAGS) -c $< -o $@

$(COREDIR)/local_eval.o: $(COREDIR)/local_eval.c $(COREDIR)/lut_eval.h
	$(CC) $(CFLAGS) -c $< -o $@

# ── Run TUI (Textual) ────────────────────────────────────────────────────

tui: lib
	PYTHONPATH=$(PWD) python3 -m $(LUTAIDIR).tui

# ── Run CLI (rich) ───────────────────────────────────────────────────────

cli: lib
	PYTHONPATH=$(PWD) python3 -m $(LUTAIDIR) --tui

# ── Run as module ────────────────────────────────────────────────────────

run: tui

# ── AppImage ─────────────────────────────────────────────────────────────

APPDIR      = build/$(APPNAME).AppDir
APPIMAGE    = $(APPNAME)-x86_64.AppImage
APIMAGE_URL = https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-x86_64.AppImage
APIMAGE_BIN = build/appimagetool

appimage: lib build/appimagetool
	@echo "==> Creating AppDir structure..."
	rm -rf $(APPDIR)
	mkdir -p $(APPDIR)/usr/lib
	mkdir -p $(APPDIR)/usr/share/$(APPNAME)/lut_ai
	mkdir -p $(APPDIR)/usr/share/applications
	mkdir -p $(APPDIR)/usr/share/icons/hicolor/256x256/apps

	@echo "==> Copying C library..."
	cp $(COREDIR)/liblut_eval_core.so $(APPDIR)/usr/lib/

	@echo "==> Copying Python package..."
	cp -r $(LUTAIDIR) $(APPDIR)/usr/share/$(APPNAME)/

	@echo "==> Installing Python dependencies..."
	python3 -m pip install --target $(APPDIR)/usr/share/$(APPNAME)/deps \
		Pillow requests rich textual --quiet \
		--break-system-packages 2>/dev/null || \
	python3 -m pip install --target $(APPDIR)/usr/share/$(APPNAME)/deps \
		Pillow requests rich textual --quiet

	@echo "==> Creating lut-ai.desktop..."
	{ \
		echo "[Desktop Entry]"; \
		echo "Type=Application"; \
		echo "Name=lut-ai"; \
		echo "Comment=LUT Evaluation & Ranking Tool"; \
		echo "Exec=lut-ai"; \
		echo "Icon=lut-ai"; \
		echo "Categories=Graphics;Qt;"; \
		echo "Terminal=true"; \
	} > $(APPDIR)/usr/share/applications/lut-ai.desktop
	cp $(APPDIR)/usr/share/applications/lut-ai.desktop $(APPDIR)/

	@echo "==> Generating icon..."
	python3 tools/mkicon.py $(APPDIR)/usr/share/icons/hicolor/256x256/apps/lut-ai.png
	cp $(APPDIR)/usr/share/icons/hicolor/256x256/apps/lut-ai.png $(APPDIR)/

	@echo "==> Creating AppRun..."
	{ \
		echo '#!/bin/bash'; \
		echo 'HERE="$$(dirname "$$(readlink -f "$$0")")"'; \
		echo 'APP_DIR="$$HERE/usr/share/$(APPNAME)"'; \
		echo 'export LD_LIBRARY_PATH="$$HERE/usr/lib:$$LD_LIBRARY_PATH"'; \
		echo 'export PYTHONPATH="$$APP_DIR:$$APP_DIR/deps:$$PYTHONPATH"'; \
		echo ''; \
		echo '# By default launch TUI; use --cli for terminal mode'; \
		echo 'if [ "$$1" = "--cli" ]; then'; \
		echo '    shift'; \
		echo '    cd "$$APP_DIR" || exit 1'; \
		echo '    exec python3 -m lut_ai "$$@"'; \
		echo 'else'; \
		echo '    cd "$$APP_DIR" || exit 1'; \
		echo '    exec python3 -m lut_ai.tui "$$@"'; \
		echo 'fi'; \
	} > $(APPDIR)/AppRun
	chmod +x $(APPDIR)/AppRun

	@echo "==> Running appimagetool..."
	ARCH=x86_64 $(APIMAGE_BIN) $(APPDIR) $(APPIMAGE)
	@echo "==> Done: $(APPIMAGE)"

build/appimagetool:
	@echo "==> Downloading appimagetool..."
	mkdir -p build
	curl -sL -o $(APIMAGE_BIN) $(APIMAGE_URL)
	chmod +x $(APIMAGE_BIN)

# ── Clean ────────────────────────────────────────────────────────────────

clean:
	rm -f $(COREDIR)/*.o $(COREDIR)/*.so
	rm -rf build/
	find . -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null || true
	find . -name '*.pyc' -delete
	@echo "Cleaned."
