import struct
from collections import namedtuple

Layout = namedtuple("Layout", "entry_bytes name_at offset_at size_at")

LAYOUTS = {
    b"FLDF0100": Layout(20, 0, 12, 16),
    b"FLDF0200": Layout(20, 0, 12, 16),
    b"FLDF0300": Layout(24, 12, 4, 8),
}
MAGIC_BYTES = 8
NAME_BYTES = 12
V1_TABLE_AT = 12


def is_fld(data: bytes) -> bool:
    return data[:MAGIC_BYTES] in LAYOUTS


def _table(data: bytes):
    magic = data[:MAGIC_BYTES]
    if magic not in LAYOUTS:
        raise ValueError(f"not an FLD archive (magic {magic!r})")
    if magic == b"FLDF0100":
        start, count = V1_TABLE_AT, struct.unpack_from("<I", data, MAGIC_BYTES)[0]
    else:
        start, count = struct.unpack_from("<II", data, MAGIC_BYTES)
    layout = LAYOUTS[magic]
    if start + count * layout.entry_bytes > len(data):
        raise ValueError(f"{count} entries at {start:#x} overrun a {len(data)}-byte file")
    return layout, start, count


def entries(data: bytes):
    layout, start, count = _table(data)
    out = []
    for i in range(count):
        at = start + i * layout.entry_bytes
        raw = data[at + layout.name_at:at + layout.name_at + NAME_BYTES]
        name = raw.split(b"\x00", 1)[0].decode("ascii", "replace")
        offset = struct.unpack_from("<I", data, at + layout.offset_at)[0]
        size = struct.unpack_from("<I", data, at + layout.size_at)[0]
        out.append((name, offset, size))
    return out


def read(data: bytes, name: str) -> bytes:
    wanted = name.lower()
    for entry_name, offset, size in entries(data):
        if entry_name.lower() == wanted:
            return data[offset:offset + size]
    raise KeyError(f"{name} not in archive")


def iter_members(data: bytes):
    for name, offset, size in entries(data):
        yield name, data[offset:offset + size]
