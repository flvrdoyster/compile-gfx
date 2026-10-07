"""Command line front end.

    compile-gfx one      <file> <out.png>
    compile-gfx batch    <src dir> <out dir>
    compile-gfx pc98     <MAIN_DAT dir> <out dir>   # Disc Station vol.10
    compile-gfx fld      <GENSE.FLD> <out dir>      # 幻世水滸伝 archive
    compile-gfx chunks   <DISK_C.DAT> <out dir>     # 幻世 series, in-game
    compile-gfx palettes <DISK_B.DAT>               # its palettes
    compile-gfx files    <game dir> <out dir>       # 幻世風狂伝, loose files

`one` and `batch` detect the format from the bytes, so they cover every
Windows-era file regardless of extension. vol.10's DOS files carry no magic
and keep their palettes in a separate table, so they get their own
subcommand rather than being guessed at.

`palettes` reports candidates, not answers: which run belongs to which
screen lives in the interpreter's control flow, not the data. See
`container.palette.find_script_palettes`.
"""
import argparse
import os
import sys

from . import load, to_png
from .codec import pc98lz
from .container import chunked, fld, gcs14
from .container import palette as palette_mod
from .container import planar, tilesheet
from .detect import NotAnImage

EXTS = (".gcn", ".cns", ".cnx", ".gcs", ".gmp", ".cnu", ".dat")

# Extensions that are only sometimes graphics. vol.12 uses .dat both for
# sprite sheets and for map tables, so a decode failure there is expected
# and gets reported as skipped rather than as an error.
AMBIGUOUS_EXTS = (".dat",)

PROGRAM_EXTS = (".COM", ".EXE", ".SYS", ".BAT")

