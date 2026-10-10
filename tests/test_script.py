import os
import struct
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from compilegfx.codec import pc98lz
from compilegfx.container import cells
from compilegfx.script import gensei, sp1


def _cell(fill):
    return cells.encode_cell(bytes([fill]) * 256)


def test_cell_round_trip_through_a_sheet():
    data = _cell(3) + cells.encode_cell(bytes(range(16)) * 16) + _cell(15)
    pal = [(i * 17,) * 3 for i in range(16)]
    img = cells.to_image(data, pal, cols=2)
    assert cells.from_image(img, cells.count(data), cols=2) == data
    assert cells.cell_indices(data, 1)[:16] == bytes(range(16))


def _program(script, data):
    code = bytearray(0x400)
    for at, blob in data.items():
        code[at - sp1.BASE:at - sp1.BASE + len(blob)] = blob
    code[0x300 - sp1.BASE:0x300 - sp1.BASE + len(script)] = script
    return sp1.Program(bytes(code), 0, (0x300,))


def _play(script, data, files):
    program = _program(script, data)
    player = sp1.Player(program, 0x300, lambda n: pc98lz.compress(files[n]))
    return player, player.run(max_ticks=50, with_cells=True)


PALETTE = bytes(b for k in range(16) for b in (k, k, 15 - k, 0))
DATA = {0x200: b"A:CELLS.CNS\0", 0x210: b"A:MAP.CNS\0", 0x220: PALETTE}
FILES = {"CELLS.CNS": _cell(5) + _cell(9), "MAP.CNS": struct.pack("<2H", 2, 0x8001)}


def _script(*ops):
    return b"".join(ops) + b"\x31"


LOAD = (bytes([0x22]) + struct.pack("<2H", 0x200, sp1.CELLS)
        + bytes([0x09]) + struct.pack("<2H", 0x210, sp1.MAP))
PAL = bytes([0x0A]) + struct.pack("<H", 0x220)
FLIP = bytes([0x13]) + struct.pack("<H", 3)


def test_draw_lands_in_the_window_with_its_palette():
    draw = bytes([0x10]) + struct.pack("<5H", 4, 205, 1, 1, 0)
    player, frames = _play(_script(LOAD, PAL, draw, FLIP), DATA, FILES)
    last = frames[-1]
    assert last.indices[0] == 9
    assert last.indices[15 * sp1.WINDOW_W + 15] == 9
    assert last.palette[9] == (9 * 17, 6 * 17, 0)
    assert player.roles == {"CELLS.CNS": "cells", "MAP.CNS": "map"}


def test_sources_name_the_cell_behind_each_byte():
    draw = bytes([0x10]) + struct.pack("<5H", 4, 205, 1, 1, 0)
    _, frames = _play(_script(LOAD, PAL, draw, FLIP), DATA, FILES)
    src = frames[-1].sources[3][1]
    assert (src.file, src.cell, src.row, src.half) == ("CELLS.CNS", 1, 3, 1)


def test_overlay_keeps_colour_zero_transparent():
    overlay_cells = {"CELLS.CNS": _cell(5) + cells.encode_cell(bytes([0, 7] * 128)),
                     "MAP.CNS": struct.pack("<2H", 1, 0x8002)}
    under = bytes([0x10]) + struct.pack("<5H", 4, 205, 1, 1, 0)
    on_top = bytes([0x23, 0x10]) + struct.pack("<5H", 4, 205, 1, 1, 1)
    _, frames = _play(_script(LOAD, PAL, under, on_top, FLIP), DATA, overlay_cells)
    row = frames[-1].indices[:4]
    assert row == bytes([5, 7, 5, 7])
    assert frames[-1].sources[0][0].under.cell == 0


def test_fade_reaches_its_target_in_sixteen_steps():
    fade = bytes([0x0B]) + struct.pack("<2H", 0x220, 1)
    wait = bytes([0x03]) + struct.pack("<H", 20)
    _, frames = _play(_script(LOAD, fade, wait), DATA, FILES)
    palettes = [f.palette[15] for f in frames]
    assert palettes[-1] == (255, 0, 0)
    assert len(set(palettes)) == 16


def test_rows_skip_the_extra_stride_before_drawing():
    files = {"CELLS.CNS": _cell(5) + _cell(9), "MAP.CNS": struct.pack("<4H", 1, 2, 1, 2)}
    draw = bytes([0x25]) + struct.pack("<6H", 1, 4, 205, 1, 2, 0)
    _, frames = _play(_script(LOAD, PAL, draw, FLIP), DATA, files)
    assert frames[-1].indices[0] == 9
    assert frames[-1].indices[16 * sp1.WINDOW_W] == 9


from compilegfx import extract
from compilegfx.container import tilesheet


def _chunked(chunks):
    table = bytearray(0x400)
    at = 0x400
    for i, chunk in enumerate(list(chunks) + [b""]):
        struct.pack_into("<HH", table, i * 4, at >> 16, at & 0xFFFF)
        at += len(chunk)
    return bytes(table) + b"".join(chunks)


