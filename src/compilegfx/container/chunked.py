"""Chunk-table containers used by the 幻世 (Gensei) series engine's DAT files.

`DISK_B.DAT` / `DISK_C.DAT` and similarly-shaped files across the shared
engine (幻世快盗伝, 幻世快盗伝, 幻世喜譚, 幻世風狂伝) start with a 0x400-byte
table of u16-pair offsets -- `(cx << 16) | dx`, both little-endian -- one
per chunk. Zero entries are unused slots. There is no explicit chunk count
or end marker; callers take `len(data)` as the boundary past the last real
chunk.

Each chunk is a `codec.pc98lz` stream. This module only resolves offsets
and slices bytes; decompression is the caller's job.
"""
import struct

TABLE_BYTES = 0x400
ENTRY_BYTES = 4


def chunk_offsets(data: bytes):
    """Every non-zero seek in the table, ascending, plus EOF as the last entry.

    The trailing EOF entry is a boundary marker, not a real chunk -- a file
    with N chunks returns N+1 offsets.
    """
    seeks = []
    for off in range(0, TABLE_BYTES, ENTRY_BYTES):
        cx, dx = struct.unpack_from("<HH", data, off)
        seek = (cx << 16) | dx
        if seek:
            seeks.append(seek)
    seeks = sorted(set(seeks))
    seeks.append(len(data))
    return seeks


def chunk_bytes(data: bytes, index: int) -> bytes:
    """Compressed bytes for chunk `index` -- feed to `codec.pc98lz.decompress`."""
    offsets = chunk_offsets(data)
    return data[offsets[index]:offsets[index + 1]]


def iter_chunks(data: bytes):
    """(index, compressed_bytes) for every chunk, in table order."""
    offsets = chunk_offsets(data)
    for i in range(len(offsets) - 1):
        yield i, data[offsets[i]:offsets[i + 1]]
