CELL_PX = 16
PLANES = 4
PLANE_BYTES = CELL_PX * CELL_PX // 8
CELL_BYTES = PLANE_BYTES * PLANES


def count(data: bytes) -> int:
    return len(data) // CELL_BYTES


def cell_indices(data: bytes, index: int) -> bytes:
    base = index * CELL_BYTES
    cell = data[base:base + CELL_BYTES]
    if len(cell) < CELL_BYTES:
        cell = cell + bytes(CELL_BYTES - len(cell))
    out = bytearray(CELL_PX * CELL_PX)
    for y in range(CELL_PX):
        words = [(cell[p * PLANE_BYTES + y * 2] << 8) | cell[p * PLANE_BYTES + y * 2 + 1]
                 for p in range(PLANES)]
        for x in range(CELL_PX):
            shift = 15 - x
            out[y * CELL_PX + x] = sum(((words[p] >> shift) & 1) << p for p in range(PLANES))
    return bytes(out)


def encode_cell(indices: bytes) -> bytes:
    if len(indices) != CELL_PX * CELL_PX:
        raise ValueError(f"a cell is {CELL_PX * CELL_PX} indices, got {len(indices)}")
    out = bytearray(CELL_BYTES)
    for y in range(CELL_PX):
        for p in range(PLANES):
            word = 0
            for x in range(CELL_PX):
                if indices[y * CELL_PX + x] > 15:
                    raise ValueError(f"index {indices[y * CELL_PX + x]} does not fit 4 planes")
                word |= ((indices[y * CELL_PX + x] >> p) & 1) << (15 - x)
            out[p * PLANE_BYTES + y * 2] = word >> 8
            out[p * PLANE_BYTES + y * 2 + 1] = word & 0xFF
    return bytes(out)


def to_image(data: bytes, palette, cols: int = 16):
    from PIL import Image

    n = count(data)
    rows = (n + cols - 1) // cols
    img = Image.new("P", (cols * CELL_PX, max(rows, 1) * CELL_PX))
    for i in range(n):
        tile = Image.frombytes("P", (CELL_PX, CELL_PX), cell_indices(data, i))
        img.paste(tile, ((i % cols) * CELL_PX, (i // cols) * CELL_PX))
    flat = b"".join(bytes(c) for c in palette)
    img.putpalette(flat + bytes(768 - len(flat)))
    return img


def from_image(img, n: int, cols: int = 16) -> bytes:
    if img.mode != "P":
        raise ValueError("cell sheets round-trip through palette indices; open the PNG as mode P")
    out = bytearray()
    for i in range(n):
        x, y = (i % cols) * CELL_PX, (i // cols) * CELL_PX
        out += encode_cell(img.crop((x, y, x + CELL_PX, y + CELL_PX)).tobytes())
    return bytes(out)
