"""Container tests that need no game data."""
import os
import struct
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from compilegfx.container import chunked, palette, tilesheet

DECOY = bytes([0x0F] * palette.PALETTE_BYTES)                     # all white
REAL = bytes(b for i in range(16) for b in (i, i, i))             # a ramp


def _menu_dat():
    """A MENU.DAT shaped like vol.8 disc 3.

    The decoy palette sits immediately after the flag byte -- where a
    reader that trusts adjacency would find it -- while the table points
    the filename at the palette the menu actually draws with.
    """
    song, name, flag = b"SONG.DAT\x00", b"TEST.CNS\x00", b"\x01"
    body_at = palette.TABLE_OFFSET + 6 * 2

    off_song = body_at
    off_name = off_song + len(song)
    off_flag = off_name + len(name)
    off_decoy = off_flag + len(flag)
    off_real = off_decoy + len(DECOY)

    slots = [off_song, off_decoy, off_name, off_flag, off_real, 0]
    return (b"DiscStation#08\x82R"
            + struct.pack("<6H", *slots)
            + song + name + flag + DECOY + REAL)


def test_menu_dat_pairs_name_to_palette_through_the_table():
    got = palette.read_menu_dat(_menu_dat())
    assert got == {"TEST.CNS": palette.rgb444(REAL)}
    assert got["TEST.CNS"] != palette.rgb444(DECOY), "took the adjacent palette"


def test_slot_table_length_is_self_describing():
    # the first entry points just past the last one
    assert len(palette.slot_table(_menu_dat())) == 6


def test_slot_table_rejects_other_files():
    assert palette.slot_table(b"\x00" * 64) == []
    assert palette.read_menu_dat(b"junk" + b"TEST.CNS\x00" + DECOY) == {}


def test_menu_com_record_has_no_flag_byte():
    # MENU.DAT puts a flag between the name and the palette; MENU.COM does not
    assert palette.read_menu_com(b"AAA.CNS\x00" + REAL) == {"AAA.CNS": palette.rgb444(REAL)}


def test_menu_com_name_stops_at_non_filename_bytes():
    # vol.10 butts Shift-JIS help text against the name, ending in '@$'
    blob = "…ます@$".encode("cp932") + b"AAA.CNS\x00" + REAL
    assert list(palette.read_menu_com(blob)) == ["AAA.CNS"]


def test_menu_com_ignores_a_name_without_a_palette():
    assert palette.read_menu_com(b"AAA.CNS\x00" + b"\xff" * 48) == {}


def test_rgb444_scales_nibbles_to_bytes():
    assert palette.rgb444(bytes([0x0F, 0x00, 0x08]), count=1) == [(255, 0, 136)]


# ── script-embedded palette stream (幻世 series in-game engine) ──────────────

def test_script_stream_registers_need_not_be_sequential():
    # 幻世快盗伝's title screen sets only registers 0, 1, 3 -- not 0..15
    blob = bytes([0, 4, 0, 0, 1, 9, 10, 3, 3, 15, 15, 15, 0xFF])
    assert palette.read_script_stream(blob, 0) == {
        0: (68, 0, 0), 1: (153, 170, 51), 3: (255, 255, 255),
    }


def test_script_stream_requires_a_terminator():
    # runs off the end without hitting 0xFF -- not a valid stream
    assert palette.read_script_stream(bytes([0, 1, 1, 1]), 0) == {}


def test_script_stream_rejects_bad_register_or_channel():
    assert palette.read_script_stream(bytes([16, 0, 0, 0, 0xFF]), 0) == {}   # register > 15
    assert palette.read_script_stream(bytes([0, 0x10, 0, 0, 0xFF]), 0) == {}  # channel > 0x0F


