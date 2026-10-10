import re
import struct
from dataclasses import dataclass, field

from ..codec import pc98lz
from ..container import cells as cells_mod

BASE = 0x100
DISPATCH = re.compile(rb"\xe8..\x8a\xd8\x32\xff\xd1\xe3\xff\xa7(..)", re.S)
TASK_START = re.compile(rb"\xb8(..)\x89\x45\x1e", re.S)
HANDLERS = (
    7818, 7819, 7820, 7828, 7875, 7884, 7891, 7898, 7916, 7929, 7958, 8090, 8163, 8170,
    8177, 8194, 8198, 8210, 8214, 8218, 8251, 8267, 8283, 8304, 8327, 8353, 8383, 8424,
    8465, 8483, 8514, 8544, 8583, 8587, 8593, 8636, 8642, 8668, 8681, 8718, 8732, 8776,
    8777, 8827, 8868, 8946, 9122, 9277, 9280, 9286, 9293, 9300, 9333,
)
LENGTHS = (
    1, 1, 1, 3, 3, 3, 3, 1, 3, 5, 3, 5, 1, 1, 7, 1, 11, 1, 1, 3, 3, 3, 3, 3, 5, 5, 5,
    5, 5, 5, 5, 7, 9, 9, 5, 1, 1, 13, 1, 3, 1, 1, 1, 1, 1, 5, 5, 1, 5, 1, 3, 3, 3,
)
CONTINUES = frozenset({0x04, 0x0A, 0x10, 0x17, 0x21, 0x23, 0x25, 0x2E, 0x2F, 0x30})

CELLS, SPARE, MAP = 0xA4AB, 0xA4AD, 0xA4AF
BUFFER_BYTES = {CELLS: 128 * 1024, SPARE: 128 * 1024, MAP: 40 * 1024}
CELL_LEAD = 128
VRAM_PLANE = 0x8000
STASH_PLANE = 0x4000
CLIP_LO, CLIP_HI = 0x4011, 0x7D00
LOWER_START, LOWER_WORDS = 0x4010, 0x1E78
FULL_BYTES = 0x7D00
CACHE_PER_PAGE = 320
WINDOW_W, WINDOW_H = 320, 192
TEXT_WINDOW = 15 * 80 + 20
TEXT_HOME = 720
GRAPHICS_HOME = 0x1100
FADE_STEPS = 16
DEFAULT_CUE_PERIOD = 65


@dataclass
class Program:
    code: bytes
    table: int
    starts: tuple

    def u16(self, addr):
        return struct.unpack_from("<H", self.code, addr - BASE)[0]

    def byte(self, addr):
        return self.code[addr - BASE]

    def string(self, addr):
        o = addr - BASE
        raw = self.code[o:o + 64].split(b"\0", 1)[0].decode("ascii", "replace")
        return raw.split(":")[-1]


def find(code: bytes):
    m = DISPATCH.search(code)
    if not m:
        return None
    table = struct.unpack("<H", m.group(1))[0]
    o = table - BASE
    if o < 0 or o + 2 * len(HANDLERS) > len(code):
        return None
    starts = tuple(struct.unpack("<H", s.group(1))[0] for s in TASK_START.finditer(code))
    return Program(code, table, starts)


def supported(program: Program) -> bool:
    o = program.table - BASE
    return struct.unpack_from(f"<{len(HANDLERS)}H", program.code, o) == HANDLERS


@dataclass(frozen=True)
class Source:
    file: str
    cell: int
    row: int
    half: int
    under: object = None


@dataclass
class Frame:
    tick: int
    indices: bytes
    palette: list
    position: tuple
    sources: list = field(default_factory=list)


