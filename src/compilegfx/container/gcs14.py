from . import planar
from .palette import rgb444

MAGIC = b"gcs v1.4"
PALETTE_AT = 0x10
DATA_AT = 0x40
WIDTH, HEIGHT = 640, 400
ROW_BYTES = WIDTH // 8
PLANE_BYTES = ROW_BYTES * HEIGHT
PLANES = 4


def is_gcs14(data: bytes) -> bool:
    return data[:len(MAGIC)] == MAGIC


def header_palette(data: bytes):
    return rgb444(data, PALETTE_AT, count=16)


class _Plane:
    def __init__(self):
        self.buf = bytearray(PLANE_BYTES + ROW_BYTES)
        self.at = 0
        self.done = False

    def put(self, value):
        self.buf[self.at] = value
        self.step()

    def back(self, distance):
        return self.buf[self.at - distance] if self.at >= distance else 0

    def step(self):
        self.at += ROW_BYTES
        if self.at < PLANE_BYTES:
            return
        if self.at == PLANE_BYTES + ROW_BYTES - 1:
            self.done = True
        else:
            self.at -= PLANE_BYTES - 1


def _count(data, i, op, low):
    if op == 2:
        if low == 0:
            return data[i], i + 1
        return low, i
    if low <= 1:
        return (low << 8) | data[i], i + 1
    return low, i


def decode_planes(data: bytes):
    if not is_gcs14(data):
        raise ValueError(f"not a gcs v1.4 image (magic {data[:len(MAGIC)]!r})")
    planes = []
    i = DATA_AT
    for _ in range(PLANES):
        out = _Plane()
        buf = out.buf
        while not out.done:
            cmd = data[i]
            op, low = cmd >> 4, cmd & 0x0F
            n, i = _count(data, i + 1, op, low)
            if op in (0, 1):
                fill = 0 if op == 0 else 0xFF
                for _ in range(n):
                    out.put(fill)
                    if out.done:
                        break
            elif op == 2:
                for _ in range(n):
                    out.put(data[i])
                    i += 1
                    if out.done:
                        break
            elif op in (3, 10):
                back = 1 if op == 3 else 2
                for _ in range(n):
                    out.put(out.back(back))
                    if out.done:
                        break
            elif 4 <= op <= 9:
                src = planes[(op - 4) // 2]
                flip = 0xFF if op & 1 else 0
                for _ in range(n):
                    out.put(src[out.at] ^ flip)
                    if out.done:
                        break
            elif op == 11:
                upper = data[i]
                i += 1
                for _ in range(n):
                    buf[out.at + ROW_BYTES] = data[i]
                    i += 1
                    out.put(upper)
                    if not out.done:
                        out.step()
                    if out.done:
                        break
            elif op == 12:
                value = data[i]
                i += 1
                for _ in range(n):
                    out.put(value)
                    if out.done:
                        break
            elif op == 13:
                value = data[i]
                i += 1
                turn = 1 if value in (0x55, 0xAA) else 2
                for _ in range(n):
                    out.put(value)
                    if out.done:
                        break
                    value = ((value << turn) | (value >> (8 - turn))) & 0xFF
            else:
                width = 2 if op == 14 else 4
                pattern = data[i:i + width]
                i += width
                for _ in range(n):
                    for value in pattern:
                        out.put(value)
                        if out.done:
                            break
                    if out.done:
                        break
        planes.append(bytes(buf[:PLANE_BYTES]))
    return planes, i


def parse(data: bytes, palette=None):
    planes, _ = decode_planes(data)
    return planar.to_bitmap(b"".join(planes), palette or header_palette(data),
                            size=(WIDTH, HEIGHT))
