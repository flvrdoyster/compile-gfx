"""Container tests that need no game data."""
import os
import struct
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from compilegfx.container import palette

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
