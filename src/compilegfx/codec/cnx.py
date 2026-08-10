"""CNX 2-bit-tag codec (Disc Station vol.20 haiyuki).

Unrelated to the other Compile codecs -- reversed from cnx106.exe (mkjpg,
2005) at sub_4012c0 / sub_4011f0.

File header, 16 bytes, sizes BIG-endian (everything else here is little):
    "CNX" + version, "GMP" + 0x10,
    u32 compressed size (= filesize - 16), u32 decompressed size.

The body is a run of chunks. One control byte packs four 2-bit ops, LSB
first; after four ops the next control byte is read, and a control byte of 0
ends the chunk.

    0  read a length byte, skip that many source bytes (+1), then force a
       control-byte refill -- inter-chunk padding
    1  copy one literal byte
    2  16-bit BE token: dist = ((v & 0xFFE0) >> 5) + 1, len = (v & 0x1F) + 4
    3  read a count byte, copy that many literal bytes
"""
import struct

from .common import copy_back

MAGIC = b"CNX"
HEADER_SIZE = 16


def is_cnx(data: bytes) -> bool:
    return data[:3] == MAGIC


def sizes(data: bytes):
    """(compressed, decompressed) as declared by the header."""
    return struct.unpack_from(">II", data, 8)


def decompress(data: bytes) -> bytes:
    if not is_cnx(data):
        raise ValueError(f"not a CNX file (magic {data[:8]!r})")
    _, dec_size = sizes(data)

    out = bytearray()
    src = HEADER_SIZE
    n = len(data)
    while len(out) < dec_size and src < n:
        tag = data[src]
        src += 1
        if tag == 0:
            break
        done = 0
        while True:
            op = tag & 3
            if op == 0:
                done = 4                      # forces a refill below
                src += data[src] + 1
            elif op == 1:
                out.append(data[src])
                src += 1
            elif op == 2:
                v = (data[src] << 8) | data[src + 1]
                src += 2
                copy_back(out, ((v & 0xFFE0) >> 5) + 1, (v & 0x1F) + 4)
            else:
                count = data[src]
                src += 1
                out += data[src:src + count]
                src += count

            done += 1
            if done < 4:
                tag >>= 2
            else:
                done = 0
                tag = data[src]
                src += 1
                if tag == 0:
                    break
    return bytes(out)
