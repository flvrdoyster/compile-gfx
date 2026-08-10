"""PC-98 planar images (Disc Station vol.10, 幻世 PC-98 titles).

PC-98 video memory is four 1bpp planes at segments A800/B000/B800/E000.
A decoded file is those planes concatenated; the colour index is bit k from
plane k, and the MSB of each byte is the leftmost pixel.

vol.10's MENU.COM encodes, in one byte per file type, both the codec (bit 7)
and a **plane mask** in the low nibble saying which planes are actually
stored -- so four planes is the common case, not a guarantee.

Palettes live outside the image; see palette.py.
"""
from ..image import Bitmap

COMMON_WIDTHS = (640, 512, 384, 320, 256, 192, 128, 96, 64)


def guess_dims(plane_size: int, widths=COMMON_WIDTHS):
    for w in widths:
        if plane_size % (w // 8) == 0:
            h = plane_size // (w // 8)
            if 1 <= h <= 1024:
                return w, h
    return None


def unpack(buf: bytes, width: int, height: int, planes: int = 4) -> bytes:
    """Planar -> one palette index per byte, still bottom-up."""
    stride = width // 8
    plane_size = stride * height
    if len(buf) < plane_size * planes:
        raise ValueError(
            f"{width}x{height} needs {plane_size * planes} bytes for "
            f"{planes} planes, have {len(buf)}"
        )
    P = [buf[p * plane_size:(p + 1) * plane_size] for p in range(planes)]
    flat = bytearray(width * height)
    for y in range(height):
        row = y * stride
        base = y * width
        for xb in range(stride):
            bs = [P[p][row + xb] for p in range(planes)]
            for bit in range(8):
                sh = 7 - bit
                idx = 0
                for p in range(planes):
                    idx |= ((bs[p] >> sh) & 1) << p
                flat[base + xb * 8 + bit] = idx
    return bytes(flat)


def to_bitmap(buf: bytes, rgb_palette, size=None, planes: int = 4) -> Bitmap:
    if len(buf) % planes:
        raise ValueError(f"decoded {len(buf)} bytes, not divisible into {planes} planes")
    plane_size = len(buf) // planes
    dims = size or guess_dims(plane_size)
    if not dims:
        raise ValueError(f"cannot infer dimensions for plane size {plane_size}")
    width, height = dims
    if (width // 8) * height != plane_size:
        raise ValueError(
            f"{width}x{height} needs {(width // 8) * height} per plane, have {plane_size}"
        )
    return Bitmap(
        width=width,
        height=height,
        bpp=8,                       # already unpacked to one index per byte
        row_bytes=width,
        pixels=unpack(buf, width, height, planes),
        rgb_palette=tuple(rgb_palette),
        bottom_up=False,          # PC-98 VRAM starts at the top-left
    )
