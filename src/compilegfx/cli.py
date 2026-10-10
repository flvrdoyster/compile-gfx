"""Compile 게임 그래픽 추출기.

    compile-gfx extract <게임 폴더 또는 파일> <출력 폴더>

형식은 파일 내용으로 판별하므로 어떤 파일이 어떤 형식인지 몰라도 됨. 결과마다 형식과
팔레트 출처를 <출력 폴더>/extract_report.tsv에 남기고, 팔레트가 추정인 그림은 따로 알려 줌.

나머지 명령은 특정 형식을 직접 다룰 때 쓰는 세부 도구:
    one / batch   Windows 계열 파일 하나 / 폴더
    fld           FLD 아카이브
    chunks        청크형 DAT (--palette, --try-palettes로 팔레트 지정·비교)
    palettes      청크형 DAT의 스크립트 팔레트 후보 나열
    files         낱개 파일 폴더 (--palette, --mask 지정)
    pc98          extract와 같음
"""
import argparse
import os
import sys

from . import load, to_png
from .image import contact_sheet, to_pil
from .codec import pc98lz
from .container import chunked, fld, gcs14
from .container import palette as palette_mod
from .container import planar, tilesheet
from .detect import NotAnImage
from . import extract as extract_mod

EXTS = (".gcn", ".cns", ".cnx", ".gcs", ".gmp", ".cnu", ".dat")

# Extensions that are only sometimes graphics. vol.12 uses .dat both for
# sprite sheets and for map tables, so a decode failure there is expected
# and gets reported as skipped rather than as an error.
AMBIGUOUS_EXTS = (".dat",)

NOT_ART_EXTS = (".COM", ".EXE", ".SYS", ".BAT", ".CMD", ".OVL")


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


def cmd_pc98(args):
    return cmd_extract(args)


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
        if len(dec) == extract_mod.SCREEN_PLANE_BYTES:
            return None, "640x400 plane, one of four consecutive chunks (see extract)"
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
    return to_pil(bmp), f"screen {bmp.width}x{bmp.height}"


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


def cmd_chunks(args):
    data = open(args.src, "rb").read()
    evidence = {}
    if args.try_palettes:
        candidates = _candidate_palettes(args.try_palettes)
        if not candidates:
            print(f"no complete palettes in {args.try_palettes}", file=sys.stderr)
            return 2
        print(f"{len(candidates)} candidate palettes from {args.try_palettes}")
        if os.path.basename(args.src).upper() == extract_mod.GRAPHICS_FILE:
            evidence = extract_mod.gensei.candidates(open(args.try_palettes, "rb").read(), data)
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
                narrowed = extract_mod.gensei.distinct(
                    evidence, extract_mod.gensei.DISK_GRAPHICS, index)
                for n, cand in enumerate(candidates):
                    if narrowed and cand not in narrowed:
                        continue
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
                contact_sheet(shots, labels).save(stem + "_palettes.png")
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
        img = to_pil(gcs14.parse(raw, pal))
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
        if not os.path.isfile(full) or name.upper().endswith(NOT_ART_EXTS):
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


def cmd_extract(args):
    counts = {}
    rows = []
    taken = set()
    for result in extract_mod.scan(args.src):
        if result.status == extract_mod.OK:
            try:
                extract_mod.save(result, args.dest, taken)
            except Exception as e:
                result.status, result.note = extract_mod.UNKNOWN, f"저장 실패: {type(e).__name__}: {e}"
        counts[result.status] = counts.get(result.status, 0) + 1
        rows.append(result)
        if result.status == extract_mod.OK:
            mark = " (추정)" if result.palette in extract_mod.GUESSED else ""
            print(f"  {result.source}: {result.kind}{mark}")
    os.makedirs(args.dest, exist_ok=True)
    with open(os.path.join(args.dest, "extract_report.tsv"), "w", encoding="utf-8") as f:
        f.write("원본\t상태\t결과\t형식\t팔레트\t비고\n")
        for r in rows:
            f.write("\t".join((r.source, r.status, r.output, r.kind, r.palette, r.note)) + "\n")
    guessed = sum(1 for r in rows if r.status == extract_mod.OK and r.palette in extract_mod.GUESSED)
    print(f"{extract_mod.OK} {counts.get(extract_mod.OK, 0)} / "
          f"{extract_mod.SKIPPED} {counts.get(extract_mod.SKIPPED, 0)} / "
          f"{extract_mod.UNKNOWN} {counts.get(extract_mod.UNKNOWN, 0)}")
    if guessed:
        print(f"팔레트가 추정인 그림 {guessed}개 — extract_report.tsv의 팔레트 열 참고")
    unknown = [r for r in rows if r.status == extract_mod.UNKNOWN]
    if unknown:
        print("판별 불가:")
        groups = {}
        for r in unknown:
            groups.setdefault(r.source.split("/")[0] if "/" in r.source else "", []).append(r)
        for parent, items in groups.items():
            if parent and len(items) > 5:
                print(f"  {parent} 안 {len(items)}개 (extract_report.tsv 참고)")
                continue
            for r in items:
                print(f"  {r.source}: {r.note}")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(prog="compile-gfx", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("extract", help="형식을 알아서 판별해 그림을 모두 뽑음")
    p.add_argument("src", help="게임 폴더 또는 파일")
    p.add_argument("dest", help="출력 폴더")
    p.set_defaults(func=cmd_extract)

    p = sub.add_parser("one", help="convert a single file")
    p.add_argument("src")
    p.add_argument("dest")
    p.set_defaults(func=cmd_one)

    p = sub.add_parser("batch", help="convert a tree, mirroring its structure")
    p.add_argument("src")
    p.add_argument("dest")
    p.set_defaults(func=cmd_batch)

    p = sub.add_parser("pc98", help="same as extract (kept for old scripts)")
    p.add_argument("src", help="the MAIN_DAT directory")
    p.add_argument("dest")
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
                   help="render each chunk under the palettes in that file, as one "
                        "contact sheet to pick from by eye; for a DISK_C.DAT only the "
                        "palettes its scripts apply near its load, when they show any")
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
