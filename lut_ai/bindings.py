"""
bindings.py — ctypes bindings to liblut_eval_core.so

Loads the C shared library and exposes its functions with
Python-friendly signatures.
"""

import ctypes
import os
from typing import Optional

from .models import ColorStats


# ── Load library ─────────────────────────────────────────────────────────

_lib: Optional[ctypes.CDLL] = None


def _get_lib_path() -> str:
    """Resolve the path to liblut_eval_core.so."""
    # Look relative to this file's directory: ../../core/
    here = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        os.path.join(here, "..", "core", "liblut_eval_core.so"),
        os.path.join(here, "..", "..", "core", "liblut_eval_core.so"),
        os.path.join(here, "liblut_eval_core.so"),
    ]
    # Also check LD_LIBRARY_PATH / standard locations
    for path in candidates:
        path = os.path.normpath(path)
        if os.path.isfile(path):
            return path

    # Last resort: let the system loader find it
    return "liblut_eval_core.so"


def load_library() -> ctypes.CDLL:
    """Load the C core library and set up function signatures."""
    global _lib
    if _lib is not None:
        return _lib

    lib_path = _get_lib_path()

    try:
        _lib = ctypes.CDLL(lib_path)
    except OSError as e:
        raise RuntimeError(
            f"Cannot load liblut_eval_core.so: {e}\n"
            f"Looked for: {lib_path}\n"
            "Try: cd core && make"
        ) from e

    # ── extract_stats ──────────────────────────────────────────────────
    _lib.extract_stats.argtypes = [
        ctypes.POINTER(ctypes.c_uint8),  # data
        ctypes.c_int,                      # w
        ctypes.c_int,                      # h
        ctypes.c_void_p,                   # stats (output)
    ]
    _lib.extract_stats.restype = ctypes.c_int

    # ── stats_serialize ─────────────────────────────────────────────────
    _lib.stats_serialize.argtypes = [
        ctypes.c_void_p,   # stats
        ctypes.c_char_p,   # buf
        ctypes.c_int,      # buf_size
    ]
    _lib.stats_serialize.restype = ctypes.c_int

    # ── local_evaluate ──────────────────────────────────────────────────
    _lib.local_evaluate.argtypes = [
        ctypes.c_void_p,   # stats
        ctypes.c_void_p,   # result (output)
    ]
    _lib.local_evaluate.restype = None

    return _lib


# ── Color stats structure (mirrors C side) ───────────────────────────────

class CColorStats(ctypes.Structure):
    _fields_ = [
        ("avg_r",     ctypes.c_float),
        ("avg_g",     ctypes.c_float),
        ("avg_b",     ctypes.c_float),
        ("avg_h",     ctypes.c_float),
        ("avg_s",     ctypes.c_float),
        ("avg_v",     ctypes.c_float),
        ("contrast",  ctypes.c_float),
        ("warm_bias", ctypes.c_float),
    ]


class CLocalEvalResult(ctypes.Structure):
    _fields_ = [
        ("score",       ctypes.c_float),
        ("tags",        ctypes.c_char * 256),
        ("description", ctypes.c_char * 512),
    ]


# ── Python API ───────────────────────────────────────────────────────────

def extract_stats(data: bytes, w: int, h: int) -> ColorStats:
    """Extract color statistics from raw RGB pixel data.

    Args:
        data: Tightly packed RGB bytes (w × h × 3).
        w: Image width.
        h: Image height.

    Returns:
        ColorStats with all 8 features.

    Raises:
        RuntimeError: If the C function fails or library not loaded.
    """
    lib = load_library()

    buf = (ctypes.c_uint8 * len(data)).from_buffer_copy(data)
    c_stats = CColorStats()

    ret = lib.extract_stats(buf, ctypes.c_int(w), ctypes.c_int(h),
                            ctypes.byref(c_stats))
    if ret != 0:
        raise RuntimeError("extract_stats returned error")

    return ColorStats(
        avg_r=c_stats.avg_r,
        avg_g=c_stats.avg_g,
        avg_b=c_stats.avg_b,
        avg_h=c_stats.avg_h,
        avg_s=c_stats.avg_s,
        avg_v=c_stats.avg_v,
        contrast=c_stats.contrast,
        warm_bias=c_stats.warm_bias,
    )


def stats_serialize(stats: ColorStats) -> str:
    """Serialize ColorStats to a short text string."""
    lib = load_library()

    c_stats = CColorStats(
        avg_r=stats.avg_r,
        avg_g=stats.avg_g,
        avg_b=stats.avg_b,
        avg_h=stats.avg_h,
        avg_s=stats.avg_s,
        avg_v=stats.avg_v,
        contrast=stats.contrast,
        warm_bias=stats.warm_bias,
    )

    buf = ctypes.create_string_buffer(1024)
    lib.stats_serialize(ctypes.byref(c_stats), buf, ctypes.c_int(1024))

    return buf.value.decode("utf-8")


def local_evaluate(stats: ColorStats) -> tuple[float, str, str]:
    """Run local heuristic evaluation.

    Args:
        stats: Color statistics.

    Returns:
        Tuple of (score, tags_str, description).
    """
    lib = load_library()

    c_stats = CColorStats(
        avg_r=stats.avg_r,
        avg_g=stats.avg_g,
        avg_b=stats.avg_b,
        avg_h=stats.avg_h,
        avg_s=stats.avg_s,
        avg_v=stats.avg_v,
        contrast=stats.contrast,
        warm_bias=stats.warm_bias,
    )
    c_result = CLocalEvalResult()

    lib.local_evaluate(ctypes.byref(c_stats), ctypes.byref(c_result))

    return (
        c_result.score,
        c_result.tags.decode("utf-8"),
        c_result.description.decode("utf-8"),
    )
