#!/usr/bin/env python3
"""Generate the battle HUD party-name patch (script/hud_names_patch.json + hud_glyphs.bin).

The battle HUD (right panel) shows party names as a table of 8x8 font tile-refs at
cooked 0x3f790a (8 tiles/member), referencing an 8x8 half-width font (VRAM tile 0x200 +
index) that only has katakana. We render each name proportionally, slice it into 8x8
tiles, and point the name table at RELOCATED tiles in free VRAM $7E00 (tiles $7E0+).

The glyphs must NOT go in the $2000 font page: its spare-looking slots $C0-$EB are the
enemy/party SHADOW sprites (empty plane0, oval in planes 2&3), so injecting there paints
our glyph over the shadow -> the enemy "white box" bug. Instead the 8-bytes-per-tile
plane0 blob is emitted to rebuild/incbin/hud_glyphs.bin (rides the bank-0x7F font asset)
and boot.s blit_hud_glyphs streams it to VRAM $7E00 each transition. The name-table refs
carry high byte $75 (real glyph -> BAT $77xx = tile $7xx after the draw's +2) or $70 for
the blank-space tile $26F. See noredist/docs/findings/enemy-shadow-tile-corruption.md.

  PYTHONPATH=tools python3 tools/alshark/hudnames.py            # regenerate with config below
  then: python rebuild/build.py --chd

To change the look: edit FONT / PX / NAMES below and re-run. The glyphs are 8x8 (cells are
tiny) so a crisp 8px pixel font + ALL-CAPS reads best. Each tile is 8 plane0 bytes
(bit set = foreground); the blit synthesizes plane1=$FF and duplicates into planes 2&3.
"""
import json
import os
import sys
from PIL import Image, ImageFont, ImageDraw
from alshark import cast

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# --- config -----------------------------------------------------------------
FONT = os.path.join(ROOT, "noredist/fonts/04b03/04B_03__.TTF")
PX = 8                              # render size (04b-03 is native at 8px)
THRESH = 110                       # ink threshold
# Names come from the single source script/names.tsv (see alshark/cast.py); editing a name
# there updates the main name table, the battle array, AND these HUD glyphs.
NAMES = cast.party_names(ROOT)
# ----------------------------------------------------------------------------

NAME_TABLE = 0x3f790a   # disc offset of the HUD name table (16 bytes / 8 tile-refs per member)
SPACE = 0x6F            # stock blank glyph index (VRAM tile $26F) used for padding
SPACE_HI = 0x70        # tile-ref high byte for the space tile (draw adds 2 -> tile $2xx, palette 7)
GLYPH_LO0 = 0xE0        # first relocated glyph tile low byte (tile $7E0)
GLYPH_HI = 0x75        # relocated-glyph tile-ref high byte (draw adds 2 -> BAT $77xx = tile $7xx)
MAX_TILES = 32         # tiles $7E0-$7FF available in free VRAM; blit is fixed-size (boot.s)
GLYPHS_BIN = os.path.join(ROOT, 'rebuild', 'incbin', 'hud_glyphs.bin')


def name_tiles(ft, nm):
    """Render a name PROPORTIONALLY across the 8-tile (64px) strip, baseline near the
    bottom, then slice into up to 8 8x8 tiles. Returns a list of <=8 tiles, each as 8
    row-bytes (0 = blank tile). Variable-width comes from the proportional render; the
    8px tile grid just samples it."""
    big = Image.new("L", (96, 16), 0)
    ImageDraw.Draw(big).text((0, 0), nm, fill=255, font=ft)
    bb = big.getbbox()
    strip = Image.new("L", (64, 8), 0)
    if bb:
        x0, y0, x1, y1 = bb
        crop = big.crop((x0, y0, min(x1, x0 + 64), y1))
        strip.paste(crop, (0, max(0, 7 - (y1 - y0))))
    tiles = []
    for t in range(8):
        rows = [sum((0x80 >> x) for x in range(8)
                    if strip.getpixel((t * 8 + x, y)) > THRESH) for y in range(8)]
        tiles.append(rows)
    while tiles and all(r == 0 for r in tiles[-1]):   # drop trailing blank tiles
        tiles.pop()
    return tiles


def main():
    ft = ImageFont.truetype(FONT, PX)

    patches = []            # name-table tile-ref rows (cooked 0x3f790a); gen_hud_idx reads these
    blob = bytearray()      # 8 plane0 bytes per relocated glyph tile, in tile order ($7E0+k)
    k = 0                   # next relocated glyph tile index
    for m, nm in enumerate(NAMES):
        tiles = name_tiles(ft, nm)
        if len(tiles) > 8:
            sys.exit("name %r needs %d tiles (>8)" % (nm, len(tiles)))
        refs = []
        for rows in tiles:
            if all(r == 0 for r in rows):
                refs.append((SPACE, SPACE_HI))
                continue
            if k >= MAX_TILES:
                sys.exit("out of HUD glyph tiles (%d > %d $7Ex slots)" % (k + 1, MAX_TILES))
            blob += bytes(rows)                    # 8 plane0 row bytes
            refs.append((GLYPH_LO0 + k, GLYPH_HI))
            k += 1
        rec = bytearray()
        for lo, hi in refs:
            rec += bytes((lo, hi))
        while len(rec) < 16:
            rec += bytes((SPACE, SPACE_HI))
        patches.append([NAME_TABLE + m * 16, bytes(rec).hex()])

    blob += bytes(MAX_TILES * 8 - len(blob))       # pad to the fixed blit size (32 tiles)
    os.makedirs(os.path.dirname(GLYPHS_BIN), exist_ok=True)
    open(GLYPHS_BIN, "wb").write(blob)
    out = os.path.join(ROOT, "script", "hud_names_patch.json")
    json.dump(patches, open(out, "w"))
    print("used %d glyph tiles ($7E0-$%03X)" % (k, 0x7E0 + k - 1))
    print("wrote %s (%d B) and %s (%d rows) for %d names (font=%s px=%d)"
          % (GLYPHS_BIN, len(blob), out, len(patches), len(NAMES), os.path.basename(FONT), PX))


if __name__ == "__main__":
    main()
