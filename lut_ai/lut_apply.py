"""
lut_apply.py — Apply 3D LUT (.cube) to PIL images

Supports loading .cube LUT files and applying them via
tetrahedral interpolation. Can optionally use the C library
(libklut_core.so) for faster batch processing.
"""

import os
import re
import struct
from typing import Optional

from PIL import Image


# ── LUT class (pure Python tetrahedral interpolation) ────────────────────

class LUT3D:
    """3D LUT with tetrahedral interpolation (pure Python)."""

    def __init__(self):
        self.size = 0
        self.data = []       # [b][g][r][3]
        self.title = ""
        self.dom_min = [0.0, 0.0, 0.0]
        self.dom_max = [1.0, 1.0, 1.0]

    def load(self, path: str) -> None:
        """Load a .cube LUT file."""
        with open(path, 'r', encoding='utf-8') as f:
            lines = f.readlines()

        parsing = False
        values = []
        for line in lines:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            if not parsing:
                if line.startswith('TITLE'):
                    m = re.search(r'"(.*)"', line)
                    if m:
                        self.title = m.group(1)
                elif line.startswith('LUT_3D_SIZE'):
                    self.size = int(line.split()[-1])
                elif line.startswith('DOMAIN_MIN'):
                    self.dom_min = list(map(float, line.split()[1:4]))
                elif line.startswith('DOMAIN_MAX'):
                    self.dom_max = list(map(float, line.split()[1:4]))
            if line and (line[0] in '-+.' or line[0].isdigit()):
                parsing = True
                parts = line.split()
                if len(parts) >= 3:
                    values.append([float(parts[0]), float(parts[1]),
                                   float(parts[2])])

        if self.size == 0:
            raise ValueError(f"No LUT_3D_SIZE found in {path}")

        expected = self.size ** 3
        if len(values) != expected:
            raise ValueError(
                f"Data mismatch in {path}: {len(values)} vs {expected}")

        # Build 3D data array
        self.data = [[[[0.0] * 3 for _ in range(self.size)]
                      for _ in range(self.size)] for _ in range(self.size)]
        idx = 0
        for b in range(self.size):
            for g in range(self.size):
                for r in range(self.size):
                    self.data[b][g][r] = values[idx]
                    idx += 1

    def apply_pixel(self, r: float, g: float, b: float
                    ) -> tuple[float, float, float]:
        """Tetrahedral interpolation for one RGB pixel (0–1)."""
        if self.size < 2:
            return (r, g, b)

        sf = self.size - 1
        rs, gs, bs = r * sf, g * sf, b * sf
        ri, gi, bi = int(rs), int(gs), int(bs)
        rf, gf, bf = rs - ri, gs - gi, bs - bi

        if ri >= sf:
            ri, rf = sf - 1, 1.0
        if gi >= sf:
            gi, gf = sf - 1, 1.0
        if bi >= sf:
            bi, bf = sf - 1, 1.0

        d = self.data
        c000 = d[bi][gi][ri]
        c100 = d[bi][gi][ri + 1]
        c010 = d[bi][gi + 1][ri]
        c110 = d[bi][gi + 1][ri + 1]
        c001 = d[bi + 1][gi][ri]
        c101 = d[bi + 1][gi][ri + 1]
        c011 = d[bi + 1][gi + 1][ri]
        c111 = d[bi + 1][gi + 1][ri + 1]

        def interp(c0, c1, c2, c3, f1, f2, f3):
            return (
                c0[0] * (1 - f1) + c1[0] * (f1 - f2)
                + c2[0] * (f2 - f3) + c3[0] * f3,
                c0[1] * (1 - f1) + c1[1] * (f1 - f2)
                + c2[1] * (f2 - f3) + c3[1] * f3,
                c0[2] * (1 - f1) + c1[2] * (f1 - f2)
                + c2[2] * (f2 - f3) + c3[2] * f3,
            )

        if rf >= gf and gf >= bf:
            return interp(c000, c100, c110, c111, rf, gf, bf)
        elif rf >= bf and bf >= gf:
            return interp(c000, c100, c101, c111, rf, bf, gf)
        elif gf >= rf and rf >= bf:
            return interp(c000, c010, c110, c111, gf, rf, bf)
        elif gf >= bf and bf >= rf:
            return interp(c000, c010, c011, c111, gf, bf, rf)
        elif bf >= rf and rf >= gf:
            return interp(c000, c001, c101, c111, bf, rf, gf)
        else:
            return interp(c000, c001, c011, c111, bf, gf, rf)

    def apply_image(self, img: Image.Image) -> Image.Image:
        """Apply LUT to an entire PIL image."""
        img = img.convert("RGB")
        w, h = img.size
        n = w * h

        raw = img.tobytes()
        out = bytearray(n * 3)

        if self.size < 2:
            return img

        sf = self.size - 1
        data = self.data
        idx = 0

        for _ in range(n):
            r = raw[idx] / 255.0
            g = raw[idx + 1] / 255.0
            b = raw[idx + 2] / 255.0

            rs = r * sf
            gs = g * sf
            bs = b * sf
            ri = int(rs)
            gi = int(gs)
            bi = int(bs)
            rf = rs - ri
            gf = gs - gi
            bf = bs - bi

            if ri >= sf:
                ri = sf - 1
                rf = 1.0
            if gi >= sf:
                gi = sf - 1
                gf = 1.0
            if bi >= sf:
                bi = sf - 1
                bf = 1.0

            d = data
            c000 = d[bi][gi][ri]
            c100 = d[bi][gi][ri + 1]
            c010 = d[bi][gi + 1][ri]
            c110 = d[bi][gi + 1][ri + 1]
            c001 = d[bi + 1][gi][ri]
            c101 = d[bi + 1][gi][ri + 1]
            c011 = d[bi + 1][gi + 1][ri]
            c111 = d[bi + 1][gi + 1][ri + 1]

            if rf >= gf and gf >= bf:
                nr = (c000[0] * (1.0 - rf) + c100[0] * (rf - gf)
                      + c110[0] * (gf - bf) + c111[0] * bf)
                ng = (c000[1] * (1.0 - rf) + c100[1] * (rf - gf)
                      + c110[1] * (gf - bf) + c111[1] * bf)
                nb = (c000[2] * (1.0 - rf) + c100[2] * (rf - gf)
                      + c110[2] * (gf - bf) + c111[2] * bf)
            elif rf >= bf and bf >= gf:
                nr = (c000[0] * (1.0 - rf) + c100[0] * (rf - bf)
                      + c101[0] * (bf - gf) + c111[0] * gf)
                ng = (c000[1] * (1.0 - rf) + c100[1] * (rf - bf)
                      + c101[1] * (bf - gf) + c111[1] * gf)
                nb = (c000[2] * (1.0 - rf) + c100[2] * (rf - bf)
                      + c101[2] * (bf - gf) + c111[2] * gf)
            elif gf >= rf and rf >= bf:
                nr = (c000[0] * (1.0 - gf) + c010[0] * (gf - rf)
                      + c110[0] * (rf - bf) + c111[0] * bf)
                ng = (c000[1] * (1.0 - gf) + c010[1] * (gf - rf)
                      + c110[1] * (rf - bf) + c111[1] * bf)
                nb = (c000[2] * (1.0 - gf) + c010[2] * (gf - rf)
                      + c110[2] * (rf - bf) + c111[2] * bf)
            elif gf >= bf and bf >= rf:
                nr = (c000[0] * (1.0 - gf) + c010[0] * (gf - bf)
                      + c011[0] * (bf - rf) + c111[0] * rf)
                ng = (c000[1] * (1.0 - gf) + c010[1] * (gf - bf)
                      + c011[1] * (bf - rf) + c111[1] * rf)
                nb = (c000[2] * (1.0 - gf) + c010[2] * (gf - bf)
                      + c011[2] * (bf - rf) + c111[2] * rf)
            elif bf >= rf and rf >= gf:
                nr = (c000[0] * (1.0 - bf) + c001[0] * (bf - rf)
                      + c101[0] * (rf - gf) + c111[0] * gf)
                ng = (c000[1] * (1.0 - bf) + c001[1] * (bf - rf)
                      + c101[1] * (rf - gf) + c111[1] * gf)
                nb = (c000[2] * (1.0 - bf) + c001[2] * (bf - rf)
                      + c101[2] * (rf - gf) + c111[2] * gf)
            else:
                nr = (c000[0] * (1.0 - bf) + c001[0] * (bf - gf)
                      + c011[0] * (gf - rf) + c111[0] * rf)
                ng = (c000[1] * (1.0 - bf) + c001[1] * (bf - gf)
                      + c011[1] * (gf - rf) + c111[1] * rf)
                nb = (c000[2] * (1.0 - bf) + c001[2] * (bf - gf)
                      + c011[2] * (gf - rf) + c111[2] * rf)

            out[idx]     = max(0, min(255, int(nr * 255.0)))
            out[idx + 1] = max(0, min(255, int(ng * 255.0)))
            out[idx + 2] = max(0, min(255, int(nb * 255.0)))
            idx += 3

        return Image.frombuffer("RGB", (w, h), bytes(out))


