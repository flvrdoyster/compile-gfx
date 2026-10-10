import os
import struct
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from compilegfx.codec import pc98lz
from compilegfx.container import cells
from compilegfx.script import sp1


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
