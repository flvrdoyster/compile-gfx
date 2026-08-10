"""PC-98 RLE, the second codec in Disc Station vol.10's MENU.COM (sub_1D60).

The extension table there maps CND -> 0x0F: bit 7 clear selects this codec,
the low nibble is the plane mask. No .CND files ship on vol.10 itself, so
this is reversed-but-unexercised -- treat it as untested against real data.

    b = *src++
    b == 0    -> end
    count = b & 0x7F
    b & 0x80  -> repeat the next byte `count` times
    else      -> copy `count` literal bytes
"""


def decompress_stream(data: bytes, start: int = 0):
    out = bytearray()
    i = start
    n = len(data)
    while i < n:
        b = data[i]
        i += 1
        if b == 0:
            break
        count = b & 0x7F
        if b & 0x80:
            if i >= n:
                break
            out += bytes([data[i]]) * count
            i += 1
        else:
            out += data[i:i + count]
            i += count
    return bytes(out), i


def decompress(data: bytes, start: int = 0) -> bytes:
    return decompress_stream(data, start)[0]
