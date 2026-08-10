"""The older 8-byte payload header (.GCN / .CNS / .CNU and some .DAT).

    [2B unknown][u16 width][u16 height][u16 palCount - 1][palette][rows]

The palette count is an explicit field. Do NOT derive it from the file size:
that happens to work for 8bpp images and silently breaks every 4bpp one,
which is how ~105 files were once written off as an unsolvable "multi-frame
container" when they were ordinary 4bpp pictures.

16 colours or fewer means the pixels are 4bpp. Rows are packed tight here --
no BMP-style alignment padding (measured across ds12/ds14/ds20: 133 files
are only consistent with tight rows, none require padding).
"""
import struct

from ..image import Bitmap


def parse(dec: bytes) -> Bitmap:
    width, height = struct.unpack_from("<HH", dec, 2)
    pal_count = struct.unpack_from("<H", dec, 6)[0] + 1
    if width <= 0 or height <= 0:
        raise ValueError(f"bad dims {width}x{height}")
    if not 1 <= pal_count <= 256:
        raise ValueError(f"bad palette count {pal_count}")

    bpp = 4 if pal_count <= 16 else 8
    pix_off = 8 + pal_count * 4
    return Bitmap(
        width=width,
        height=height,
        bpp=bpp,
        row_bytes=(width * bpp + 7) // 8,
        palette=dec[8:pix_off],
        pixels=dec[pix_off:],
    )
