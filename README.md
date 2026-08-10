# compile-gfx

Decoders for Compile's graphics formats — Disc Station (PC/Windows and DOS
eras) and the PC-98 幻世 / 水滸伝 titles.

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

## Use

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
