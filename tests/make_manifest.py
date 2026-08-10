"""Regenerate tests/vectors/corpus.json from a local EXTRACT tree."""
import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, "..", "src"))
sys.path.insert(0, _HERE)
from test_corpus import (EXTS, PC98, _decoded_hash,  # noqa: E402
                         pc98_hash, pc98_palettes)

def main(corpus):
    out = {}
    for dp, _, fs in os.walk(corpus):
        for fn in sorted(fs):
            if not fn.lower().endswith(EXTS):
                continue
            p = os.path.join(dp, fn)
            try:
                out[os.path.relpath(p, corpus)] = _decoded_hash(p)
            except Exception:
                pass          # not-an-image files are covered by unit tests

        # DOS-era images never reach the loop above: they have no magic to
        # sniff, so _decoded_hash raises on them. Take the ones whose
        # palette this directory actually names -- the rest would only
        # pin whatever palette a caller happened to borrow.
        table = pc98_palettes(dp)
        for fn in sorted(fs):
            pal = table.get(fn.upper())
            if pal is None or not fn.lower().endswith(".cns"):
                continue
            p = os.path.join(dp, fn)
            try:
                out[PC98 + os.path.relpath(p, corpus)] = pc98_hash(p, pal)
            except Exception:
                pass
    dest = os.path.join(_HERE, "vectors", "corpus.json")
    json.dump(out, open(dest, "w"), indent=0, sort_keys=True)
    print(f"wrote {len(out)} entries to {dest}")

if __name__ == "__main__":
    main(sys.argv[1])