class Player:
    def __init__(self, program, start, open_file, cue_period=DEFAULT_CUE_PERIOD):
        self.p = program
        self.pc = start
        self.open_file = open_file
        self.cue_period = cue_period
        self.tick = 0
        self.mem = {var: bytearray(size) for var, size in BUFFER_BYTES.items()}
        self.names = {}
        self.vram = [[bytearray(VRAM_PLANE) for _ in range(4)] for _ in range(2)]
        self.owner = [[None] * VRAM_PLANE, [None] * VRAM_PLANE]
        self.cache = [0] * (CACHE_PER_PAGE * 8)
        self.access, self.cache_page, self.display = 1, 0, 0
        self.scroll = (GRAPHICS_HOME, 400, 0, 0)
        self.text_sad = TEXT_HOME
        self.colour = [0] * 48
        self.fader = None
        self.vars = bytearray(256)
        self.wait = 0
        self.cues_used = 0
        self.done = False
        self.roles = {}
        self.file_palettes = {}

    def fetch(self):
        v = self.p.u16(self.pc)
        self.pc += 2
        return v

    def palette(self):
        return [tuple((self.colour[i * 3 + c] >> 4) * 17 for c in range(3)) for i in range(16)]

    def record_at(self, addr):
        return [self.p.byte(addr + k * 4 + 1 + c) for k in range(16) for c in range(3)]

    def set_palette(self, addr):
        self.colour = [(v << 4) & 0xFF for v in self.record_at(addr)]
        self.fader = None

    def start_fade(self, addr, period):
        target = self.record_at(addr)
        delta = []
        for i in range(48):
            nib = self.colour[i] >> 4
            delta.append((target[i] - nib) & 0xFF)
            self.colour[i] = (nib << 4) & 0xFF
        self.fader = [delta, period, 0, FADE_STEPS]

    def fade_tick(self):
        if not self.fader:
            return
        f = self.fader
        f[2] += 1
        if f[2] != f[1]:
            return
        f[2] = 0
        self.colour = [(c + d) & 0xFF for c, d in zip(self.colour, f[0])]
        f[3] -= 1
        if f[3] == 0:
            self.fader = None

    def load(self, op):
        name = self.p.string(self.fetch())
        var = self.fetch()
        data = pc98lz.decompress(self.open_file(name))
        offset = 0 if op == 0x09 else CELL_LEAD
        buf = self.mem.setdefault(var, bytearray(BUFFER_BYTES[CELLS]))
        buf[offset:offset + len(data)] = data
        self.names[var] = name
        self.roles[name] = "map" if op == 0x09 else "cells"
        if op == 0x2D:
            for page in range(2):
                for p in range(4):
                    src = (page * 4 + p) * STASH_PLANE
                    self.vram[page][p][0:STASH_PLANE] = buf[src:src + STASH_PLANE]
            self.names["stash"] = name

    def draw(self, extra):
        x, y, w, h, off = (self.fetch() for _ in range(5))
        cellbuf = self.mem[CELLS]
        opmap = self.mem[MAP]
        planes = self.vram[self.access]
        owner = self.owner[self.access]
        source = self.names.get(CELLS)
        self.file_palettes.setdefault(source, self.palette())
        counter = self.cache_page * CACHE_PER_PAGE
        row_di = x + y * 80
        bx = off * 2
        for _ in range(h):
            bx += extra * 2
            di = row_di
            for c in range(w):
                cx = struct.unpack_from("<H", opmap, bx + c * 2)[0]
                if self.cache[counter] != cx:
                    self.cache[counter] = cx
                    self.blit(planes, cellbuf, cx, di)
                    index = (cx & 0x7FFF) - 1
                    overlay = bool(cx & 0x8000)
                    for r in range(16):
                        at = di + r * 80
                        if CLIP_LO <= at < CLIP_HI:
                            for half in (0, 1):
                                under = owner[at + half] if overlay else None
                                owner[at + half] = Source(source, index, r, half, under)
                counter += 1
                di += 2
            bx += w * 2
            row_di += 0x500

    def blit(self, planes, cellbuf, cx, di):
        base = (cx & 0x7FFF) * cells_mod.CELL_BYTES
        cell = bytes(cellbuf[base:base + cells_mod.CELL_BYTES]).ljust(cells_mod.CELL_BYTES, b"\0")
        overlay = cx & 0x8000
        if overlay:
            mask = []
            for r in range(16):
                acc = 0
                for p in range(4):
                    acc |= (cell[p * 32 + r * 2] << 8) | cell[p * 32 + r * 2 + 1]
                mask.append(~acc & 0xFFFF)
        for p in range(4):
            plane = planes[p]
            for r in range(16):
                at = di + r * 80
                if not CLIP_LO <= at < CLIP_HI:
                    continue
                hi, lo = cell[p * 32 + r * 2], cell[p * 32 + r * 2 + 1]
                if overlay:
                    hi |= plane[at] & (mask[r] >> 8)
                    lo |= plane[at + 1] & (mask[r] & 0xFF)
                plane[at], plane[at + 1] = hi, lo

    def clear_cache(self):
        at = self.cache_page * CACHE_PER_PAGE
        self.cache[at:at + CACHE_PER_PAGE] = [0] * CACHE_PER_PAGE

    def clear(self, start, length):
        for plane in self.vram[self.access]:
            plane[start:start + length] = bytes(length)
        self.owner[self.access][start:start + length] = [None] * length

    def cue_ready(self):
        return self.tick // self.cue_period > self.cues_used

    def step(self):
        start = self.pc
        op = self.p.byte(start)
        self.pc += 1
        if op >= len(LENGTHS):
            raise ValueError(f"unknown opcode {op:#x} at {start:#x}")
        if op == 0x03:
            if self.wait == 0:
                self.wait = self.p.u16(self.pc)
            self.wait -= 1
            self.pc = start + 3 if self.wait == 0 else start
            return False
        if op == 0x04:
            self.pc = self.p.u16(self.pc)
            return True
        if op in (0x09, 0x22, 0x2D):
            self.load(op)
            return False
        if op == 0x0A:
            self.set_palette(self.fetch())
            return True
        if op == 0x0B:
            addr = self.fetch()
            self.start_fade(addr, self.fetch())
            return False
        if op in (0x10, 0x25):
            self.draw(self.fetch() if op == 0x25 else 0)
            return True
        if op == 0x11:
            self.clear(LOWER_START, LOWER_WORDS * 2)
            self.clear_cache()
            return False
        if op == 0x12:
            self.clear(0, FULL_BYTES)
            return False
        if op == 0x13:
            flags = self.fetch()
            if flags & 1:
                self.display ^= 1
            if flags & 2:
                self.cache_page ^= 1
                self.access ^= 1
            return False
        if op in (0x14, 0x15):
            self.vars[self.fetch() & 0xFF] = 1 if op == 0x14 else 0
            return False
        if op in (0x16, 0x17):
            v = self.fetch() & 0xFF
            self.vars[v] = min(255, self.vars[v] + 1) if op == 0x16 else max(0, self.vars[v] - 1)
            return op == 0x17
        if op in (0x18, 0x19, 0x1A, 0x1B):
            v = self.fetch() & 0xFF
            n = self.fetch() & 0xFF
            if op in (0x1A, 0x1B):
                n = self.vars[n]
            add = op in (0x18, 0x1A)
            self.vars[v] = min(255, self.vars[v] + n) if add else max(0, self.vars[v] - n)
            return False
        if op == 0x1C:
            v = self.fetch() & 0xFF
            self.vars[v] = self.fetch() & 0xFF
            return False
        if op == 0x1D:
            d = self.fetch() & 0xFF
            self.vars[d] = self.vars[self.fetch() & 0xFF]
            return False
        if op == 0x1E:
            v = self.vars[self.fetch() & 0xFF]
            target = self.fetch()
            if v:
                self.pc = target
            return False
        if op == 0x1F:
            v = self.vars[self.fetch() & 0xFF]
            n = self.fetch() & 0xFF
            target = self.fetch()
            if v == n:
                self.pc = target
                return True
            return False
        if op == 0x21:
            self.scroll = tuple(self.fetch() for _ in range(4))
            return True
        if op == 0x23:
            self.clear_cache()
            return True
        if op == 0x2B:
            self.mem[CELLS][:] = self.mem[SPARE]
            self.names[CELLS] = self.names.get(SPARE)
            return False
        if op == 0x2C:
            dst = self.mem[CELLS]
            for dl in range(8):
                page, p = (dl >> 2) & 1, dl & 3
                dst[dl * STASH_PLANE:(dl + 1) * STASH_PLANE] = self.vram[page][p][0:STASH_PLANE]
            self.names[CELLS] = self.names.get("stash")
            return False
        if op == 0x30:
            self.text_sad = self.fetch()
            self.fetch()
            return True
        if op == 0x33:
            if self.cue_ready():
                self.cues_used += 1
                self.pc += 2
            else:
                self.pc = start + 3 - (self.p.u16(self.pc) + 2)
            return False
        if op == 0x34:
            if self.cue_ready():
                self.cues_used += 1
                self.pc = self.p.u16(self.pc)
            else:
                self.pc += 2
            return False
        if op in (0x02, 0x31):
            self.done = True
            return False
        self.pc = start + LENGTHS[op]
        return op in CONTINUES

    def window(self):
        rel = TEXT_WINDOW - self.text_sad
        return (rel % 80) * 8, (rel // 80) * 16

    def capture(self):
        sad1, len1, sad2, _ = self.scroll
        x0, y0 = self.window()
        page = self.vram[self.display]
        stride = WINDOW_W // 8
        planes = [bytearray(stride * WINDOW_H) for _ in range(4)]
        starts = []
        for r in range(WINDOW_H):
            line = y0 + r
            base = sad1 * 2 + line * 80 if line < len1 else sad2 * 2 + (line - len1) * 80
            start = (base + x0 // 8) % VRAM_PLANE
            starts.append(start)
            for p in range(4):
                src = page[p]
                if start + stride <= VRAM_PLANE:
                    planes[p][r * stride:(r + 1) * stride] = src[start:start + stride]
                else:
                    planes[p][r * stride:(r + 1) * stride] = bytes(src[(start + i) % VRAM_PLANE] for i in range(stride))
        return planes, starts

    def frame_cells(self, starts):
        owner = self.owner[self.display]
        stride = WINDOW_W // 8
        return [[owner[(start + i) % VRAM_PLANE] for i in range(stride)] for start in starts]

    def run(self, max_ticks=100000, with_cells=False):
        frames = []
        last = None
        while not self.done and self.tick < max_ticks:
            for _ in range(100000):
                if not self.step() or self.done:
                    break
            self.fade_tick()
            planes, starts = self.capture()
            key = (bytes(b"".join(planes)), tuple(self.colour))
            if key != last:
                last = key
                frame = Frame(self.tick, unplanar(planes), self.palette(), self.window())
                if with_cells:
                    frame.sources = self.frame_cells(starts)
                frames.append(frame)
            self.tick += 1
        return frames


def unplanar(planes):
    stride = WINDOW_W // 8
    out = bytearray(WINDOW_W * WINDOW_H)
    for r in range(WINDOW_H):
        for xb in range(stride):
            bs = [planes[p][r * stride + xb] for p in range(4)]
            for bit in range(8):
                s = 7 - bit
                out[r * WINDOW_W + xb * 8 + bit] = (
                    ((bs[0] >> s) & 1) | (((bs[1] >> s) & 1) << 1)
                    | (((bs[2] >> s) & 1) << 2) | (((bs[3] >> s) & 1) << 3))
    return bytes(out)


def frame_image(frame):
    from PIL import Image

    img = Image.frombytes("P", (WINDOW_W, WINDOW_H), frame.indices)
    flat = b"".join(bytes(c) for c in frame.palette)
    img.putpalette(flat + bytes(768 - len(flat)))
    return img
