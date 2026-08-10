"""Regression against real discs, by hash -- no game data is committed.

Point COMPILE_GFX_CORPUS at the EXTRACT directory and run; without it these
skip. Refresh the manifest with `python tests/make_manifest.py <corpus>`
only when a change is *meant* to alter output.
"""
import hashlib
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import compilegfx

CORPUS = os.environ.get("COMPILE_GFX_CORPUS")
MANIFEST = os.path.join(os.path.dirname(__file__), "vectors", "corpus.json")
EXTS = (".gcn", ".cns", ".cnx", ".gcs", ".gmp", ".cnu", ".dat")


def _decoded_hash(path):
    raw = open(path, "rb").read()
    bmp = compilegfx.load(raw, path)
    h = hashlib.sha256()
    h.update(f"{bmp.width}x{bmp.height}x{bmp.bpp}|{bmp.bottom_up}|".encode())
    h.update(bytes(bmp.palette))
    h.update(bmp.pixels[:bmp.row_bytes * bmp.height])
    return h.hexdigest()


@pytest.mark.skipif(not CORPUS, reason="set COMPILE_GFX_CORPUS to run")
def test_corpus_matches_manifest():
    manifest = json.load(open(MANIFEST))
    checked = failed = 0
    for rel, expect in manifest.items():
        path = os.path.join(CORPUS, rel)
        if not os.path.exists(path):
            continue
        checked += 1
        if _decoded_hash(path) != expect:
            failed += 1
            print("MISMATCH:", rel)
    assert checked, "manifest matched no files -- wrong corpus path?"
    assert not failed, f"{failed}/{checked} files decode differently"
