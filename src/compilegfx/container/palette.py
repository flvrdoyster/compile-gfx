"""External palettes -- the DOS-era formats keep them out of the image file.

Disc Station vol.10's MAIN_DAT/MENU.DAT is a table of

    filename\\0  +  one flag byte  +  48 bytes (16 colours, RGB444)

Each nibble scales by 17 to reach 8-bit. **Channel order is R,G,B** despite
PC-98 palette registers conventionally being G,R,B -- reading it the "PC-98
way" produces a plausible-looking but wrong image.
"""


def rgb444(data: bytes, offset: int = 0, count: int = 16):
    return [
        (data[offset + i * 3] * 17,
         data[offset + i * 3 + 1] * 17,
         data[offset + i * 3 + 2] * 17)
        for i in range(count)
    ]


def read_menu_dat(data: bytes, suffix: bytes = b".CNS") -> dict:
    """{upper-case filename: [(r, g, b)] * 16} from a MENU.DAT-style table."""
    table = {}
    i = 0
    while True:
        j = data.find(suffix, i)
        if j < 0:
            break
        start = j
        while start > 0 and 0x20 <= data[start - 1] <= 0x7E:
            start -= 1
        name = data[start:j + len(suffix)].decode("ascii", "replace").upper()
        pal_off = j + len(suffix) + 1 + 1     # skip the suffix, its NUL, the flag
        pal = data[pal_off:pal_off + 48]
        if len(pal) == 48 and all(b <= 0x0F for b in pal):
            table[name] = rgb444(pal)
        i = j + len(suffix)
    return table
