#!/usr/bin/env python3
"""Render 04b-03 at 8px into a fixed 8x8 ASCII glyph set for the anime-cutscene subtitles.

Writes rebuild/incbin/sub_glyphs.bin: 95 glyphs (ASCII 0x20..0x7E), 8 bytes each (one
row-byte per row, bit 0x80>>x = pixel column x), 1bpp. Same 04b-03 face the battle HUD
names use (tools/alshark/hudnames.py) so the English text stays consistent, and a true
8px font so each character is ONE 8x8 BG tile with nothing clipped (the 12px dialogue
VWF had to be squashed into 8 rows, which shaved the letter bottoms).

All glyphs share one baseline (a single common vertical shift, not per-glyph), so the
line sits straight. Caps/ascenders up top, descenders (g j p q y) drop below it.

  PYTHONPATH=tools python3 tools/alshark/subfont.py        # regenerate sub_glyphs.bin + preview
  then: python rebuild/build.py --chd
"""
import os
from PIL import Image, ImageFont, ImageDraw

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
FONT = os.path.join(ROOT, "noredist/fonts/04b03/04B_03__.TTF")
PX = 8
THRESH = 110
OUT = os.path.join(ROOT, "rebuild", "incbin", "sub_glyphs.bin")
PREVIEW = os.path.join(ROOT, "noredist", "work", "sub_glyphs_preview.png")
CHARS = [chr(c) for c in range(0x20, 0x7F)]        # 95 glyphs


def render():
    ft = ImageFont.truetype(FONT, PX)
    # one common baseline: union the ink of caps + descenders, shift so its top -> row 0
    probe = Image.new("L", (32, 24), 0)
    ImageDraw.Draw(probe).text((0, 4), "AQTgjypq", fill=255, font=ft)
    y0 = probe.getbbox()[1] - 4                     # ink-top relative to the pen origin
    glyphs = bytearray()
    grid = []
    for ch in CHARS:
        c = Image.new("L", (8, 8), 0)
        ImageDraw.Draw(c).text((0, -y0), ch, fill=255, font=ft)
        rows = [sum((0x80 >> x) for x in range(8) if c.getpixel((x, y)) > THRESH)
                for y in range(8)]
        glyphs += bytes(rows)
        grid.append(rows)
    return glyphs, grid


def main():
    glyphs, grid = render()
    open(OUT, "wb").write(glyphs)
    print("wrote %s: %d glyphs x 8 rows = %d bytes" % (OUT, len(CHARS), len(glyphs)))

    # preview: a grid of every glyph, plus a sample line, scaled up 6x
    sample = "ALSHARK  A NEW JOURNEY  gjpqy!?"
    cols = 32
    sheet = Image.new("L", (cols * 9, ((len(CHARS) + cols - 1) // cols) * 9 + 12), 40)
    for i, rows in enumerate(grid):
        ox, oy = (i % cols) * 9, (i // cols) * 9
        for y, rb in enumerate(rows):
            for x in range(8):
                if rb & (0x80 >> x):
                    sheet.putpixel((ox + x, oy + y), 255)
    sy = sheet.height - 9
    for i, ch in enumerate(sample):
        rows = grid[ord(ch) - 0x20]
        ox = i * 8
        if ox + 8 > sheet.width:
            break
        for y, rb in enumerate(rows):
            for x in range(8):
                if rb & (0x80 >> x):
                    sheet.putpixel((ox + x, sy + y), 255)
    sheet.resize((sheet.width * 6, sheet.height * 6), Image.NEAREST).save(PREVIEW)
    print("wrote preview %s" % PREVIEW)


if __name__ == "__main__":
    main()
