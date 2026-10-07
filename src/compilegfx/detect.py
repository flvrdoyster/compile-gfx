from .codec import cnx, gcn
from .container import gcs14, gmp200, header8, tilemap
from .image import Bitmap


class NotAnImage(Exception):
    pass


def looks_like_sjis_text(raw: bytes) -> bool:
    head = raw[:64]
    i = 0
    pairs = 0
    while i < len(head) - 1:
        b = head[i]
        if 0x81 <= b <= 0x9F or 0xE0 <= b <= 0xEF:
            if not (0x40 <= head[i + 1] <= 0xFC and head[i + 1] != 0x7F):
                return False
            pairs += 1
            i += 2
        elif b in (0x09, 0x0A, 0x0D) or 0x20 <= b <= 0x7E:
            i += 1
        else:
            return False
    return pairs >= 4


def load(raw: bytes, path_hint: str = "") -> Bitmap:
    if gcs14.is_gcs14(raw):
        return gcs14.parse(raw)
    if cnx.is_cnx(raw):
        return gmp200.parse(cnx.decompress(raw))
    if gmp200.is_gmp200(raw):
        return gmp200.parse(raw)             # .GMP: payload stored raw
    if looks_like_sjis_text(raw):
        raise NotAnImage("plain Shift-JIS text despite the extension")
    if path_hint.lower().endswith(".cnx"):
        raise NotAnImage(f".cnx without CNX magic (starts {raw[:8]!r})")

    dec = gcn.decompress(raw)
    if gmp200.is_gmp200(dec):
        return gmp200.parse(dec)
    if tilemap.looks_like_tilemap(dec):
        raise NotAnImage("tile map grid, not a picture")
    return header8.parse(dec)
