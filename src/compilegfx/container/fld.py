"""FLD archives -- 幻世水滸伝 keeps its whole graphics set in one GENSE.FLD.

    "FLDF0100", u32 entry count,
    then per entry: 12-byte NUL-padded name, u32 offset, u32 size

Offsets are absolute, and the payloads start right where the table ends and
run back to back with no gaps. Each payload is an ordinary member file --
usually a `codec.gcn` stream, so `detect.load()` takes one straight from
`read()`.

Read-only on purpose: rewriting an archive means re-packing every offset
behind the entry you changed, which is reinsertion policy each patch
project already owns.
"""
import struct

MAGIC = b"FLDF0100"
HEADER_BYTES = 12
ENTRY_BYTES = 20
NAME_BYTES = 12


def is_fld(data: bytes) -> bool:
    return data[:len(MAGIC)] == MAGIC


def entries(data: bytes):
    """[(name, offset, size)] in table order."""
    if not is_fld(data):
        raise ValueError(f"not an FLD archive (magic {data[:8]!r})")
    count = struct.unpack_from("<I", data, len(MAGIC))[0]
    out = []
    for i in range(count):
        at = HEADER_BYTES + i * ENTRY_BYTES
        raw = data[at:at + NAME_BYTES]
        name = raw.split(b"\x00", 1)[0].decode("ascii", "replace")
        offset, size = struct.unpack_from("<II", data, at + NAME_BYTES)
        out.append((name, offset, size))
    return out


def read(data: bytes, name: str) -> bytes:
    """The named member's bytes, matched case-insensitively."""
    wanted = name.lower()
    for entry_name, offset, size in entries(data):
        if entry_name.lower() == wanted:
            return data[offset:offset + size]
    raise KeyError(f"{name} not in archive")


def iter_members(data: bytes):
    """(name, member_bytes) for every entry, in table order."""
    for name, offset, size in entries(data):
        yield name, data[offset:offset + size]
