"""Pick a decoder by content, never by extension.

Six Windows-era extensions map onto just two codecs and two payload headers,
and the same extension means different things on different discs (.CNS is a
Windows LZ image on vol.12/14/20 but a DOS planar one on vol.10). Sniffing
the bytes is the only thing that holds up.

Note this handles the **Windows** lineage. vol.10's DOS/PC-98 files carry no
magic at all and need an external palette, so they go through the planar and
palette modules explicitly rather than being guessed at here.
"""
from .codec import cnx, gcn
from .container import gmp200, header8
from .image import Bitmap


class NotAnImage(Exception):
    """A graphics extension wrapping something else entirely.

    Both known cases are on vol.20 and are worth keeping rather than fixing:
    a plain Shift-JIS staff note (kaihatu.cns) and a nazopuyo puzzle data
    file (nazopuyo.cnx).
    """


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
    if cnx.is_cnx(raw):
        return gmp200.parse(cnx.decompress(raw))
    if gmp200.is_gmp200(raw):
        return gmp200.parse(raw)             # .GMP: payload stored raw
    if looks_like_sjis_text(raw):
        raise NotAnImage("plain Shift-JIS text despite the extension")
    if path_hint.lower().endswith(".cnx"):
        raise NotAnImage(f".cnx without CNX magic (starts {raw[:8]!r})")

    dec = gcn.decompress(raw)
    return gmp200.parse(dec) if gmp200.is_gmp200(dec) else header8.parse(dec)
