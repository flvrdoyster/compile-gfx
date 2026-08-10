"""Container tests that need no game data."""
import os
import struct
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from compilegfx.container import chunked, fld, header8, palette, tilemap, tilesheet

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


def test_find_script_palettes_reports_a_run_once():
    # a run whose registers repeat has more records than distinct entries;
    # resuming by the distinct count lands back inside it and re-reports
    # the tail as a second palette
    run = bytes([0, 1, 1, 1, 1, 2, 2, 2, 0, 3, 3, 3, 1, 4, 4, 4, 0xFF])
    found = palette.find_script_palettes(run, min_entries=2)
    assert [off for off, _ in found] == [0]
    assert found[0][1] == {0: (51, 51, 51), 1: (68, 68, 68)}, "last write wins"


def test_find_script_palettes_needs_the_terminator_to_close_the_span():
    # nibbles running straight into non-nibble data are not a run
    assert palette.find_script_palettes(bytes([0, 1, 1, 1]) + b"\x99", min_entries=1) == []


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


def test_tilesheet_default_palette_is_a_full_16_colour_table():
    assert len(tilesheet.DEFAULT_PALETTE) == 16
    assert all(len(c) == 3 and all(0 <= v <= 255 for v in c)
               for c in tilesheet.DEFAULT_PALETTE)
    # decode() falls back to it, so a caller with no palette still works
    img = tilesheet.decode(_one_tile(idx=15), cols=1)
    assert img.getpixel((0, 0)) == tilesheet.DEFAULT_PALETTE[15] + (255,)


def test_tilesheet_decode_rejects_partial_tiles():
    try:
        tilesheet.decode(b"\x00" * (tilesheet.TILE_BYTES - 1), TILE_PAL)
        assert False, "expected ValueError"
    except ValueError:
        pass


# ── tile maps vs images (幻世水滸伝 ships both as .cns) ──────────────────────

def _tilemap(width=3, height=2):
    cells = width * height
    return struct.pack(f"<HH{cells * 2}H", width, height, *range(cells * 2))


def _header8_image(width=4, height=2, colours=2):
    """A minimal valid header8 payload: two zero bytes, then the fields."""
    body = struct.pack("<HHH", width, height, colours - 1)
    return b"\x00\x00" + body + b"\x00" * (colours * 4) + b"\x00" * (width * height)


def test_tilemap_is_recognised_by_its_exact_size():
    assert tilemap.looks_like_tilemap(_tilemap())
    assert not tilemap.looks_like_tilemap(_tilemap() + b"\x00")   # one byte over


def test_tilemap_parse_splits_the_two_grids():
    width, height, tiles, attrs = tilemap.parse(_tilemap(3, 2))
    assert (width, height) == (3, 2)
    assert tiles == [0, 1, 2, 3, 4, 5]
    assert attrs == [6, 7, 8, 9, 10, 11]


def test_header8_requires_its_two_leading_zeros():
    # a tile map opens with its width, which header8 used to read straight
    # past -- parsing the grid as an image made of noise
    assert header8.looks_like_header8(_header8_image())
    assert not header8.looks_like_header8(_tilemap(21, 17))
    try:
        header8.parse(_tilemap(21, 17))
        assert False, "expected ValueError"
    except ValueError:
        pass


# ── FLD archives (幻世水滸伝's GENSE.FLD) ────────────────────────────────────

def _fld(*members):
    table = b""
    body = b""
    offset = fld.HEADER_BYTES + len(members) * fld.ENTRY_BYTES
    for name, payload in members:
        table += name.encode("ascii").ljust(fld.NAME_BYTES, b"\x00")
        table += struct.pack("<II", offset + len(body), len(payload))
        body += payload
    return fld.MAGIC + struct.pack("<I", len(members)) + table + body


def test_fld_entries_and_read():
    blob = _fld(("a.cns", b"AAA"), ("b.cns", b"BBBB"))
    assert [(n, s) for n, _, s in fld.entries(blob)] == [("a.cns", 3), ("b.cns", 4)]
    assert fld.read(blob, "a.cns") == b"AAA"
    assert fld.read(blob, "B.CNS") == b"BBBB", "names match case-insensitively"


def test_fld_iter_members_keeps_table_order():
    blob = _fld(("a.cns", b"AAA"), ("b.cns", b"BBBB"))
    assert list(fld.iter_members(blob)) == [("a.cns", b"AAA"), ("b.cns", b"BBBB")]


def test_fld_rejects_other_files():
    try:
        fld.entries(b"NOTANFLD" + b"\x00" * 16)
        assert False, "expected ValueError"
    except ValueError:
        pass
