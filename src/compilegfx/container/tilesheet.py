"""256-tile 5-bitplane sprite sheets -- 幻世 series `DISK_C.DAT` graphics.

Each 16x16 tile packs five 1bpp bitplanes back to back (32 bytes each: 16
rows x 2-byte row = 160 bytes/tile). Plane 0 is a transparency mask, not a
colour bit: planes 1-4 give the 4bpp palette index, and only apply where
plane 0's bit is set -- pixels with plane 0 clear stay fully transparent
regardless of the other four planes. 256 tiles laid out 16 wide make a
256x256 sheet.

This differs from `container.planar`'s screens in both shape (tiled, with
per-pixel transparency) and plane count (5, not 4), so it produces an RGBA
`PIL.Image` directly rather than a `Bitmap` -- `Bitmap`/`image.to_png` model
a single flat index plane plus palette and have no transparency channel.

Confirmed identical (same layout, same default 16-colour palette) across
every 幻世-engine title checked so far (幻世風狂伝／torimono, 幻世快盗伝／kaitou).
"""
TILE_BYTES = 160
TILE_PX = 16


def decode(data: bytes, palette, cols: int = 16):
    """`data` must be a whole number of tiles. Returns an RGBA PIL Image.

    Needs Pillow -- unlike the other containers, this one's whole output is
    an RGBA image (per-pixel transparency has nowhere to go in `Bitmap`),
    so the dependency isn't optional here the way it is for `image.to_png`.
    """
    from PIL import Image

    if len(data) % TILE_BYTES:
        raise ValueError(
            f"{len(data)} bytes is not a whole number of {TILE_BYTES}-byte tiles"
        )
    n_tiles = len(data) // TILE_BYTES
    rows = (n_tiles + cols - 1) // cols

    img = Image.new("RGBA", (cols * TILE_PX, rows * TILE_PX), (0, 0, 0, 0))
    px = img.load()
    for tile in range(n_tiles):
        tr, tc = divmod(tile, cols)
        base = tile * TILE_BYTES
        for ry in range(TILE_PX):
            words = [(data[base + p * 32 + ry * 2] << 8) | data[base + p * 32 + ry * 2 + 1]
                     for p in range(5)]
            mask, w1, w2, w3, w4 = words
            for bit in range(TILE_PX):
                shift = 15 - bit           # MSB = leftmost pixel
                if not (mask >> shift) & 1:
                    continue
                idx = (((w1 >> shift) & 1) | (((w2 >> shift) & 1) << 1)
                       | (((w3 >> shift) & 1) << 2) | (((w4 >> shift) & 1) << 3))
                r, g, b = palette[idx]
                px[tc * TILE_PX + bit, tr * TILE_PX + ry] = (r, g, b, 255)
    return img