def test_find_script_palettes_locates_runs_amid_junk():
    run = bytes([0, 4, 0, 0, 1, 9, 10, 3, 3, 15, 15, 15, 0xFF])
    blob = b"\x99\x99\x99\x99\x99" + run + b"\x99\x99\x99"  # >0x0F: not nibble-shaped
    found = palette.find_script_palettes(blob, min_entries=2)
    assert found == [(5, {0: (68, 0, 0), 1: (153, 170, 51), 3: (255, 255, 255)})]


def test_find_script_palettes_respects_min_entries():
    run = bytes([0, 4, 0, 0, 1, 9, 10, 3, 0xFF])  # 2 entries
    assert palette.find_script_palettes(run, min_entries=2) == [
        (0, {0: (68, 0, 0), 1: (153, 170, 51)})
    ]
    assert palette.find_script_palettes(run, min_entries=3) == []


# ── chunked containers (幻世 series DISK_B.DAT / DISK_C.DAT) ─────────────────

def _chunked_file(*parts):
    table = bytearray(chunked.TABLE_BYTES)
    pos = chunked.TABLE_BYTES
    for i, part in enumerate(parts):
        struct.pack_into("<HH", table, i * 4, pos >> 16, pos & 0xFFFF)
        pos += len(part)
    return bytes(table) + b"".join(parts)


def test_chunk_offsets_resolve_table_entries():
    data = _chunked_file(b"AAA", b"BBBBB")
    offs = chunked.chunk_offsets(data)
    assert offs == [chunked.TABLE_BYTES, chunked.TABLE_BYTES + 3, len(data)]


def test_chunk_bytes_slices_between_offsets():
    data = _chunked_file(b"AAA", b"BBBBB")
    assert chunked.chunk_bytes(data, 0) == b"AAA"
    assert chunked.chunk_bytes(data, 1) == b"BBBBB"


def test_iter_chunks_yields_index_and_bytes_in_order():
    data = _chunked_file(b"AAA", b"BBBBB")
    assert list(chunked.iter_chunks(data)) == [(0, b"AAA"), (1, b"BBBBB")]


def test_chunk_offsets_ignores_zero_slots():
    # a file with one real chunk still has 255 unused zero entries in the table
    data = _chunked_file(b"solo")
    assert chunked.chunk_offsets(data) == [chunked.TABLE_BYTES, len(data)]


# ── tile sheets (幻世 series DISK_C.DAT sprite/tile graphics) ────────────────

TILE_PAL = [(0, 0, 0)] * 16
TILE_PAL[5] = (255, 34, 17)


def _one_tile(opaque_bits=0xFFFF, idx=5):
    """One 160-byte tile: `opaque_bits` masks which columns of every row are
    opaque, all opaque pixels carrying palette index `idx`."""
    planes = [opaque_bits if p == 0 else (opaque_bits if idx & (1 << (p - 1)) else 0)
              for p in range(5)]
    tile = bytearray(tilesheet.TILE_BYTES)
    for p, word in enumerate(planes):
        for row in range(16):
            struct.pack_into(">H", tile, p * 32 + row * 2, word)
    return bytes(tile)


def test_tilesheet_decode_applies_palette_to_opaque_pixels():
    img = tilesheet.decode(_one_tile(), TILE_PAL, cols=1)
    assert img.size == (16, 16)
    assert img.getpixel((0, 0)) == (255, 34, 17, 255)


def test_tilesheet_decode_plane0_is_a_transparency_mask():
    # only the leftmost pixel (MSB) opaque; the rest stay (0,0,0,0)
    img = tilesheet.decode(_one_tile(opaque_bits=0x8000), TILE_PAL, cols=1)
    assert img.getpixel((0, 0)) == (255, 34, 17, 255)
    assert img.getpixel((1, 0)) == (0, 0, 0, 0)


def test_tilesheet_decode_rejects_partial_tiles():
    try:
        tilesheet.decode(b"\x00" * (tilesheet.TILE_BYTES - 1), TILE_PAL)
        assert False, "expected ValueError"
    except ValueError:
        pass
