"""Regression against real discs, by hash -- no game data is committed.

Point COMPILE_GFX_CORPUS at the EXTRACT directory and run; without it these
skip. Refresh the manifest with `python tests/make_manifest.py <corpus>`
only when a change is *meant* to alter output.

Keys prefixed "pc98:" get their own pass. Those files carry no magic and
take their palette from a sibling MENU.DAT/MENU.COM, so compilegfx.load()
-- which only sniffs the Windows lineage -- raises on them and quietly left
them out of the manifest. That is how a palette bug once shipped with two
thousand Windows-era files passing.
"""
import hashlib
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import compilegfx
from compilegfx.codec import pc98lz
from compilegfx.container import palette, planar

CORPUS = os.environ.get("COMPILE_GFX_CORPUS")
MANIFEST = os.path.join(os.path.dirname(__file__), "vectors", "corpus.json")
EXTS = (".gcn", ".cns", ".cnx", ".gcs", ".gmp", ".cnu", ".dat")
PC98 = "pc98:"


def _decoded_hash(path):
    raw = open(path, "rb").read()
    bmp = compilegfx.load(raw, path)
    h = hashlib.sha256()
    h.update(f"{bmp.width}x{bmp.height}x{bmp.bpp}|{bmp.bottom_up}|".encode())
    h.update(bytes(bmp.palette))
    h.update(bmp.pixels[:bmp.row_bytes * bmp.height])
    return h.hexdigest()


def pc98_palettes(directory):
    """Every palette covering one DOS-era directory.

    MENU.DAT holds most of them and MENU.COM carries the ones it leaves
    out, so the table is only complete with both. Matching MENU.DAT by
    prefix keeps this working on a tree that merges several discs into one
    directory and has to suffix the colliding tables.
    """
    table = {}
    names = sorted(f for f in os.listdir(directory)
                   if os.path.isfile(os.path.join(directory, f)))
    for fn in names:
        if fn.upper().startswith("MENU.DAT"):
            raw = open(os.path.join(directory, fn), "rb").read()
            table.update(palette.read_menu_dat(raw))
    for fn in names:
        if fn.upper() == "MENU.COM":
            raw = open(os.path.join(directory, fn), "rb").read()
            for name, pal in palette.read_menu_com(raw).items():
                table.setdefault(name, pal)
    return table


def pc98_hash(path, pal):
    """Hash a DOS-era image, palette included -- the palette is the point.

    Kept apart from _decoded_hash because the colours live in rgb_palette
    here rather than the raw BGRA `palette`, and folding them into that
    hash would rewrite every Windows-era entry in the manifest.
    """
    bmp = planar.to_bitmap(pc98lz.decompress(open(path, "rb").read()), pal)
    h = hashlib.sha256()
    h.update(f"{bmp.width}x{bmp.height}|{bmp.bottom_up}|".encode())
    for rgb in bmp.rgb_palette:
        h.update(bytes(rgb))
    h.update(bmp.pixels)
    return h.hexdigest()


@pytest.mark.skipif(not CORPUS, reason="set COMPILE_GFX_CORPUS to run")
def test_corpus_matches_manifest():
    manifest = json.load(open(MANIFEST))
    tables = {}
    checked = failed = 0
    for rel, expect in manifest.items():
        is_pc98 = rel.startswith(PC98)
        path = os.path.join(CORPUS, rel[len(PC98):] if is_pc98 else rel)
        if not os.path.exists(path):
            continue
        checked += 1
        if is_pc98:
            where = os.path.dirname(path)
            if where not in tables:
                tables[where] = pc98_palettes(where)
            got = pc98_hash(path, tables[where][os.path.basename(path).upper()])
        else:
            got = _decoded_hash(path)
        if got != expect:
            failed += 1
            print("MISMATCH:", rel)
    assert checked, "manifest matched no files -- wrong corpus path?"
    assert not failed, f"{failed}/{checked} files decode differently"
