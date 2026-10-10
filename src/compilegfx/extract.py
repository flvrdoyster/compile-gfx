import os
from collections import Counter
from dataclasses import dataclass

from .codec import cnx, gcn, pc98lz
from .container import cells, chunked, fld, gcs14, gmp200, planar, tilesheet
from .container import palette as palette_mod
from .detect import NotAnImage, load, looks_like_sjis_text
from .image import Bitmap
from .script import sp1

PAL_EMBEDDED = "파일 내장"
PAL_TABLE = "팔레트 표"
PAL_SCRIPT = "스크립트 최빈값(추정)"
PAL_DEFAULT = "기본값(추정)"
PAL_PLAYED = "스크립트 재생"
GUESSED = (PAL_SCRIPT, PAL_DEFAULT)

OK, SKIPPED, UNKNOWN = "변환", "건너뜀", "판별 불가"

NOT_ART_EXTS = (".COM", ".EXE", ".SYS", ".BAT", ".CMD", ".OVL", ".DLL", ".INF")
TABLE_SUFFIXES = (b".CNS", b".GCS")
PLANE_SPLIT_DIGITS = "0123"
MIN_SCRIPT_COLOURS = 8
SCRIPT_SJIS_RATIO = 0.15
TILE_ROW_STRIDE = 2
MIN_TILE_SIMILARITY = 0.05
SCREEN_DIMS = (640, 400)
SCREEN_PLANE_BYTES = SCREEN_DIMS[0] // 8 * SCREEN_DIMS[1]
MAX_BYTES = 16 << 20
MAX_SCRIPT_BYTES = 2 << 20

FOREIGN_MAGICS = (
    (b"RIFF", "RIFF(AVI·WAV)"), (b"\x89PNG", "PNG"), (b"\xff\xd8\xff", "JPEG"),
    (b"8BPS", "PSD"), (b"GIF8", "GIF"), (b"MThd", "MIDI"), (b"PK\x03\x04", "ZIP"),
    (b"BM", "BMP"),
)


def foreign_format(head):
    for magic, label in FOREIGN_MAGICS:
        if head.startswith(magic):
            return label
    if len(head) > 0x8006 and head[0x8001:0x8006] == b"CD001":
        return "ISO 디스크 이미지"
    return None

PC98_DEFAULT_8 = palette_mod.rgb444(bytes.fromhex(
    "000000 00000d 0d0000 0d000d 000d00 000d0d 0d0d00 080808"
    "0d0d0d 00000f 0f0000 0f000f 000f00 000f0f 0f0f00 0f0f0f"))


@dataclass
class Result:
    source: str
    status: str
    kind: str = ""
    image: object = None
    palette: str = ""
    note: str = ""
    output: str = ""


class Folder:
    def __init__(self, path, names):
        self.path = path
        self.names = names
        self._table = None
        self._script = False

    def read(self, name):
        return open(os.path.join(self.path, name), "rb").read()

    def table(self):
        if self._table is None:
            table = {}
            for name in self.names:
                if name.upper().startswith("MENU.DAT"):
                    raw = self.read(name)
                    for suffix in TABLE_SUFFIXES:
                        table.update(palette_mod.read_menu_dat(raw, suffix))
            for name in self.names:
                if name.upper() == "MENU.COM":
                    raw = self.read(name)
                    for suffix in TABLE_SUFFIXES:
                        for key, pal in palette_mod.read_menu_com(raw, suffix).items():
                            table.setdefault(key, pal)
            self._table = table
        return self._table

    def script_palette(self):
        if self._script is False:
            counts = Counter()
            for name in self.names:
                if os.path.getsize(os.path.join(self.path, name)) > MAX_SCRIPT_BYTES:
                    continue
                raw = self.read(name)
                if foreign_format(raw[:0x8010]):
                    continue
                blobs = [raw, pc98lz.decompress(raw)]
                if _is_chunked(raw):
                    blobs += [pc98lz.decompress_stream(c)[0] for _, c in chunked.iter_chunks(raw)]
                for blob in blobs:
                    for _, entries in palette_mod.find_script_palettes(blob, min_entries=16):
                        key = tuple(entries[k] for k in range(16))
                        if len(set(key)) >= MIN_SCRIPT_COLOURS:
                            counts[key] += 1
            self._script = list(counts.most_common(1)[0][0]) if counts else None
        return self._script

    def pc98_palette(self, name):
        pal = self.table().get(name.upper())
        if pal:
            return pal, PAL_TABLE
        pal = self.script_palette()
        if pal:
            return pal, PAL_SCRIPT
        return list(tilesheet.DEFAULT_PALETTE), PAL_DEFAULT


