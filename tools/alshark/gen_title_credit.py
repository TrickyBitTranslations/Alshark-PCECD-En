#!/usr/bin/env python3
"""Pre-render the title-screen translator credit ("TrickyBit") to 8x8 tiles.

build.py title_credit_patch() writes the output (script/title_credit.bin) into the title's free
BG-tile slots (tiles 0x1FA+, which the title setup at bank 0x69 $6045 uploads to VRAM $1FA0+), and
writes the tile numbers into a blank row of the title's BG tilemap (bank 0x69 $72CD -> VRAM $0000).
No code hook: the title already uploads both regions. Tile format matches the baked copyright tiles
- 4bpp with all four planes = the glyph, so glyph pixels are color 15 (white in palette 0) and the
rest color 0 (transparent). Output is committed so the build needs no PIL:

  PYTHONPATH=tools python3 tools/alshark/gen_title_credit.py
"""
import os
from PIL import Image, ImageFont, ImageDraw

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TEXT = 'TrickyBit'
FONT = os.path.join(ROOT, 'noredist/fonts/04b03/04B_03__.TTF')
PX = 8
THRESH = 110
OUT = os.path.join(ROOT, 'script', 'title_credit.bin')


def main():
    ft = ImageFont.truetype(FONT, PX)
    img = Image.new('L', (160, 8), 0)
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
        plane = b''.join(bytes([r, r]) for r in rows)   # 8 rows, planes 0 & 1 = glyph
        tiles += plane + plane                           # planes 2 & 3 = glyph -> color 15 white
    open(OUT, 'wb').write(tiles)
    print('wrote %s (%d tiles, %dpx wide)' % (OUT, n, w))


if __name__ == '__main__':
    main()
