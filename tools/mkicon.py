#!/usr/bin/env python3
"""Generate a simple gradient icon for lut-ai AppImage."""

import struct
import zlib
import sys


def make_png(path: str, w: int = 256, h: int = 256):
    """Create an orange-purple gradient PNG icon."""
    raw = bytearray()
    for y in range(h):
        raw.append(0)  # filter byte
        for x in range(w):
            cx, cy = w // 2, h // 2
            dx = x - cx
            dy = y - cy
            dist = (dx * dx + dy * dy) ** 0.5
            radius = min(w, h) * 0.42

            if dist <= radius:
                # Gradient: warm orange center -> cool purple edge
                t = dist / radius
                r = int(255 * (1 - t) + 120 * t)
                g = int(150 * (1 - t) + 80 * t)
                b = int(50 * (1 - t) + 200 * t)
                raw.extend((r, g, b, 255))
            elif dist <= radius + 4:
                raw.extend((255, 255, 255, 255))  # thin highlight border
            else:
                raw.extend((0, 0, 0, 0))  # transparent

    def chunk(ctype, data):
        c = ctype + data
        return (struct.pack(">I", len(data)) + c +
                struct.pack(">I", zlib.crc32(c) & 0xffffffff))

    with open(path, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n")
        f.write(chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0)))
        f.write(chunk(b"IDAT", zlib.compress(bytes(raw))))
        f.write(chunk(b"IEND", b""))


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "lut-ai.png"
    make_png(out, 256, 256)
    print(f"Icon created: {out} ({256}x{256})")
