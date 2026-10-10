import os
import struct
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from compilegfx import extract
from compilegfx.codec import pc98lz
from compilegfx.container import gcs14, palette, tilesheet

PLANE = 80 * 100


def _write(tmp_path, name, data):
    path = tmp_path / name
    path.write_bytes(data)
    return path


def _by_source(root):
    return {r.source: r for r in extract.scan(str(root))}


def _screen_streams(fill=0x55):
    return b"".join(pc98lz.compress(bytes([fill]) * PLANE) for _ in range(4))


def _menu_dat(name, pal_bytes):
    body_at = palette.TABLE_OFFSET + 4 * 2
    name_z = name + b"\x00"
    slots = [body_at, body_at + len(name_z), body_at + len(name_z) + 1, 0]
    return b"DiscStation#10\x82P" + struct.pack("<4H", *slots) + name_z + b"\x01" + pal_bytes


def test_screen_takes_its_palette_from_a_sibling_menu_dat(tmp_path):
    pal = bytes(i % 16 for i in range(48))
    _write(tmp_path, "MENU.DAT", _menu_dat(b"TEST.CNS", pal))
    _write(tmp_path, "TEST.CNS", _screen_streams())
    got = _by_source(tmp_path)["TEST.CNS"]
    assert got.status == extract.OK
    assert got.palette == extract.PAL_TABLE
    assert (got.image.width, got.image.height) == (640, 100)
    assert list(got.image.rgb_palette) == palette.rgb444(pal)


def test_without_any_palette_source_the_default_is_marked_as_a_guess(tmp_path):
    _write(tmp_path, "LONE.CNS", _screen_streams())
    got = _by_source(tmp_path)["LONE.CNS"]
    assert got.palette == extract.PAL_DEFAULT
    assert got.palette in extract.GUESSED


def test_tile_sheet_is_found_by_content_whatever_the_name(tmp_path):
    _write(tmp_path, "ANYTHING.BIN", pc98lz.compress(bytes([0x3C]) * (tilesheet.TILE_BYTES * 16)))
    got = _by_source(tmp_path)["ANYTHING.BIN"]
    assert got.status == extract.OK
    assert got.kind.startswith("타일시트")


def test_four_plane_files_merge_into_one_screen(tmp_path):
    for digit in "0123":
        _write(tmp_path, f"TITLE{digit}.DAT", pc98lz.compress(bytes([int(digit)]) * PLANE))
    results = _by_source(tmp_path)
    assert set(results) == {"TITLE.DAT"}
    assert "TITLE0.DAT" in results["TITLE.DAT"].note


def test_map_grid_is_skipped_not_drawn(tmp_path):
    grid = struct.pack("<HH", 4, 2) + bytes(3 * 4 * 2)
    _write(tmp_path, "MAP.DAT", pc98lz.compress(grid))
    assert _by_source(tmp_path)["MAP.DAT"].status == extract.SKIPPED


def test_gcs14_placeholder_header_palette_is_not_trusted(tmp_path):
    header = gcs14.MAGIC + bytes(8) + bytes(c // 17 for rgb in extract.PC98_DEFAULT_8 for c in rgb)
    planes = b""
    for _ in range(4):
        left = gcs14.PLANE_BYTES
        while left:
            take = min(left, 0x1FF)
            planes += bytes(((take >> 8), take & 0xFF))
            left -= take
    _write(tmp_path, "SCREEN.DAT", header + planes)
    got = _by_source(tmp_path)["SCREEN.DAT"]
    assert got.status == extract.OK
    assert got.palette in extract.GUESSED


def test_foreign_and_unknown_files_are_reported(tmp_path):
    _write(tmp_path, "MOVIE.AVI", b"RIFF" + bytes(64))
    _write(tmp_path, "NOISE.BIN", bytes(range(1, 200)))
    results = _by_source(tmp_path)
    assert results["MOVIE.AVI"].status == extract.SKIPPED
    assert results["NOISE.BIN"].status == extract.UNKNOWN


def test_save_keeps_colliding_stems_apart(tmp_path):
    _write(tmp_path, "PIC.CNS", _screen_streams(1))
    _write(tmp_path, "PIC.DAT", _screen_streams(2))
    taken = set()
    outs = [extract.save(r, str(tmp_path / "out"), taken) for r in extract.scan(str(tmp_path))
            if r.status == extract.OK]
    assert len(set(outs)) == len(outs) == 2


def test_four_consecutive_plane_chunks_merge_into_one_screen(tmp_path):
    chunks = [pc98lz.compress(bytes([0x0F]) * extract.SCREEN_PLANE_BYTES) for _ in range(4)]
    table = bytearray(0x400)
    at = 0x400
    for i, chunk in enumerate(chunks + [b""]):
        struct.pack_into("<HH", table, i * 4, at >> 16, at & 0xFFFF)
        at += len(chunk)
    _write(tmp_path, "DISK_C.DAT", bytes(table) + b"".join(chunks))
    results = _by_source(tmp_path)
    assert list(results) == ["DISK_C.DAT/c00-c03"]
    assert (results["DISK_C.DAT/c00-c03"].image.width, results["DISK_C.DAT/c00-c03"].image.height) == (640, 400)
