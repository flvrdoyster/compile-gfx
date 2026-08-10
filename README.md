# compile-gfx

Decoders for Compile's graphics formats — Disc Station (PC/Windows and DOS
eras) and the PC-98 幻世 / 水滸伝 titles.

Written for preservation and fan-translation work. **No game data is
included here** — this is format documentation and code only. You need your
own copies of the discs for any of it to be useful.

**Extraction only, on purpose.** Each patch project keeps its own
reinsertion layer: fitting an exact byte budget, rebuilding archives,
injecting into disk images, pointer tables, font slots. What lives here is
the codec and container knowledge those projects would otherwise each copy.

That split isn't theoretical. Two independent copies of the same codec had
already drifted into two different bugs — one assumed BMP row padding that
doesn't exist in the older payload header (its test file was 640px wide,
where padded and tight agree, so the assumption was never exercised), and
the other was missing the "back-reference before the buffer start reads as
zero" rule and crashed on a real file. Each had a bug the other didn't.
The encoders therefore live here beside their decoders too, so the two
directions of one opcode table can't diverge.

## Install

```bash
pip install git+https://github.com/flvrdoyster/compile-gfx
```

PNG output needs Pillow: `pip install "compile-gfx[png] @ git+https://github.com/flvrdoyster/compile-gfx"`.
The decoders themselves are pure standard library, so you can use them
without it.

## Command line

```bash
compile-gfx one   MAIN14.GCN out.png
compile-gfx batch ds14/data  ds14/png     # whole tree, structure mirrored
compile-gfx pc98  ds10/data/MAIN_DAT ds10/png
```

`batch` detects each file from its bytes, so it handles every Windows-era
format in one pass. It reports three counts: converted, *skipped* (files
with a graphics extension that aren't images — vol.20 has two, a staff note
and a puzzle file), and *failed* (anything genuinely unexpected).

vol.10 needs `pc98` instead: those files carry no magic and take their
palette from `MAIN_DAT/MENU.DAT`.

## Use as a library

```python
import compilegfx
bmp = compilegfx.load(open("MAIN14.GCN", "rb").read())
compilegfx.to_png(bmp, "out.png")          # needs pillow
```

`load()` sniffs the content — never trust the extension. The same `.CNS`
suffix is a Windows LZ image on Disc Station vol.12/14/20 and a DOS planar
one on vol.10.

DOS/PC-98 files carry no magic and keep their palette in a separate table,
so they are assembled explicitly:

```python
from compilegfx.codec import pc98lz
from compilegfx.container import palette, planar

pal = palette.read_menu_dat(open("MENU.DAT", "rb").read())["DS10_T.CNS"]
buf = pc98lz.decompress(open("DS10_T.CNS", "rb").read())
compilegfx.to_png(planar.to_bitmap(buf, pal), "out.png")
```

## What's covered

| | codec | container |
|---|---|---|
| `.GCN` `.CNS` `.CNU` | `codec.gcn` | `container.header8` |
| `.GCS` (vol.20) | `codec.gcn` | `container.gmp200` |
| `.GMP` | none — stored raw | `container.gmp200` |
| `.CNX` | `codec.cnx` | `container.gmp200` |
| vol.10 `.CNS` | `codec.pc98lz` | `container.planar` + `container.palette` |
| `.CND` | `codec.pc98rle` | `container.planar` |

`codec.pc98rle` is reversed from vol.10's `MENU.COM` but no `.CND` files
ship on that disc, so it is untested against real data.

Two gotchas worth keeping in mind, both of which cost real debugging time:

- **Row order differs by lineage.** Windows formats are bottom-up like a
  Windows DIB; PC-98 planar VRAM is top-down. `Bitmap.bottom_up` carries it
  rather than leaving it to be assumed. Getting it wrong flips the image and
  changes nothing else, which is easy to miss on tiled or symmetric art.
- **Palette counts and channel orders are stored, not inferable.** The
  8-byte header keeps the count at offset 6; deriving it from file size
  happens to work at 8bpp and silently breaks every 4bpp image.

## Tests

```bash
pytest tests/test_codecs.py                    # no game data needed
COMPILE_GFX_CORPUS=/path/to/EXTRACT pytest     # + 2056-file regression
```

No disc data is committed. `tests/vectors/corpus.json` holds only hashes of
decoded output, checked against whatever files you have locally.
Regenerate with `python tests/make_manifest.py <corpus>` — but only when a
change is *meant* to alter output.

## Credits

The formats were worked out from a mix of disassembly and prior art:

- **mkjpg**'s `cns110.exe` and `cnx106.exe` (2005) — standalone CNS→BMP and
  CNX→BMP converters. Disassembling `cnx106.exe` is what produced the CNX
  2-bit-tag codec here, and its changelog was the first hint at the shape of
  the tag stream.
- Disc Station vol.14's `DSMENU.EXE` and vol.10's `MENU.COM` — the Windows
  LZ opcode table, the PC-98 LZ, the RLE, and the codec/plane-mask byte all
  come from those.
- [gensei-pc98](https://github.com/flvrdoyster/gensei-pc98) — the PC-98 LZ
  and the planar layout, cross-checked against this.
- [suiko-web-v2](https://github.com/flvrdoyster/suiko-web-v2) — the CNS
  palette-count field and the 4bpp split, independently derived there first.