GLYPH_W = GLYPH_H = 16
GLYPH_BYTES = (GLYPH_W // 8) * GLYPH_H * 4      # 128: four planes per cell


def _walk(src_root):
    for dirpath, _, filenames in os.walk(src_root):
        for fn in sorted(filenames):
            if fn.lower().endswith(EXTS):
                yield os.path.join(dirpath, fn)


def cmd_one(args):
    raw = open(args.src, "rb").read()
    try:
        to_png(load(raw, args.src), args.dest)
    except NotAnImage as e:
        print(f"{args.src}: not an image -- {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"{args.src}: {type(e).__name__}: {e}", file=sys.stderr)
        return 1
    return 0


def cmd_batch(args):
    ok = 0
    skipped, failed = [], []
    for src in _walk(args.src):
        rel = os.path.relpath(src, args.src)
        dest = os.path.join(args.dest, os.path.splitext(rel)[0] + ".png")
        try:
            to_png(load(open(src, "rb").read(), src), dest)
            ok += 1
        except NotAnImage as e:
            skipped.append((rel, str(e)))
        except Exception as e:
            if src.lower().endswith(AMBIGUOUS_EXTS):
                skipped.append((rel, "not graphics data"))
            else:
                failed.append((rel, f"{type(e).__name__}: {e}"))
    print(f"OK={ok} SKIPPED={len(skipped)} FAILED={len(failed)}")
    for rel, why in skipped:
        print(f"  skipped (not an image): {rel} -- {why}")
    for rel, why in failed:
        print(f"  FAILED: {rel} -- {why}")
    return 1 if failed else 0


def _pc98_glyph_sheet(buf, pal, dest, per_row=15):
    """vol.10 packs fonts as a run of 16x16 four-plane cells.

    Laying one out as a screen "succeeds" but yields noise; the tell is each
    character appearing four times in a row, which is the four planes being
    read as separate glyphs.
    """
    if len(buf) % GLYPH_BYTES:
        raise ValueError(
            f"decoded {len(buf)} bytes, not a whole number of {GLYPH_W}x{GLYPH_H} cells"
        )
    n = len(buf) // GLYPH_BYTES
    rows = (n + per_row - 1) // per_row
    w, h = per_row * GLYPH_W, rows * GLYPH_H
    flat = bytearray(w * h)
    for g in range(n):
        gx, gy = (g % per_row) * GLYPH_W, (g // per_row) * GLYPH_H
        cell = planar.unpack(buf[g * GLYPH_BYTES:(g + 1) * GLYPH_BYTES],
                             GLYPH_W, GLYPH_H, 4)
        for y in range(GLYPH_H):
            start = (gy + y) * w + gx
            flat[start:start + GLYPH_W] = cell[y * GLYPH_W:(y + 1) * GLYPH_W]
    from .image import Bitmap
    to_png(Bitmap(width=w, height=h, bpp=8, row_bytes=w, pixels=bytes(flat),
                  rgb_palette=tuple(pal), bottom_up=False), dest)
    return w, h, n


def cmd_pc98(args):
    menu_dat = args.palette or os.path.join(args.src, "MENU.DAT")
    if not os.path.exists(menu_dat):
        print(f"no palette table at {menu_dat} (pass --palette)", file=sys.stderr)
        return 2
    table = palette_mod.read_menu_dat(open(menu_dat, "rb").read())
    if not table:
        print(f"{menu_dat} holds no palettes", file=sys.stderr)
        return 2

    # Images MENU.DAT doesn't list may still have a palette of their own,
    # kept inside the menu binary; borrowing a neighbour's is badly wrong.
    menu_com = os.path.join(os.path.dirname(menu_dat), "MENU.COM")
    if os.path.exists(menu_com):
        for name, pal in palette_mod.read_menu_com(open(menu_com, "rb").read()).items():
            table.setdefault(name, pal)

    fallback = next(iter(table.values()))

    ok = 0
    skipped = []
    for fn in sorted(os.listdir(args.src)):
        if not fn.upper().endswith(".CNS"):
            continue
        pal = table.get(fn.upper(), fallback)
        note = "" if fn.upper() in table else " (shared palette)"
        dest = os.path.join(args.dest, os.path.splitext(fn)[0] + ".png")
        buf = pc98lz.decompress(open(os.path.join(args.src, fn), "rb").read())

        # A real screen is 640 wide and reasonably tall; anything shorter
        # that divides into 16x16 cells is a glyph sheet.
        plane = len(buf) // 4 if len(buf) % 4 == 0 else 0
        screen_first = bool(plane and plane % 80 == 0 and plane // 80 >= 100)
        attempts = []
        if screen_first or len(buf) % GLYPH_BYTES:
            attempts = ["screen", "glyphs"]
        else:
            attempts = ["glyphs", "screen"]

        errors = []
        for how in attempts:
            try:
                if how == "screen":
                    bmp = planar.to_bitmap(buf, pal)
                    to_png(bmp, dest)
                    print(f"  {fn:16s} {bmp.width}x{bmp.height} screen{note}")
                else:
                    w, h, n = _pc98_glyph_sheet(buf, pal, dest)
                    print(f"  {fn:16s} {w}x{h} glyph sheet, {n} cells{note}")
                ok += 1
                break
            except Exception as e:
                errors.append(f"{how}: {e}")
        else:
            skipped.append((fn, "; ".join(errors)))

    print(f"OK={ok} SKIPPED={len(skipped)}")
    for fn, why in skipped:
        print(f"  skipped {fn}: {why}")
    return 0


def cmd_fld(args):
    data = open(args.src, "rb").read()
    if args.list:
        for name, _, size in fld.entries(data):
            print(f"  {name:14s} {size:>9,}")
        print(f"{len(fld.entries(data))} entries")
        return 0

    ok = 0
    skipped = []
    for name, member in fld.iter_members(data):
        dest = os.path.join(args.dest, os.path.splitext(name)[0] + ".png")
        try:
            bmp = load(member, name)
            to_png(bmp, dest)
            print(f"  {name:14s} {bmp.width}x{bmp.height} {bmp.bpp}bpp")
            ok += 1
        except NotAnImage as e:
            skipped.append((name, str(e)))
        except Exception as e:
            skipped.append((name, f"{type(e).__name__}: {e}"))

    print(f"OK={ok} SKIPPED={len(skipped)}")
    for name, why in skipped:
        print(f"  skipped {name}: {why}")
    return 0


def _parse_palette_arg(text):
    tokens = text.replace(",", " ").split()
    if len(tokens) == 16 and all(len(t) == 3 for t in tokens):
        return [tuple(int(c, 16) * 17 for c in t) for t in tokens]
    parts = [int(v) for v in tokens]
    if len(parts) != 48:
        raise ValueError("need 16 RGB triples as 48 numbers, or 16 hex 'rgb' nibble triples")
    return [tuple(parts[i:i + 3]) for i in range(0, 48, 3)]


def _render_chunk(raw, pal):
    parts, _ = pc98lz.streams(raw)
    if not parts:
        return None, "empty chunk"

    if len(parts) == 1:
        dec = parts[0]
        if len(dec) % tilesheet.TILE_BYTES:
            return None, f"{len(dec)} bytes: not whole tiles"
        mask = tilesheet.guess_mask(dec)
        img = tilesheet.decode(dec, pal, mask=mask)
        return img, f"tile sheet {img.size[0]}x{img.size[1]}, mask {mask}"

    joined = b"".join(parts)
    dims = planar.guess_dims(len(joined) // 4) if len(joined) % 4 == 0 else None
    if not dims:
        return None, f"{len(parts)} streams, {len(joined)} bytes: not a plane set"
    bmp = planar.to_bitmap(joined, pal, size=dims)
    return _bitmap_image(bmp), f"screen {bmp.width}x{bmp.height}"


def _bitmap_image(bmp):
    from PIL import Image

    rows = [bmp.pixels[y * bmp.row_bytes:y * bmp.row_bytes + bmp.width]
            for y in range(bmp.height)]
    img = Image.frombytes("P", (bmp.width, bmp.height), b"".join(rows))
    flat = bytearray()
    for r, g, b in bmp.rgb_triples():
        flat += bytes((r, g, b))
    img.putpalette(bytes(flat) + bytes(768 - len(flat)))
    return img.convert("RGBA")


def _candidate_palettes(path):
    """Distinct complete palettes in a chunked DAT, first-appearance order.

    That order is not arbitrary trivia: it is what a human's notes end up
    referring to ("chunk 45 uses palette 3"), so it has to stay stable.
    """
    data = open(path, "rb").read()
    seen, order = set(), []
    for _, raw in chunked.iter_chunks(data):
        try:
            dec = pc98lz.decompress_stream(raw)[0]
        except Exception:
            continue
        for _, entries in palette_mod.find_script_palettes(dec, min_entries=16):
            if len(entries) != 16:
                continue
            key = tuple(entries[k] for k in range(16))
            if key not in seen:
                seen.add(key)
                order.append(key)
    return order


def _contact_sheet(images, labels, cell=200, cols=8):
    """One sheet of every candidate, labelled, for picking by eye."""
    from PIL import Image, ImageDraw

    gap = 16
    rows = (len(images) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * cell, rows * (cell + gap)), (30, 30, 34))
    draw = ImageDraw.Draw(sheet)
    for i, (img, label) in enumerate(zip(images, labels)):
        flat = Image.new("RGBA", img.size, (255, 255, 255, 255))
        thumb = Image.alpha_composite(flat, img).convert("RGB")
        thumb.thumbnail((cell, cell), Image.NEAREST)
        r, c = divmod(i, cols)
        sheet.paste(thumb, (c * cell + (cell - thumb.width) // 2, r * (cell + gap)))
        draw.text((c * cell + 3, r * (cell + gap) + cell + 2), label, fill=(210, 210, 215))
    return sheet


def cmd_chunks(args):
    data = open(args.src, "rb").read()
    if args.try_palettes:
        candidates = _candidate_palettes(args.try_palettes)
        if not candidates:
            print(f"no complete palettes in {args.try_palettes}", file=sys.stderr)
            return 2
        print(f"{len(candidates)} candidate palettes from {args.try_palettes}")
    else:
        candidates = None
    pal = _parse_palette_arg(args.palette) if args.palette else tilesheet.DEFAULT_PALETTE

    ok = 0
    skipped = []
    for index, raw in chunked.iter_chunks(data):
        if args.chunk is not None and index != args.chunk:
            continue
        stem = os.path.join(args.dest, f"c{index:02d}")
        try:
            if candidates:
                # Which palette belongs to which picture is not recoverable
                # from the file -- the records carry no tag and the choice
                # lives in the interpreter's control flow. So render them
                # all and let a human pick, then pass it back via --palette.
                shots, labels = [], []
                for n, cand in enumerate(candidates):
                    img, _ = _render_chunk(raw, list(cand))
                    if img is None:
                        continue
                    shots.append(img)
                    labels.append(f"[{n}]")
                if not shots:
                    _, why = _render_chunk(raw, pal)
                    skipped.append((index, why))
                    continue
                os.makedirs(args.dest, exist_ok=True)
                _contact_sheet(shots, labels).save(stem + "_palettes.png")
                print(f"  chunk {index:3d} {len(shots)} candidates "
                      f"-> c{index:02d}_palettes.png")
            else:
                img, note = _render_chunk(raw, pal)
                if img is None:
                    skipped.append((index, note))
                    continue
                os.makedirs(args.dest, exist_ok=True)
                img.save(stem + ".png")
                print(f"  chunk {index:3d} {note}")
            ok += 1
        except Exception as e:
            skipped.append((index, f"{type(e).__name__}: {e}"))

    print(f"OK={ok} SKIPPED={len(skipped)}")
    for index, why in skipped:
        print(f"  skipped chunk {index}: {why}")
    return 0


def cmd_palettes(args):
    data = open(args.src, "rb").read()
    total = 0
    for index, raw in chunked.iter_chunks(data):
        if args.chunk is not None and index != args.chunk:
            continue
        try:
            dec = pc98lz.decompress_stream(raw)[0]
        except Exception:
            continue
        for offset, entries in palette_mod.find_script_palettes(dec, args.min_entries):
            total += 1
            regs = ",".join(str(r) for r in sorted(entries))
            print(f"chunk {index:3d} @{offset:#07x}  registers [{regs}]")
            for reg in sorted(entries):
                r, g, b = entries[reg]
                print(f"    {reg:2d}: {r:3d},{g:3d},{b:3d}")
    print(f"{total} candidate(s)")
    return 0


def _script_palette(src_dir, min_colours=8):
    counts = {}
    for path in sorted(os.listdir(src_dir)):
        full = os.path.join(src_dir, path)
        if not os.path.isfile(full):
            continue
        raw = open(full, "rb").read()
        for data in (raw, pc98lz.decompress(raw)):
            for _, entries in palette_mod.find_script_palettes(data, min_entries=16):
                key = tuple(entries[k] for k in range(16))
                if len(set(key)) >= min_colours:
                    counts[key] = counts.get(key, 0) + 1
    if not counts:
        return None
    return list(max(counts, key=counts.get))


def _map_grid(dec):
    if len(dec) < 4:
        return False
    width, height = int.from_bytes(dec[0:2], "little"), int.from_bytes(dec[2:4], "little")
    return 0 < width <= 256 and 0 < height <= 256 and len(dec) >= 4 + 3 * width * height


def _render_file(raw, pal, mask):
    if gcs14.is_gcs14(raw):
        img = _bitmap_image(gcs14.parse(raw, pal))
        return img, "gcs v1.4 screen 640x400"
    parts, end = pc98lz.streams(raw)
    if len(parts) != 1 or end != len(raw):
        return None, "not a single LZ stream"
    dec = parts[0]
    if _map_grid(dec):
        return None, "map grid"
    whole = len(dec) // tilesheet.TILE_BYTES * tilesheet.TILE_BYTES
    if not whole or any(dec[whole:]):
        return None, f"{len(dec)} bytes: not whole tiles"
    tiles = dec[:whole]
    chosen = mask or tilesheet.guess_mask(tiles)
    img = tilesheet.decode(tiles, pal, mask=chosen)
    return img, f"tile sheet {img.size[0]}x{img.size[1]}, mask {chosen}"


def cmd_files(args):
    if args.palette:
        pal = _parse_palette_arg(args.palette)
    else:
        pal = _script_palette(args.src)
        if pal is None:
            print(f"no script palette in {args.src}; using the tile sheet default",
                  file=sys.stderr)
            pal = list(tilesheet.DEFAULT_PALETTE)
    ok = 0
    skipped = []
    for name in sorted(os.listdir(args.src)):
        full = os.path.join(args.src, name)
        if not os.path.isfile(full) or name.upper().endswith(PROGRAM_EXTS):
            continue
        if args.only and name.upper() not in args.only:
            continue
        try:
            img, note = _render_file(open(full, "rb").read(), pal, args.mask)
        except Exception as e:
            skipped.append((name, f"{type(e).__name__}: {e}"))
            continue
        if img is None:
            skipped.append((name, note))
            continue
        os.makedirs(args.dest, exist_ok=True)
        img.save(os.path.join(args.dest, os.path.splitext(name)[0] + ".png"))
        print(f"  {name}: {note}")
        ok += 1
    print(f"OK={ok} SKIPPED={len(skipped)}")
    for name, why in skipped:
        print(f"  skipped {name}: {why}")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(prog="compile-gfx", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("one", help="convert a single file")
    p.add_argument("src")
    p.add_argument("dest")
    p.set_defaults(func=cmd_one)

    p = sub.add_parser("batch", help="convert a tree, mirroring its structure")
    p.add_argument("src")
    p.add_argument("dest")
    p.set_defaults(func=cmd_batch)

    p = sub.add_parser("pc98", help="convert Disc Station vol.10's MAIN_DAT")
    p.add_argument("src", help="the MAIN_DAT directory")
    p.add_argument("dest")
    p.add_argument("--palette", help="palette table (default: <src>/MENU.DAT)")
    p.set_defaults(func=cmd_pc98)

    p = sub.add_parser("fld", help="convert an FLD archive's members")
    p.add_argument("src", help="a GENSE.FLD-style archive")
    p.add_argument("dest", nargs="?", default=".")
    p.add_argument("--list", action="store_true", help="list members instead")
    p.set_defaults(func=cmd_fld)

    p = sub.add_parser("chunks", help="convert a chunked DAT's graphics")
    p.add_argument("src", help="a DISK_C.DAT-style chunked file")
    p.add_argument("dest", nargs="?", default=".")
    p.add_argument("--chunk", type=int, help="convert only this chunk")
    p.add_argument("--palette", help='16 RGB triples, "r,g,b,r,g,b,..." '
                                     "(default: the engine's most common one)")
    p.add_argument("--try-palettes", metavar="DISK_B.DAT",
                   help="render each chunk under every palette in that file, as "
                        "one contact sheet to pick from by eye")
    p.set_defaults(func=cmd_chunks)

    p = sub.add_parser("palettes",
                       help="scan a chunked DAT for script-embedded palettes")
    p.add_argument("src", help="a DISK_B.DAT / DISK_C.DAT-style chunked file")
    p.add_argument("--chunk", type=int, help="scan only this chunk")
    p.add_argument("--min-entries", type=int, default=2,
                   help="ignore runs setting fewer registers than this (default 2)")
    p.set_defaults(func=cmd_palettes)

    p = sub.add_parser("files", help="convert a directory of loose engine files")
    p.add_argument("src", help="the game directory (幻世風狂伝's files)")
    p.add_argument("dest", nargs="?", default=".")
    p.add_argument("--only", type=lambda v: {n.upper() for n in v.split(",")},
                   help="comma-separated file names to convert")
    p.add_argument("--palette", help='16 "rgb" hex nibble triples, or 48 numbers '
                                     "(default: the scripts' most common one)")
    p.add_argument("--mask", choices=tilesheet.MASKS,
                   help="tile sheet plane 0 meaning (default: guessed per sheet)")
    p.set_defaults(func=cmd_files)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
