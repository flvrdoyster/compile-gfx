"""Codec tests that need no game data.

The corpus tests in test_corpus.py cover real files; these pin the codec
semantics themselves so a refactor can't quietly change them.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from compilegfx.codec import gcn, pc98lz, pc98rle
from compilegfx.detect import looks_like_sjis_text


def test_pc98lz_roundtrip():
    for data in [b"", b"A", b"AAAAAAAA", b"abcabcabcabc",
                 bytes(range(256)), b"\x00" * 300, os.urandom(1000)]:
        assert pc98lz.decompress(pc98lz.compress(data)) == data, data[:20]


def test_pc98lz_literal_and_match():
    # literal run of 3, then a match of length 3 at distance 1 (run of 'A')
    assert pc98lz.decompress(bytes([3]) + b"ABA" + bytes([0x80, 0]) + b"\x00") == b"ABAAAA"


def test_pc98lz_out_of_range_reads_zero():
    # a match at position 0 has nothing behind it; the original decoders
    # yield zeros rather than erroring, and at least one real file needs it
    assert pc98lz.decompress(bytes([0x80, 0]) + b"\x00") == b"\x00\x00\x00"


def test_gcn_literal_runs():
    assert gcn.decompress(bytes([0x43]) + b"abc" + b"\x00") == b"abc"
    assert gcn.decompress(bytes([0x60, 4]) + b"abcd" + b"\x00") == b"abcd"


def test_gcn_combined_op():
    # 0x80|: copy N literals, then a match read *after* them
    out = gcn.decompress(bytes([0x91]) + b"X" + bytes([1]) + b"\x00")
    assert out == b"XXXX"


def test_gcn_consumed_counts_terminator():
    stream = bytes([0x43]) + b"abc" + b"\x00"
    assert gcn.consumed(stream) == len(stream)


def test_pc98rle():
    assert pc98rle.decompress(bytes([0x83, 0x41]) + b"\x00") == b"AAA"
    assert pc98rle.decompress(bytes([3]) + b"abc" + b"\x00") == b"abc"


def test_sjis_detection():
    assert looks_like_sjis_text("こんなところを見つけて読む人は".encode("cp932"))
    assert not looks_like_sjis_text(bytes([0x4C, 0x00, 0x00, 0x20, 0x02, 0x18]))
