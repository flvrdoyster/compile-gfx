"""Windows-era Compile LZ token stream (.GCN / .CNS / .CNU / .GCS).

Verified twice over: disassembled from Disc Station vol.14's DSMENU.EXE at
`sub_419000`, and independently derived by the suiko project from
`cns110.exe` at 0x401820. The two agree.

One opcode byte per token; `0x00` ends the stream. The top bit and high
nibble pick the shape:

  0x80-0xFF  copy (b >> 4) & 7 literals, then a match of len (b & 0xF) + 2
             with a 1-byte distance read *after* the literals
  0x00-0x0F  match, len = (b & 0xF) + 2, 1-byte distance
  0x10-0x1F  match, len = (b & 0xF) + 2, 2-byte LE distance
  0x20-0x2F  match, len = ((b & 0xF) << 8) | next, 1-byte distance
  0x30-0x3F  match, len = ((b & 0xF) << 8) | next, 2-byte LE distance
  0x40-0x5F  literal run of b & 0x1F bytes
  0x60-0x7F  literal run of ((b & 0x1F) << 8) | next bytes
"""
from .common import copy_back


def decompress(src: bytes, start: int = 0) -> bytes:
    out = bytearray()
    i = start
    n = len(src)
    while i < n:
        b = src[i]
        i += 1
        if b == 0:
            break

        if b >= 0x80:
            for _ in range((b >> 4) & 0x7):
                out.append(src[i])
                i += 1
            dist = src[i]
            i += 1
            copy_back(out, dist, (b & 0xF) + 2)
            continue

        hi, lo = b & 0xF0, b & 0x0F
        if hi in (0x00, 0x10, 0x20, 0x30):
            if hi in (0x00, 0x10):
                length = lo + 2
            else:
                length = (lo << 8) | src[i]
                i += 1
            if hi in (0x00, 0x20):
                dist = src[i]
                i += 1
            else:
                dist = src[i] | (src[i + 1] << 8)
                i += 2
            copy_back(out, dist, length)
        elif hi in (0x40, 0x50, 0x60, 0x70):
            count = b & 0x1F
            if hi in (0x60, 0x70):
                count = (count << 8) | src[i]
                i += 1
            out += src[i:i + count]
            i += count
        else:  # unreachable: every byte < 0x80 is covered above
            raise ValueError(f"unhandled opcode {b:#x} at src[{i - 1}]")
    return bytes(out)


def consumed(src: bytes, start: int = 0) -> int:
    """Index just past the terminator -- how many bytes a decode eats.

    Reinsertion needs this: at least one loader advances its read cursor by
    bytes consumed rather than seeking per directory entry, so a replacement
    stream must consume exactly as many bytes as the original.
    """
    i = start
    n = len(src)
    while i < n:
        b = src[i]
        i += 1
        if b == 0:
            return i
        if b >= 0x80:
            i += ((b >> 4) & 0x7) + 1
        elif b >= 0x60:
            i += 1 + (((b & 0x1F) << 8) | src[i])
        elif b >= 0x40:
            i += b & 0x1F
        elif b >= 0x30:
            i += 3
        elif b >= 0x20:
            i += 2
        elif b >= 0x10:
            i += 2
        else:
            i += 1
    return i