def _is_chunked(data):
    if len(data) <= chunked.TABLE_BYTES or data[:4] != b"\x00\x00\x00\x04":
        return False
    offsets = chunked.chunk_offsets(data)
    if len(offsets) < 3 or offsets[0] != chunked.TABLE_BYTES or offsets[-1] != len(data):
        return False
    for _, chunk in list(chunked.iter_chunks(data))[:4]:
        out, used = pc98lz.decompress_stream(chunk)
        if not out or used > len(chunk):
            return False
    return True


def _sjis_ratio(data):
    pairs = i = 0
    n = len(data)
    while i < n - 1:
        b = data[i]
        if (0x81 <= b <= 0x9F or 0xE0 <= b <= 0xEF) and 0x40 <= data[i + 1] <= 0xFC and data[i + 1] != 0x7F:
            pairs += 1
            i += 2
        else:
            i += 1
    return pairs * 2 / n if n else 0


def _row_similarity(data, stride):
    hit = total = 0
    for i in range(0, len(data) - stride, 2):
        a, b = data[i], data[i + stride]
        if a or b:
            total += 1
            hit += a == b
    return hit / total if total else 0


def _layout(dec):
    if len(dec) == SCREEN_PLANE_BYTES:
        return "plane", SCREEN_DIMS
    if _row_similarity(dec, TILE_ROW_STRIDE) >= MIN_TILE_SIMILARITY:
        return "tile", None
    return "unclear", None


def _map_grid(dec):
    if len(dec) < 4:
        return False
    width = int.from_bytes(dec[0:2], "little")
    height = int.from_bytes(dec[2:4], "little")
    return 0 < width <= 256 and 0 < height <= 256 and len(dec) >= 4 + 3 * width * height


def _windows(name, raw):
    if not (cnx.is_cnx(raw) or gmp200.is_gmp200(raw) or gcn.consumed(raw) == len(raw)):
        return None
    try:
        bmp = load(raw, name)
    except NotAnImage as e:
        return Result(name, SKIPPED, "Windows 계열", note=str(e))
    except Exception:
        return None
    kind = "CNX" if cnx.is_cnx(raw) else "GMP-200" if gmp200.is_gmp200(raw) else "GCN"
    return Result(name, OK, f"{kind} {bmp.width}x{bmp.height} {bmp.bpp}bpp", bmp,
                  PAL_EMBEDDED if bmp.bpp <= 8 else "")


def _gcs14(name, raw, folder):
    header = gcs14.header_palette(raw)
    pal = folder.table().get(os.path.basename(name).upper())
    source = PAL_TABLE
    if not pal and header != PC98_DEFAULT_8:
        pal, source = header, PAL_EMBEDDED
    if not pal:
        pal, source = folder.pc98_palette("")
    return Result(name, OK, "gcs v1.4 화면 640x400", gcs14.parse(raw, pal), source)


