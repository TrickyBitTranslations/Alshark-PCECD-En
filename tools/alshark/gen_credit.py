#!/usr/bin/env python3
"""Pre-render the boot save-menu credit ("TrickyBit Translations") to 8x8 tiles.

build.py save_menu_patch() reads the output (script/savemenu_credit.bin), DMAs the tiles to free
VRAM, and writes the BAT row at the bottom of the save screen - borderless white text on black.
Tile format: 4bpp, plane0 = plane3 = glyph, plane1 = plane2 = 0, so glyph pixels are color 9
(white in palette 2) and the rest color 0 (transparent). Run to regenerate (e.g. to change the
text or font); the output is committed so the build itself needs no PIL:

  PYTHONPATH=tools python3 tools/alshark/gen_credit.py
"""
import os
from PIL import Image, ImageFont, ImageDraw

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TEXT = 'TrickyBit Translations'
FONT = os.path.join(ROOT, 'noredist/fonts/04b03/04B_03__.TTF')
PX = 8
THRESH = 110
OUT = os.path.join(ROOT, 'script', 'savemenu_credit.bin')


def main():
    ft = ImageFont.truetype(FONT, PX)
    img = Image.new('L', (336, 8), 0)
    ImageDraw.Draw(img).text((0, 1), TEXT, fill=255, font=ft)   # 1px top margin
    bb = img.getbbox()
    w = bb[2] if bb else 0
    n = (w + 7) // 8
    px = img.load()
    tiles = b''
    for t in range(n):
        rows = []
        for y in range(8):
            r = 0
            for x in range(8):
                if t * 8 + x < img.width and px[t * 8 + x, y] > THRESH:
                    r |= 0x80 >> x
            rows.append(r)
        tiles += b''.join(bytes([r, 0]) for r in rows)   # rows 0-7: plane0=glyph, plane1=0
        tiles += b''.join(bytes([0, r]) for r in rows)   # rows 0-7: plane2=0, plane3=glyph
    open(OUT, 'wb').write(tiles)
    print('wrote %s (%d tiles, %dpx wide)' % (OUT, n, w))


if __name__ == '__main__':
    main()