# ── LUT scanning ─────────────────────────────────────────────────────────

LUT_CACHE: dict[str, LUT3D] = {}


def load_lut(name_or_path: str, lut_dir: str = "") -> LUT3D:
    """Load a LUT from cache or disk.

    Args:
        name_or_path: LUT name (without .cube) or full path.
        lut_dir: Directory containing .cube files (used if name given).

    Returns:
        Loaded LUT3D instance.
    """
    # Determine path
    if os.path.isfile(name_or_path):
        path = name_or_path
        key = path
    else:
        path = os.path.join(lut_dir, name_or_path + ".cube")
        key = f"{lut_dir}/{name_or_path}"

    if key in LUT_CACHE:
        return LUT_CACHE[key]

    lut = LUT3D()
    lut.load(path)
    LUT_CACHE[key] = lut
    return lut


def scan_luts(lut_dir: str) -> list[str]:
    """Scan a directory for .cube files.

    Returns:
        Sorted list of LUT names (without .cube extension).
    """
    if not os.path.isdir(lut_dir):
        return []
    return sorted([
        f.replace('.cube', '') for f in os.listdir(lut_dir)
        if f.endswith('.cube')
    ])


def clear_lut_cache() -> None:
    """Clear the LUT cache."""
    LUT_CACHE.clear()
