"""The "GMP-200" payload (.GCS, .CNX, and .GMP stored raw).

    "GMP-200\\0", u32 height, u32 width, u32 unknown,
    u32 palette offset, u32 pixel offset, u16 palCount, u16 bpp

Note height comes before width, and the fields are u32 -- both unlike the
older 8-byte header. Rows here ARE padded to a 4-byte boundary.

Take the palette size from `pixOffset - palOffset` rather than the u16
count: vol.14's .GMP files store 0 there for a full 256-colour table, and
24bpp files have no palette at all.
"""
import struct

from ..image import Bitmap

MAGIC = b"GMP-200"


def is_gmp200(data: bytes) -> bool:
    return data[:7] == MAGIC


def parse(dec: bytes) -> Bitmap:
    if not is_gmp200(dec):
        raise ValueError(f"unexpected payload magic {dec[:8]!r}")
    height, width = struct.unpack_from("<II", dec, 8)
    pal_off, pix_off = struct.unpack_from("<II", dec, 0x14)
    bpp = struct.unpack_from("<H", dec, 0x1E)[0]
    if width <= 0 or height <= 0:
        raise ValueError(f"bad dims {width}x{height}")
    if bpp not in (4, 8, 24):
        raise ValueError(f"unsupported bpp {bpp}")
    if not 0 <= pal_off <= pix_off <= len(dec):
        raise ValueError(f"bad offsets pal={pal_off:#x} pix={pix_off:#x}")

    return Bitmap(
        width=width,
        height=height,
        bpp=bpp,
        row_bytes=((width * bpp + 31) >> 5) << 2,
        palette=dec[pal_off:pix_off],
        pixels=dec[pix_off:],
    )
