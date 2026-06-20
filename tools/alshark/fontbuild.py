"""Glyph-grid PNG (+ widths) -> glyphs.bin + widths.bin for the VWF.

glyphs.bin is the exact $4EDA buffer format the #-engine compositor reads, locked by
dumping a System Card glyph (2026-06-19): 12 rows top->bottom, each 2 bytes:
  byte0 = pixels 0-7  (bit7 = leftmost pixel)
  byte1 = pixels 8-11 in bits 7-4  (bit4..7), bits 3-0 unused
So a 12px-wide, MSB-first, 12-row bitmap, 24 bytes/glyph, ASCII 0x20-0x7E (95 glyphs).
widths.bin is one advance-width byte per glyph, same order.
"""
import argparse
from PIL import Image

CH = 12
COLS = 16
FIRST, LAST = 0x20, 0x7e


def load_widths(path):
    w = {}
    for ln in open(path):
        ln = ln.strip()
        if not ln or ln.startswith('#'):
            continue
        p = ln.split()
        w[int(p[0], 16)] = int(p[1])
    return w


# Compact VWF format for the on-disc font bank (the $4EDA 24B/glyph form is 2280B and does
# not fit; see noredist/docs/findings/font-resident-space.md). Store 1 byte/row (px0-7
# MSB-left) <=8px wide, for the full 12-row cell, padded to a 16-byte (power-of-2) stride so
# the bank-0x6D render hook's glyph pointer is fontBase + idx<<4. The hook copies RH rows
# into $4EDA (byte0 = the row, byte1 = 0). 95 glyphs x 16 = 1520 B.
ROW0, RH, STRIDE = 0, 12, 16


def build_compact(png, widths_txt, out_glyphs, out_widths):
    grid = Image.open(png).convert('1')
    cw = grid.width // COLS
    widths = load_widths(widths_txt)
    glyphs, wbytes = bytearray(), bytearray()
    for c in range(FIRST, LAST + 1):
        i = c - FIRST
        cx, cy = (i % COLS) * cw, (i // COLS) * CH
        for ry in range(ROW0, ROW0 + RH):
            b = 0
            for rx in range(min(cw, 8)):
                if grid.getpixel((cx + rx, cy + ry)):
                    b |= 0x80 >> rx
            glyphs.append(b)
        glyphs += bytes(STRIDE - RH)              # pad each glyph to the 16-byte stride
        wbytes.append(min(widths.get(c, 4), 11))  # advance capped below the full-width cell
    open(out_glyphs, 'wb').write(glyphs)
    open(out_widths, 'wb').write(wbytes)
    print('%s: %d bytes (%d glyphs x %d-byte stride, %d rows)   %s: %d widths'
          % (out_glyphs, len(glyphs), len(glyphs) // STRIDE, STRIDE, RH, out_widths,
             len(wbytes)))


def build(png, widths_txt, out_glyphs, out_widths):
    grid = Image.open(png).convert('1')
    cw = grid.width // COLS
    widths = load_widths(widths_txt)
    glyphs, wbytes = bytearray(), bytearray()
    for c in range(FIRST, LAST + 1):
        i = c - FIRST
        cell = grid.crop(((i % COLS) * cw, (i // COLS) * CH,
                          (i % COLS) * cw + cw, (i // COLS) * CH + CH))
        for ry in range(CH):
            b0 = b1 = 0
            for rx in range(min(cw, 12)):
                if cell.getpixel((rx, ry)):
                    if rx < 8:
                        b0 |= 0x80 >> rx
                    else:
                        b1 |= 0x80 >> (rx - 8)
            glyphs += bytes((b0, b1))
        wbytes.append(min(widths.get(c, 4), 12))
    open(out_glyphs, 'wb').write(glyphs)
    open(out_widths, 'wb').write(wbytes)
    print('%s: %d bytes (%d glyphs x 24)   %s: %d widths'
          % (out_glyphs, len(glyphs), len(glyphs) // 24, out_widths, len(wbytes)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('png')
    ap.add_argument('widths')
    ap.add_argument('--out-glyphs', default='build/glyphs.bin')
    ap.add_argument('--out-widths', default='build/widths.bin')
    ap.add_argument('--compact', action='store_true',
                    help='8 bytes/glyph compact form for the on-disc font bank')
    a = ap.parse_args()
    (build_compact if a.compact else build)(a.png, a.widths, a.out_glyphs, a.out_widths)


if __name__ == '__main__':
    main()
