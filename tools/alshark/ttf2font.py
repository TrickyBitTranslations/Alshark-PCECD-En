"""TTF -> 1-bit glyph-grid PNG + per-glyph widths, for the VWF font pipeline.

Renders ASCII 0x20-0x7E from a TTF, baseline-aligned into a grid of CELL_W x CELL_H cells
(default 8x12), thresholds to 1-bit, flush-lefts each glyph and measures its advance width.
Outputs <out>.png (the editable grid, hand-tweak in any pixel editor), <out>_preview.png
(nearest-neighbour upscale to eyeball it), and <out>.widths.txt (hex code + width).
The PNG then feeds fontbuild.py -> glyphs.bin / widths.bin for baking.

Use a pixel-designed TTF at its native size for crisp results; a normal TTF works but is
rough at 8-12px. Tune --px / --baseline / --threshold to fit caps+descenders in CELL_H.
"""
import argparse
from PIL import Image, ImageFont, ImageDraw

ASCII = list(range(0x20, 0x7f))
COLS = 16


def build(ttf, px, cw, ch, baseline, thr, gap, space_w, out, weight=None):
    font = ImageFont.truetype(ttf, px)
    if weight is not None:
        font.set_variation_by_axes([weight])     # variable font: set wght axis
    rows = (len(ASCII) + COLS - 1) // COLS
    grid = Image.new('1', (COLS * cw, rows * ch), 0)
    widths = {}
    clipped = []
    for i, c in enumerate(ASCII):
        tmp = Image.new('L', (cw * 4, ch), 0)
        ImageDraw.Draw(tmp).text((1, baseline), chr(c), fill=255, font=font, anchor='ls')
        bw = tmp.point(lambda p, t=thr: 255 if p >= t else 0, mode='1')
        bb = bw.getbbox()
        if bb is None:                       # blank glyph (space)
            widths[c] = space_w
            continue
        x0, _, x1, _ = bb
        ink = x1 - x0
        if ink > cw:
            clipped.append(chr(c))
            ink = cw
        glyph = bw.crop((x0, 0, x0 + ink, ch))   # flush-left, keep baseline rows
        grid.paste(glyph, ((i % COLS) * cw, (i // COLS) * ch))
        widths[c] = ink + gap                    # advance = ink width + inter-glyph gap
    grid.save(out + '.png')
    grid.convert('L').resize((grid.width * 6, grid.height * 6), Image.NEAREST).save(
        out + '_preview.png')
    with open(out + '.widths.txt', 'w') as f:
        f.write('# hex  width  char\n')
        for c in ASCII:
            f.write('%02x %2d  %s\n' % (c, widths[c], repr(chr(c))))
    if clipped:
        print('WARNING clipped (ink > %d px): %s -> raise --cw or use a narrower font'
              % (cw, ' '.join(clipped)))
    print('wrote %s.png (%dx%d), %s_preview.png, %s.widths.txt'
          % (out, grid.width, grid.height, out, out))
    print('widths:', ' '.join('%s=%d' % (repr(chr(c)), widths[c]) for c in ASCII[:32]))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('ttf')
    ap.add_argument('out')
    ap.add_argument('--px', type=int, default=11, help='font pixel size (em)')
    ap.add_argument('--cw', type=int, default=8, help='cell width / max glyph px (<=12)')
    ap.add_argument('--ch', type=int, default=12, help='cell height / rows')
    ap.add_argument('--baseline', type=int, default=9, help='baseline row within the cell')
    ap.add_argument('--threshold', type=int, default=128, help='1-bit cutoff 0-255')
    ap.add_argument('--gap', type=int, default=1, help='inter-glyph advance gap px')
    ap.add_argument('--space', type=int, default=4, help='advance width of space (0x20)')
    ap.add_argument('--weight', type=float, default=None, help='variable-font wght axis')
    a = ap.parse_args()
    build(a.ttf, a.px, a.cw, a.ch, a.baseline, a.threshold, a.gap, a.space, a.out, a.weight)


if __name__ == '__main__':
    main()
