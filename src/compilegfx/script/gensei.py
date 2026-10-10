import struct
from dataclasses import dataclass

from ..codec import pc98lz
from ..container import chunked
from ..container import palette as palette_mod

PALETTE_OPS = (0x20, 0x2F)
LOAD_OP = 0x32
DISK_SCRIPTS, DISK_GRAPHICS = 1, 2
MAX_SLOT = 0x1F
BATCH_GAP = 8
NEXT_GAP = 12
MIN_REGISTERS = 2
FULL_REGISTERS = 16


@dataclass(frozen=True)
class Candidate:
    palette: tuple
    script: int
    at: int
    address: int
    relation: str


def palette_events(script):
    events = []
    for k in range(len(script) - 3):
        if script[k] in PALETTE_OPS:
            address = struct.unpack_from("<H", script, k + 1)[0]
            if address < len(script):
                entries = palette_mod.read_script_stream(script, address)
                if len(entries) >= MIN_REGISTERS:
                    events.append((k, address, entries))
    return events


def load_events(script, counts):
    raw = [(k, script[k + 1], script[k + 2], script[k + 3])
           for k in range(len(script) - 3)
           if script[k] == LOAD_OP and script[k + 1] in counts and script[k + 3] <= MAX_SLOT
           and script[k + 2] < counts[script[k + 1]]]
    kept = []
    for i, event in enumerate(raw):
        before = i > 0 and event[0] - raw[i - 1][0] <= BATCH_GAP
        after = i + 1 < len(raw) and raw[i + 1][0] - event[0] <= BATCH_GAP
        if before or after:
            kept.append(event)
    return kept


def _full(entries):
    if len(entries) != FULL_REGISTERS:
        return None
    return tuple(entries[k] for k in range(FULL_REGISTERS))


def candidates(scripts: bytes, graphics: bytes):
    counts = {DISK_SCRIPTS: len(chunked.chunk_offsets(scripts)) - 1,
              DISK_GRAPHICS: len(chunked.chunk_offsets(graphics)) - 1}
    found = {}
    for index, chunk in chunked.iter_chunks(scripts):
        try:
            script = pc98lz.decompress_stream(chunk)[0]
        except Exception:
            continue
        palettes = palette_events(script)
        loads = load_events(script, counts)
        for j, (at, disk, number, _) in enumerate(loads):
            batch_end = at
            for later, *_ in loads[j:]:
                if later - batch_end > BATCH_GAP:
                    break
                batch_end = later
            next_load = next((later for later, *_ in loads if later > batch_end), len(script))
            entries = []
            earlier = [p for p in palettes if p[0] < at]
            if earlier:
                entries.append(("before", earlier[-1]))
            entries += [("after", p) for p in palettes
                        if batch_end < p[0] < next_load and next_load - p[0] > NEXT_GAP]
            for relation, (position, address, regs) in entries:
                full = _full(regs)
                if full:
                    found.setdefault((disk, number), []).append(
                        Candidate(full, index, position, address, relation))
    return found


def distinct(found, disk, number):
    seen = []
    for c in found.get((disk, number), []):
        if c.palette not in seen:
            seen.append(c.palette)
    return seen


def describe(found, disk, number):
    out = []
    order = distinct(found, disk, number)
    for k, palette in enumerate(order, 1):
        places = []
        for c in found.get((disk, number), []):
            if c.palette == palette:
                place = f"스크립트{c.script}@{c.address:#x}({'로드 전' if c.relation == 'before' else '로드 후'})"
                if place not in places:
                    places.append(place)
        out.append(f"#{k}={', '.join(places)}")
    return out