def _stream(colour15):
    regs = [(k, k % 16, (k * 2) % 16, (k * 3) % 16) for k in range(15)] + [(15,) + colour15]
    return b"".join(bytes(r) for r in regs) + b"\xff"


def _gensei_script(*parts):
    body = bytearray(0x200)
    for at, blob in parts:
        body[at:at + len(blob)] = blob
    return bytes(body)


APPLY = bytes([0x21, 0x01])
PAL_A, PAL_B = _stream((15, 0, 7)), _stream((0, 15, 3))


def _games(script, images=2):
    scripts = _chunked([pc98lz.compress(b"\x00" * 64), pc98lz.compress(script), pc98lz.compress(b"\x00" * 64)])
    sheet = pc98lz.compress(bytes([0x3C]) * (tilesheet.TILE_BYTES * 16))
    graphics = _chunked([pc98lz.compress(b"\x00" * 64)] + [sheet] * images)
    return scripts, graphics


def _colour(register15):
    return tuple(v * 17 for v in register15)


def test_palette_applied_right_before_a_load_batch_is_the_only_candidate():
    script = _gensei_script((0, bytes([0x20]) + struct.pack("<H", 0x100) + APPLY),
                     (5, bytes([0x32, 2, 1, 0, 0x32, 2, 2, 1])),
                     (0x100, PAL_A))
    scripts, graphics = _games(script)
    found = gensei.candidates(scripts, graphics)
    assert [p[15] for p in gensei.distinct(found, 2, 1)] == [(255, 0, 119)]
    assert gensei.distinct(found, 2, 2) == gensei.distinct(found, 2, 1)


def test_a_palette_just_before_the_next_batch_belongs_to_that_batch():
    script = _gensei_script((0, bytes([0x20]) + struct.pack("<H", 0x100) + APPLY),
                     (5, bytes([0x32, 2, 1, 0, 0x32, 2, 1, 1])),
                     (20, bytes([0x20]) + struct.pack("<H", 0x150) + APPLY),
                     (25, bytes([0x32, 2, 2, 2, 0x32, 2, 2, 3])),
                     (0x100, PAL_A), (0x150, PAL_B))
    scripts, graphics = _games(script)
    found = gensei.candidates(scripts, graphics)
    assert len(gensei.distinct(found, 2, 1)) == 1
    assert [p[15] for p in gensei.distinct(found, 2, 2)] == [(0, 255, 51)]


def test_an_isolated_load_pattern_is_treated_as_text():
    script = _gensei_script((0, bytes([0x20]) + struct.pack("<H", 0x100) + APPLY),
                     (5, bytes([0x32, 2, 1, 0])), (0x100, PAL_A))
    scripts, graphics = _games(script)
    assert gensei.candidates(scripts, graphics) == {}


def _folder(tmp_path, script):
    scripts, graphics = _games(script)
    (tmp_path / "DISK_B.DAT").write_bytes(scripts)
    (tmp_path / "DISK_C.DAT").write_bytes(graphics)
    return {r.source: r for r in extract.scan(str(tmp_path))}


def test_extract_picks_the_only_script_palette(tmp_path):
    script = _gensei_script((0, bytes([0x20]) + struct.pack("<H", 0x100) + APPLY),
                     (5, bytes([0x32, 2, 1, 0, 0x32, 2, 2, 1])), (0x100, PAL_A))
    got = _folder(tmp_path, script)["DISK_C.DAT/c01"]
    assert got.palette == extract.PAL_EVIDENCE
    assert got.image.getpixel((2, 0)) == (255, 0, 119, 255)


def test_extract_offers_a_sheet_when_the_script_names_several_palettes(tmp_path):
    script = _gensei_script((0, bytes([0x20]) + struct.pack("<H", 0x100) + APPLY),
                     (5, bytes([0x32, 2, 1, 0, 0x32, 2, 2, 1])),
                     (60, bytes([0x20]) + struct.pack("<H", 0x150) + APPLY),
                     (0x100, PAL_A), (0x150, PAL_B))
    results = _folder(tmp_path, script)
    assert results["DISK_C.DAT/c01"].palette in extract.GUESSED
    sheet = results["DISK_C.DAT/c01_palettes"]
    assert sheet.status == extract.OK and "#1" in sheet.note and "#2" in sheet.note


def test_other_file_names_get_no_script_evidence(tmp_path):
    script = _gensei_script((0, bytes([0x20]) + struct.pack("<H", 0x100) + APPLY),
                     (5, bytes([0x32, 2, 1, 0, 0x32, 2, 2, 1])), (0x100, PAL_A))
    scripts, graphics = _games(script)
    (tmp_path / "DISK_B.DAT").write_bytes(scripts)
    (tmp_path / "OTHER.DAT").write_bytes(graphics)
    results = {r.source: r for r in extract.scan(str(tmp_path))}
    assert results["OTHER.DAT/c01"].palette != extract.PAL_EVIDENCE
