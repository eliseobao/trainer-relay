"""Generate the project's simple relay-arrow icon with only the standard library."""

import math
import struct
import zlib
from pathlib import Path


def image(size):
    def inside(x, y, polygon):
        odd = False
        j = len(polygon) - 1
        for i, (xi, yi) in enumerate(polygon):
            xj, yj = polygon[j]
            if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
                odd = not odd
            j = i
        return odd

    arrows = [
        [(20, 30), (59, 30), (59, 19), (81, 39), (59, 59), (59, 48), (20, 48)],
        [(80, 70), (41, 70), (41, 81), (19, 61), (41, 41), (41, 52), (80, 52)],
    ]
    rows = bytearray()
    for py in range(size):
        rows.append(0)
        for px in range(size):
            x, y = (px + 0.5) * 100 / size, (py + 0.5) * 100 / size
            outside = math.hypot(max(0, abs(x - 50) - 29), max(0, abs(y - 50) - 29)) > 19
            color = (23, 43, 58, 0 if outside else 255)
            if inside(x, y, arrows[0]):
                color = (80, 210, 183, 255)
            if inside(x, y, arrows[1]):
                color = (234, 244, 247, 255)
            rows.extend(color)

    def chunk(kind, data):
        return (
            struct.pack("!I", len(data)) + kind + data + struct.pack("!I", zlib.crc32(kind + data))
        )

    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack("!2I5B", size, size, 8, 6, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(rows))
        + chunk(b"IEND", b"")
    )


def main():
    root = Path(__file__).resolve().parents[1] / "assets"
    root.mkdir(exist_ok=True)
    sizes = [32, 64, 128, 256]
    images = [image(size) for size in sizes]
    offset = 6 + 16 * len(sizes)
    header = struct.pack("<3H", 0, 1, len(sizes))
    for size, png in zip(sizes, images):
        header += struct.pack("<4B2H2I", size % 256, size % 256, 0, 0, 1, 32, len(png), offset)
        offset += len(png)
    (root / "app.ico").write_bytes(header + b"".join(images))
    (root / "app.png").write_bytes(images[1])


if __name__ == "__main__":
    main()
