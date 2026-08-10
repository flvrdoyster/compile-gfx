"""Compile's PC-98 LZ (DOS-era: Disc Station vol.10, 幻世 PC-98 titles).

Confirmed against Disc Station vol.10's MENU.COM at sub_1D98, and shared
with the gensei-pc98 patch tools. Much simpler than the Windows codec:

    al = *src++
    al == 0    -> end of stream
    al & 0x80  -> match, length = (al & 0x7F) + 3, distance = *src++ + 1
    else       -> literal run of `al` bytes

A file usually holds several streams back to back; use `streams()` to walk
them. In MENU.COM the extension table maps CNS -> 0x8F, where bit 7 selects
this codec and the low nibble is a plane mask.
"""
from .common import copy_back


def decompress_stream(data: bytes, start: int = 0):
    """One stream. Returns (output, index just past its terminator)."""
    out = bytearray()
    i = start
    n = len(data)
    while i < n:
        al = data[i]
        i += 1
        if al == 0:
            break
        if al & 0x80:
            length = (al & 0x7F) + 3
            if i >= n:
                break
            dist = data[i] + 1
            i += 1
            copy_back(out, dist, length)
        else:
            out += data[i:i + al]
            i += al
    return bytes(out), i


def streams(data: bytes, start: int = 0, limit: int = 64):
    """Every stream in the file, in order. Returns (parts, end index).

    A correct decode consumes the file exactly -- leftover bytes or an
    overrun means the layout assumption is wrong, so callers should check.
    """
    parts = []
    i = start
    while i < len(data) and len(parts) < limit:
        out, i = decompress_stream(data, i)
        if not out:
            break
        parts.append(out)
    return parts, i


def decompress(data: bytes, start: int = 0, limit: int = 64) -> bytes:
    parts, _ = streams(data, start, limit)
    return b"".join(parts)


def _longest_match(data: bytes, i: int, max_dist: int = 256, max_len: int = 130):
    best_len = best_dist = 0
    hi = min(i, max_dist)
    cap = min(len(data) - i, max_len)
    for dist in range(1, hi + 1):
        ml = 0
        base = i - dist
        while ml < cap and data[i + ml] == data[base + (ml % dist)]:
            ml += 1
        if ml > best_len:
            best_len, best_dist = ml, dist
            if best_len == cap:
                break
    return best_len, best_dist


def compress(data: bytes) -> bytes:
    """Cost-optimal (DP) encoder -- the exact inverse of decompress_stream.

    Window 256 bytes, match length 3..130, literal runs 1..127. Kept here
    rather than in a patch project so the encoder can never drift from the
    decoder above; reinsertion *policy* (fitting an exact byte budget,
    rebuilding archives) stays with each project.
    """
    n = len(data)
    if n == 0:
        return b"\x00"

    INF = float("inf")
    dp = [INF] * (n + 1)
    dp[n] = 0
    choice = [None] * n

    for i in range(n - 1, -1, -1):
        for L in range(1, min(127, n - i) + 1):
            cost = 1 + L + dp[i + L]
            if cost < dp[i]:
                dp[i] = cost
                choice[i] = ("lit", L, 0)
        ml, dist = _longest_match(data, i)
        for k in range(3, ml + 1):
            cost = 2 + dp[i + k]
            if cost < dp[i]:
                dp[i] = cost
                choice[i] = ("match", k, dist)

    out = bytearray()
    i = 0
    while i < n:
        kind, k, dist = choice[i]
        if kind == "lit":
            out.append(k)
            out += data[i:i + k]
        else:
            out.append(0x80 | (k - 3))
            out.append(dist - 1)
        i += k
    out.append(0x00)
    return bytes(out)