def _pc98_lz(name, raw, folder, mask=None):
    parts, end = pc98lz.streams(raw)
    if not parts or end != len(raw):
        return None
    pal, source = folder.pc98_palette(os.path.basename(name))
    if len(parts) == 4 and len({len(p) for p in parts}) == 1:
        dims = planar.guess_dims(len(parts[0]))
        if dims:
            bmp = planar.to_bitmap(b"".join(parts), pal, size=dims)
            return Result(name, OK, f"PC-98 화면 {dims[0]}x{dims[1]}", bmp, source)
    if len(parts) != 1:
        return Result(name, UNKNOWN, note=f"LZ 스트림 {len(parts)}개 {[len(p) for p in parts][:6]}")
    dec = parts[0]
    if _map_grid(dec):
        return Result(name, SKIPPED, "맵 격자", note=f"{len(dec)}B")
    kind, dims = _layout(dec)
    if kind == "plane":
        return Result(name, UNKNOWN, note=f"플레인 1장({dims[0]}x{dims[1]})으로 보임, 짝이 되는 플레인 없음")
    whole = len(dec) // tilesheet.TILE_BYTES * tilesheet.TILE_BYTES
    if whole and not any(dec[whole:]) and _layout(dec[:whole])[0] == "tile":
        tiles = dec[:whole]
        chosen = mask or tilesheet.guess_mask(tiles)
        img = tilesheet.decode(tiles, pal, mask=chosen)
        return Result(name, OK, f"타일시트 {img.size[0]}x{img.size[1]}", img, source,
                      note=f"마스크 {chosen}")
    ratio = _sjis_ratio(dec)
    if ratio >= SCRIPT_SJIS_RATIO:
        return Result(name, SKIPPED, "스크립트·텍스트로 보임", note=f"Shift-JIS {ratio:.0%}, {len(dec)}B")
    return Result(name, UNKNOWN, note=f"LZ 단일 스트림 {len(dec)}B, 타일(160B) 단위 아님")


def inspect(name, raw, folder):
    if fld.is_fld(raw):
        results = []
        for member, data in fld.iter_members(raw):
            results += inspect(f"{name}/{member}", data, folder)
        return results
    if gcs14.is_gcs14(raw):
        return [_gcs14(name, raw, folder)]
    if _is_chunked(raw):
        return _chunks(name, raw, folder)
    if looks_like_sjis_text(raw):
        return [Result(name, SKIPPED, "텍스트")]
    if raw[:2] == b"MZ" or name.upper().endswith(NOT_ART_EXTS):
        return [Result(name, SKIPPED, "프로그램·스크립트")]
    got = _windows(name, raw) or _pc98_lz(name, raw, folder)
    if got:
        return [got]
    return [Result(name, UNKNOWN, note=f"{len(raw)}B")]


def _single_stream(chunk):
    parts, end = pc98lz.streams(chunk)
    if len(parts) == 1 and end <= len(chunk):
        return parts[0]
    return None


def _plane_group(bufs):
    if len(bufs) == 4 and all(b is not None and _layout(b)[0] == "plane" for b in bufs):
        return SCREEN_DIMS
    return None


def _chunks(name, raw, folder):
    items = [(index, chunk) for index, chunk in chunked.iter_chunks(raw) if chunk]
    streams = {index: _single_stream(chunk) for index, chunk in items}
    results = []
    i = 0
    while i < len(items):
        index, chunk = items[i]
        group = [items[i + k][0] for k in range(4) if i + k < len(items)]
        dims = None
        if group == list(range(index, index + 4)):
            dims = _plane_group([streams[g] for g in group])
        if dims:
            pal, source = folder.pc98_palette("")
            sub = f"{name}/c{index:02d}-c{group[-1]:02d}"
            bmp = planar.to_bitmap(b"".join(streams[g] for g in group), pal, size=dims)
            results.append(Result(sub, OK, f"PC-98 화면 {dims[0]}x{dims[1]} (플레인 4청크)", bmp, source))
            i += 4
            continue
        sub = f"{name}/c{index:02d}"
        got = _pc98_lz(sub, chunk, folder) or _pc98_lz_prefix(sub, chunk, folder)
        results.append(got or Result(sub, UNKNOWN, note=f"{len(chunk)}B"))
        i += 1
    return results


def _pc98_lz_prefix(name, chunk, folder):
    parts, end = pc98lz.streams(chunk)
    if parts and end <= len(chunk):
        return _pc98_lz(name, chunk[:end], folder)
    return None


def _plane_split_groups(folder):
    groups = {}
    for name in folder.names:
        stem, ext = os.path.splitext(name)
        if stem and stem[-1] in PLANE_SPLIT_DIGITS:
            groups.setdefault((stem[:-1], ext), {})[stem[-1]] = name
    found = []
    for (prefix, ext), members in sorted(groups.items()):
        if set(members) != set(PLANE_SPLIT_DIGITS):
            continue
        planes = []
        for digit in PLANE_SPLIT_DIGITS:
            raw = folder.read(members[digit])
            parts, end = pc98lz.streams(raw)
            if len(parts) != 1 or end != len(raw):
                break
            planes.append(parts[0])
        if len(planes) == 4 and len({len(p) for p in planes}) == 1 and planar.guess_dims(len(planes[0])):
            found.append((prefix + ext, [members[d] for d in PLANE_SPLIT_DIGITS], planes))
    return found


