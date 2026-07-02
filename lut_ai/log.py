"""
log.py — Simple file logging for debugging

Writes to $HOME/.cache/lut-ai/lut-ai.log or /tmp/lut-ai.log
with timestamps. No external dependencies.
"""

import os
import sys
from datetime import datetime

_LOG_FILE: str | None = None


def _log_path() -> str:
    global _LOG_FILE
    if _LOG_FILE:
        return _LOG_FILE
    home = os.environ.get("HOME", "/tmp")
    log_dir = os.path.join(home, ".cache", "lut-ai")
    try:
        os.makedirs(log_dir, exist_ok=True)
        _LOG_FILE = os.path.join(log_dir, "lut-ai.log")
    except OSError:
        _LOG_FILE = "/tmp/lut-ai.log"
    return _LOG_FILE


def info(msg: str) -> None:
    """Write an info-level log entry."""
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] INFO  {msg}"
    _write(line)


def error(msg: str) -> None:
    """Write an error-level log entry."""
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] ERROR {msg}"
    _write(line)


def debug(msg: str) -> None:
    """Write a debug-level log entry."""
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] DEBUG {msg}"
    _write(line)


def _write(line: str) -> None:
    try:
        path = _log_path()
        with open(path, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass  # can't log, ignore
