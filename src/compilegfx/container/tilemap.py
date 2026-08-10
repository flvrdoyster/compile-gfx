"""Tile-map grids that ship alongside images in the same archives.

幻世水滸伝's GENSE.FLD stores map and battlefield layouts under the same
`.cns` extension as its pictures -- 200 of 377 entries are these, not
images. They are layout data referencing a tile sheet, so there is nothing
to render here without the sheet and its mapping.

    [u16 width][u16 height][u16 tiles[w*h]][u16 attrs[w*h]]

Two same-sized grids follow the header; the first indexes tiles, the second
carries per-cell attributes. 199 of the 200 GENSE.FLD entries match that
size relation exactly.

This module exists mostly so nothing mistakes one for a picture. A tile map
opens with its width where `header8` expects two bytes it ignores, and the
values that follow land in `header8`'s valid ranges often enough to parse
as a plausible image -- yielding pure noise, with no error raised. Both
mkjpg's cns110.exe and a JS extractor written against it shipped BMPs of
that noise. `looks_like_tilemap()` is what keeps `detect.load()` from
doing the same.
"""
import struct

HEADER_BYTES = 4


def looks_like_tilemap(data: bytes) -> bool:
    """True when `data`'s size matches its own declared grid exactly.

    The size relation is the whole test: two u16 grids of w*h after a
    4-byte header leaves no slack, so a picture is very unlikely to
    satisfy it by chance.
    """
    if len(data) < HEADER_BYTES:
        return False
    width, height = struct.unpack_from("<HH", data, 0)
    if width <= 0 or height <= 0:
        return False
    return len(data) == HEADER_BYTES + 4 * width * height


def parse(data: bytes):
    """(width, height, tiles, attrs) -- the two grids as lists of ints."""
    if not looks_like_tilemap(data):
        raise ValueError("not a tile map: size doesn't match its declared grid")
    width, height = struct.unpack_from("<HH", data, 0)
    cells = width * height
    grids = struct.unpack_from(f"<{cells * 2}H", data, HEADER_BYTES)
    return width, height, list(grids[:cells]), list(grids[cells:])