def _players(folder, prefix):
    handled = {}
    results = []
    for name in folder.names:
        if not name.upper().endswith((".COM", ".EXE")):
            continue
        program = sp1.find(folder.read(name))
        if not program:
            continue
        if not sp1.supported(program):
            results.append(Result(prefix + name, UNKNOWN, note="SP1형 연출 플레이어로 보이나 판본이 다름"))
            continue
        lookup = {n.upper(): n for n in folder.names}

        def open_file(wanted):
            return folder.read(lookup[wanted.upper()])

        for start in sorted(program.starts):
            player = sp1.Player(program, start, open_file)
            try:
                frames = player.run()
            except (KeyError, ValueError) as e:
                results.append(Result(f"{prefix}{name}/{start:04x}", UNKNOWN, note=f"재생 중단: {e}"))
                continue
            for i, frame in enumerate(frames):
                results.append(Result(f"{prefix}{name}/{start:04x}/{i:04d}_t{frame.tick:04d}", OK,
                                      "SP1 연출 프레임 320x192", sp1.frame_image(frame), PAL_PLAYED))
            for file, role in player.roles.items():
                key = lookup.get(file.upper())
                if not key or key in handled:
                    continue
                if role == "map":
                    handled[key] = Result(prefix + key, SKIPPED, "SP1 배치표", note=f"{name}가 사용")
                    continue
                data = pc98lz.decompress(folder.read(key))
                pal = player.file_palettes.get(file)
                source = PAL_PLAYED if pal else PAL_DEFAULT
                img = cells.to_image(data, pal or tilesheet.DEFAULT_PALETTE)
                handled[key] = Result(prefix + key, OK, f"SP1 조각 {cells.count(data)}개",
                                      img, source, note=f"{name}가 사용, 16x16 4플레인")
    return results, handled


def scan(root):
    if os.path.isfile(root):
        folder = Folder(os.path.dirname(root) or ".", [os.path.basename(root)])
        folder.names = sorted(f for f in os.listdir(folder.path)
                              if os.path.isfile(os.path.join(folder.path, f)))
        yield from inspect(os.path.basename(root), folder.read(os.path.basename(root)), folder)
        return
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames.sort()
        names = sorted(f for f in filenames if not f.startswith("."))
        folder = Folder(dirpath, names)
        rel = os.path.relpath(dirpath, root)
        prefix = "" if rel == "." else rel + "/"
        played, handled = _players(folder, prefix)
        yield from played
        yield from handled.values()
        merged = set(handled)
        for combined, members, planes in _plane_split_groups(folder):
            if set(members) & merged:
                continue
            pal, source = folder.pc98_palette(combined)
            dims = planar.guess_dims(len(planes[0]))
            bmp = planar.to_bitmap(b"".join(planes), pal, size=dims)
            yield Result(prefix + combined, OK, f"PC-98 화면 {dims[0]}x{dims[1]} (플레인 4파일)",
                         bmp, source, note=" ".join(members))
            merged.update(members)
        for name in names:
            if name in merged:
                continue
            path = os.path.join(dirpath, name)
            with open(path, "rb") as f:
                head = f.read(0x8010)
            label = foreign_format(head)
            if label:
                yield Result(prefix + name, SKIPPED, label)
                continue
            if os.path.getsize(path) > MAX_BYTES and not fld.is_fld(head):
                yield Result(prefix + name, SKIPPED, "큰 파일", note=f"{os.path.getsize(path):,}B")
                continue
            yield from inspect(prefix + name, folder.read(name), folder)


def save(result, dest_root, taken):
    stem, ext = os.path.splitext(result.source)
    rel = stem + ".png"
    if rel.lower() in taken:
        rel = f"{stem}_{ext.lstrip('.')}.png"
    taken.add(rel.lower())
    out = os.path.join(dest_root, *rel.split("/"))
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    if isinstance(result.image, Bitmap):
        from .image import to_png
        to_png(result.image, out)
    else:
        result.image.save(out)
    result.output = rel
    return out
