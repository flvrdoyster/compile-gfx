"""Shared primitives for the Compile codecs."""


def copy_back(out: bytearray, dist: int, length: int) -> None:
    """Emit an LZ back-reference, one byte at a time so overlap works.

    A reference reaching before the start of the buffer reads as zero. Every
    original decoder does this rather than treating it as an error, and at
    least one real file relies on it -- do not "fix" it into a raise.
    """
    start = len(out) - dist
    for k in range(length):
        pos = start + k
        out.append(out[pos] if pos >= 0 else 0)
