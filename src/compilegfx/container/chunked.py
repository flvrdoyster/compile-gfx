import struct

TABLE_BYTES = 0x400
ENTRY_BYTES = 4


def chunk_offsets(data: bytes):
    seeks = []
    for off in range(0, TABLE_BYTES, ENTRY_BYTES):
        cx, dx = struct.unpack_from("<HH", data, off)
        seek = (cx << 16) | dx
        if seek:
            seeks.append(seek)
    seeks = sorted(set(seeks))
    if not seeks or seeks[-1] < len(data):
        seeks.append(len(data))
    return seeks


def chunk_bytes(data: bytes, index: int) -> bytes:
    offsets = chunk_offsets(data)
    return data[offsets[index]:offsets[index + 1]]


def iter_chunks(data: bytes):
    offsets = chunk_offsets(data)
    for i in range(len(offsets) - 1):
        yield i, data[offsets[i]:offsets[i + 1]]
