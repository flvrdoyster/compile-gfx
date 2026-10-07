TILE_BYTES = 160
TILE_PX = 16
SHEET_BYTES = 256 * TILE_BYTES

DEFAULT_PALETTE = (
    (0, 0, 0), (153, 170, 204), (85, 119, 136), (0, 85, 255),
    (0, 17, 170), (119, 187, 153), (51, 136, 68), (255, 187, 153),
    (221, 136, 102), (255, 0, 0), (136, 68, 34), (255, 238, 0),
    (187, 170, 17), (255, 221, 204), (255, 119, 187), (255, 255, 255),
)

MASK_SET_OPAQUE = "set-opaque"
MASK_SET_TRANSPARENT = "set-transparent"
MASK_NONE = "none"
MASKS = (MASK_SET_OPAQUE, MASK_SET_TRANSPARENT, MASK_NONE)
MASK_TOLERANCE = 0.002


def _rows(data: bytes):
    for tile in range(len(data) // TILE_BYTES):
        base = tile * TILE_BYTES
        for ry in range(TILE_PX):
            yield tile, ry, [(data[base + p * 32 + ry * 2] << 8) | data[base + p * 32 + ry * 2 + 1]
                             for p in range(5)]


def guess_mask(data: bytes, tolerance: float = MASK_TOLERANCE) -> str:
    colour_px = set_hides = clear_hides = 0
    any_set = any_clear = False
    for _, _, (mask, w1, w2, w3, w4) in _rows(data):
        colour = w1 | w2 | w3 | w4
        any_set |= mask != 0
        any_clear |= mask != 0xFFFF
        colour_px += bin(colour).count("1")
        set_hides += bin(mask & colour).count("1")
        clear_hides += bin(~mask & colour & 0xFFFF).count("1")
    allowed = colour_px * tolerance
    if any_clear and clear_hides <= allowed:
        return MASK_SET_OPAQUE
    if any_set and set_hides <= allowed:
        return MASK_SET_TRANSPARENT
    return MASK_NONE


def decode(data: bytes, palette=DEFAULT_PALETTE, cols: int = 16, mask: str = MASK_SET_OPAQUE):
    from PIL import Image

    if len(data) % TILE_BYTES:
        raise ValueError(
            f"{len(data)} bytes is not a whole number of {TILE_BYTES}-byte tiles"
        )
    if mask not in MASKS:
        raise ValueError(f"mask must be one of {MASKS}, got {mask!r}")
    n_tiles = len(data) // TILE_BYTES
    rows = (n_tiles + cols - 1) // cols

    img = Image.new("RGBA", (cols * TILE_PX, rows * TILE_PX), (0, 0, 0, 0))
    px = img.load()
    for tile, ry, (m, w1, w2, w3, w4) in _rows(data):
        if mask == MASK_NONE:
            m = 0xFFFF
        elif mask == MASK_SET_TRANSPARENT:
            m = ~m & 0xFFFF
        tr, tc = divmod(tile, cols)
        for bit in range(TILE_PX):
            shift = 15 - bit
            if not (m >> shift) & 1:
                continue
            idx = (((w1 >> shift) & 1) | (((w2 >> shift) & 1) << 1)
                   | (((w3 >> shift) & 1) << 2) | (((w4 >> shift) & 1) << 3))
            r, g, b = palette[idx]
            px[tc * TILE_PX + bit, tr * TILE_PX + ry] = (r, g, b, 255)
    return img
