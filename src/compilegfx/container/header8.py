"""The older 8-byte payload header (.GCN / .CNS / .CNU and some .DAT).

    [2B zero][u16 width][u16 height][u16 palCount - 1][palette][rows]

Those first two bytes are always zero -- all 1471 header8 payloads across
ds12/ds14/ds20 have them, as do 幻世水滸伝's. Treating them as "unknown and
therefore ignorable" is what let tile maps through: those open with their
width, and the fields that land in width/height/palCount are plausible
often enough to parse as an image made of noise. See `container.tilemap`.

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


def looks_like_header8(dec: bytes) -> bool:
    """Cheap gate before parse(): the two leading zeros and sane fields."""
    if len(dec) < 8 or dec[0:2] != b"\x00\x00":
        return False
    width, height = struct.unpack_from("<HH", dec, 2)
    pal_count = struct.unpack_from("<H", dec, 6)[0] + 1
    return width > 0 and height > 0 and 1 <= pal_count <= 256


def parse(dec: bytes) -> Bitmap:
    if len(dec) < 8:
        raise ValueError(f"too short for an 8-byte header ({len(dec)} bytes)")
    if dec[0:2] != b"\x00\x00":
        raise ValueError(f"header does not start with two zero bytes ({dec[0:2]!r})")
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
