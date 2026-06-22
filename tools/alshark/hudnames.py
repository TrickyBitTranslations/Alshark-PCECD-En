#!/usr/bin/env python3
"""Generate the battle HUD party-name patch (script/hud_names_patch.json).

The battle HUD (right panel) shows party names as a table of 8x8 font tile-refs at
cooked 0x3f790a (8 tiles/member), referencing an 8x8 half-width font at disc 0x39000
(VRAM tile 0x200 + index) that only has katakana. This injects English 8x8 glyphs into
spare font slots (plane0==00) and rewrites the name table with English tile-refs - pure
data, no code hook. build.py: hud_patch() splices the resulting JSON. See
docs/battle-text-map.md.

  PYTHONPATH=tools python3 tools/alshark/hudnames.py            # regenerate with config below
  then: python rebuild/build.py --chd

To change the look: edit FONT / PX / Y_BASELINE / NAMES below and re-run. The glyphs are
8x8 (cells are tiny) so a crisp 8px pixel font + ALL-CAPS reads best; a 12px font like
Hardpixel gets mushy when squished. For pixel-perfect control, hand-edit the "glyphs"
hex in the JSON (32 bytes/glyph: per row [plane0,0xFF] x8, then repeated for planes 2&3;
plane0 bit set = foreground).
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
# spare font glyph slots (index into the 8x8 font page; must be blank AND unreferenced).
# IMPORTANT: slots 0x70-0xA3 are blank but USED as HUD box/bar/gauge graphics - do NOT use
# them (caused garbage in the bottom-right). The high run 0xC0-0xEB is blank and unreferenced.
SLOTS = list(range(0xC0, 0xEC))    # 0xC0..0xEB (44 slots; proportional slices need >1/name)
# ----------------------------------------------------------------------------

FONT_BASE = 0x39000     # disc offset of font glyph index 0 (32 bytes/glyph, interleaved)
NAME_TABLE = 0x3f790a   # disc offset of the HUD name table (16 bytes / 8 tile-refs per member)
SPACE = 0x6F            # existing blank glyph index used for padding
PAL = 0x70             # palette high-byte stored per tile-ref (matches the JP entries)


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


def glyph32(rows):
    g16 = bytearray()
    for r in rows:
        g16 += bytes((r, 0xFF))     # plane0 = shape, plane1 = 0xFF (matches the katakana glyphs)
    return bytes(g16 + g16)         # planes 2&3 = same as 0&1


def main():
    cooked = os.path.join(ROOT, "work", "track02.iso")
    disc = open(cooked, "rb").read() if os.path.exists(cooked) else None
    ft = ImageFont.truetype(FONT, PX)

    patches = []
    pool = list(SLOTS)
    for m, nm in enumerate(NAMES):
        tiles = name_tiles(ft, nm)
        if len(tiles) > 8:
            sys.exit("name %r needs %d tiles (>8)" % (nm, len(tiles)))
        refs = []
        for rows in tiles:
            if all(r == 0 for r in rows):
                refs.append(SPACE)
                continue
            if not pool:
                sys.exit("out of glyph slots")
            slot = pool.pop(0)
            if disc is not None:    # safety: only overwrite blank font slots
                g = disc[FONT_BASE + slot * 32: FONT_BASE + slot * 32 + 32]
                if any(g[k] for k in range(0, 16, 2)):
                    sys.exit("font slot 0x%x is not blank" % slot)
            patches.append([FONT_BASE + slot * 32, glyph32(rows).hex()])
            refs.append(slot)
        rec = bytearray()
        for r in refs:
            rec += bytes((r, PAL))
        while len(rec) < 16:
            rec += bytes((SPACE, PAL))
        patches.append([NAME_TABLE + m * 16, bytes(rec).hex()])
    print("used %d glyph slots of %d" % (len(SLOTS) - len(pool), len(SLOTS)))

    out = os.path.join(ROOT, "script", "hud_names_patch.json")
    json.dump(patches, open(out, "w"))
    print("wrote %s: %d patches for %d names (font=%s px=%d)"
          % (out, len(patches), len(NAMES), os.path.basename(FONT), PX))


if __name__ == "__main__":
    main()
