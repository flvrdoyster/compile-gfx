"""External palettes -- the DOS-era formats keep them out of the image file.

Disc Station's MAIN_DAT/MENU.DAT is a small resource file: 16 bytes of
header ("DiscStation#NN" plus a Shift-JIS disc digit), a table of u16
offsets, then the resources those offsets point at -- loader command lines,
image filenames, and 16-colour palettes.

An image takes three consecutive slots: its filename, a one-byte flag, and
its palette. **Pair a name with its palette through the table, never by
what physically follows it.** vol.8 disc 3 stores a second, unused palette
immediately after the flag byte, so the palette adjacent to MENU083.CNS is
not the one the menu draws with. Taking the adjacent one recolours the
whole screen *and* exposes a bitplane the real palette exists to hide:
these menus keep an illustration in plane 2 and repeat colours 0-3 at 4-7
so that plane cannot show through.

Each nibble scales by 17 to reach 8-bit. **Channel order is R,G,B** despite
PC-98 palette registers conventionally being G,R,B -- reading it the "PC-98
way" produces a plausible-looking but wrong image.
"""
import struct

TABLE_OFFSET = 0x10
PALETTE_BYTES = 48        # 16 colours, RGB444, one nibble per channel
PALETTE_SLOT = 2          # slots run: filename, flag, palette

# what a DOS-era Compile filename is made of, for scanning a name backwards
NAME_CHARS = frozenset(b"ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-")


def rgb444(data: bytes, offset: int = 0, count: int = 16):
    return [
        (data[offset + i * 3] * 17,
         data[offset + i * 3 + 1] * 17,
         data[offset + i * 3 + 2] * 17)
        for i in range(count)
    ]


def slot_table(data: bytes):
    """The u16 offset table, or [] if this isn't a MENU.DAT-shaped file.

    The file describes its own table length: resources start where the
    table ends, so the first entry points just past the last one.
    """
    if len(data) < TABLE_OFFSET + 2:
        return []
    first = struct.unpack_from("<H", data, TABLE_OFFSET)[0]
    if not TABLE_OFFSET < first <= len(data):
        return []
    count = (first - TABLE_OFFSET) // 2
    if not 1 <= count <= 64:
        return []
    return list(struct.unpack_from(f"<{count}H", data, TABLE_OFFSET))


def _palette_at(data: bytes, offset: int):
    """rgb444 at `offset`, or None if those bytes can't be a palette.

    Every channel is a nibble, so a byte above 0x0F rules the run out.
    """
    if offset <= 0 or offset + PALETTE_BYTES > len(data):
        return None
    if any(b > 0x0F for b in data[offset:offset + PALETTE_BYTES]):
        return None
    return rgb444(data, offset)


def read_menu_com(data: bytes, suffix: bytes = b".CNS") -> dict:
    """{upper-case filename: [(r, g, b)] * 16} embedded in MENU.COM itself.

    Not every image is listed in MENU.DAT -- vol.8 and vol.10 both keep
    AAA.CNS's palette inside the menu binary instead, and rendering it with
    some other image's palette is silently, badly wrong.

    The record here is **name, NUL, then the palette**, with none of the
    flag byte MENU.DAT puts in between. There is no table to walk in an
    executable, so records are found by scanning; the 48 nibble-only bytes
    a real palette needs make a false hit unlikely.

    The name is read backwards from the suffix, which is why NAME_CHARS is
    narrower than DOS allows: vol.10 parks Shift-JIS help text right up
    against AAA.CNS, ending in bytes ('@', '$') that are legal in a DOS
    name and would otherwise be swallowed into it.
    """
    table = {}
    at = 0
    while True:
        at = data.find(suffix.upper() + b"\x00", at)
        if at < 0:
            return table
        end = at + len(suffix)
        start = at
        while start > 0 and data[start - 1] in NAME_CHARS and at - start < 8:
            start -= 1
        pal = _palette_at(data, end + 1)
        if pal and start < at:
            table[data[start:end].decode("ascii", "replace").upper()] = pal
        at = end


def read_script_stream(data: bytes, offset: int):
    """One [reg][R][G][B]... run at `offset`, terminated by a 0xFF register.

    This is the 幻世 series' *other* palette source, used by the in-game
    script interpreter rather than the Disc Station launcher -- found by
    disassembling 幻世快盗伝's palette-apply routine (kaitou `DISK_B.DAT`
    chunk 0, `GSC.COM`-loaded, at offset 0x612B) and matching its exact
    read pattern: select register, write R, write G, write B, repeat.

    Registers need not be sequential or complete -- a scene can set only
    the handful its art actually uses (幻世快盗伝's title screen sets just
    3 of 16). Returns `{register: (r, g, b)}`, empty if `offset` isn't the
    start of a valid, terminated run.
    """
    entries = {}
    i, n = offset, len(data)
    while i < n:
        reg = data[i]
        if reg == 0xFF:
            return entries
        if reg > 15 or i + 4 > n or any(b > 0x0F for b in data[i + 1:i + 4]):
            return {}
        entries[reg] = rgb444(data, i + 1, count=1)[0]
        i += 4
    return {}


def find_script_palettes(data: bytes, min_entries: int = 2):
    """Every terminated read_script_stream() run in `data`.

    There is no directory to walk -- this is scanned out of raw script
    bytecode -- so it returns every candidate as (offset, {reg: (r,g,b)})
    rather than a name-keyed table. **Which candidate belongs to which
    on-screen image isn't recoverable by scanning alone**: that mapping
    only exists in the interpreter's runtime control flow. Use this to
    narrow candidates, then match by eye (or by cross-checking which
    registers a decoded image's pixels actually use) against the real
    picture.
    """
    runs = []
    i, n = 0, len(data)
    while i + 4 <= n:
        if not (data[i] <= 15 and all(b <= 0x0F for b in data[i + 1:i + 4])):
            i += 1
            continue
        entries = read_script_stream(data, i)
        if len(entries) >= min_entries:
            runs.append((i, entries))
            i += 4 * len(entries) + 1
        else:
            i += 1
    return runs


def read_menu_dat(data: bytes, suffix: bytes = b".CNS") -> dict:
    """{upper-case filename: [(r, g, b)] * 16} from a MENU.DAT-style table."""
    table = {}
    slots = slot_table(data)
    for i, offset in enumerate(slots[:len(slots) - PALETTE_SLOT]):
        if not 0 < offset < len(data):
            continue
        end = data.find(b"\x00", offset)
        if end < 0:
            continue
        name = data[offset:end]
        if not name.upper().endswith(suffix.upper()):
            continue
        pal = _palette_at(data, slots[i + PALETTE_SLOT])
        if pal:
            table[name.decode("ascii", "replace").upper()] = pal
    return table
