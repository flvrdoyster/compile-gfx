"""The decoded-image type every container parser produces."""
import os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Bitmap:
    """An image in the disc's own layout, not yet flipped or unpacked.

    `row_bytes` is the *source* stride, which includes 4-byte alignment
    padding for GMP-200 payloads but not for the older 8-byte header.
    `palette` is raw BGRA (4 bytes per colour) and is empty at 24bpp.

    Row order is **not** the same across lineages, so it is carried here
    rather than assumed: the Windows formats are bottom-up like a Windows
    DIB, while PC-98 planar VRAM starts at the top-left and is top-down.
    Getting this wrong flips the picture and nothing else, which is easy to
    miss when eyeballing a tiled or symmetric image.
    """
    width: int
    height: int
    bpp: int                  # 4, 8, or 24 (truecolor, no palette)
    row_bytes: int
    pixels: bytes
    palette: bytes = b""
    rgb_palette: tuple = field(default=())   # set when the palette isn't BGRA
    bottom_up: bool = True

    def rgb_triples(self):
        """Palette as [(r, g, b)] * n, whatever form it was stored in."""
        if self.rgb_palette:
            return list(self.rgb_palette)
        return [(self.palette[i + 2], self.palette[i + 1], self.palette[i])
                for i in range(0, len(self.palette), 4)]


# byte -> its two 4bpp pixels, high nibble (the left pixel) first
_NIBBLES = [bytes(((b >> 4), b & 0x0F)) for b in range(256)]


def to_png(bmp: Bitmap, out_path: str) -> None:
    from PIL import Image

    need = bmp.row_bytes * bmp.height
    if len(bmp.pixels) < need:
        raise ValueError(
            f"truncated pixel data: have {len(bmp.pixels)}, need {need} "
            f"({bmp.width}x{bmp.height} {bmp.bpp}bpp)"
        )

    if bmp.bpp == 24:
        rows = [bmp.pixels[y * bmp.row_bytes:y * bmp.row_bytes + bmp.width * 3]
                for y in range(bmp.height)]
        img = Image.frombytes("RGB", (bmp.width, bmp.height), b"".join(rows))
        b, g, r = img.split()          # stored BGR
        img = Image.merge("RGB", (r, g, b))
    else:
        rows = []
        for y in range(bmp.height):
            row = bmp.pixels[y * bmp.row_bytes:(y + 1) * bmp.row_bytes]
            if bmp.bpp == 4:
                rows.append(b"".join(_NIBBLES[b] for b in row)[:bmp.width])
            else:
                rows.append(row[:bmp.width])
        pal = bytearray()
        for r, g, b in bmp.rgb_triples():
            pal += bytes((r, g, b))
        pal += bytes(768 - len(pal))
        img = Image.frombytes("P", (bmp.width, bmp.height), b"".join(rows))
        img.putpalette(bytes(pal))

    if bmp.bottom_up:
        img = img.transpose(Image.FLIP_TOP_BOTTOM)
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    img.convert("RGB").save(out_path)


def to_pil(bmp: Bitmap):
    from PIL import Image

    rows = [bmp.pixels[y * bmp.row_bytes:y * bmp.row_bytes + bmp.width]
            for y in range(bmp.height)]
    img = Image.frombytes("P", (bmp.width, bmp.height), b"".join(rows))
    flat = bytearray()
    for r, g, b in bmp.rgb_triples():
        flat += bytes((r, g, b))
    img.putpalette(bytes(flat) + bytes(768 - len(flat)))
    return img.convert("RGBA")


def contact_sheet(images, labels, cell=200, cols=8):
    from PIL import Image, ImageDraw

    gap = 16
    rows = (len(images) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * cell, rows * (cell + gap)), (30, 30, 34))
    draw = ImageDraw.Draw(sheet)
    for i, (img, label) in enumerate(zip(images, labels)):
        flat = Image.new("RGBA", img.size, (255, 255, 255, 255))
        thumb = Image.alpha_composite(flat, img.convert("RGBA")).convert("RGB")
        thumb.thumbnail((cell, cell), Image.NEAREST)
        r, c = divmod(i, cols)
        sheet.paste(thumb, (c * cell + (cell - thumb.width) // 2, r * (cell + gap)))
        draw.text((c * cell + 3, r * (cell + gap) + cell + 2), label, fill=(210, 210, 215))
    return sheet
