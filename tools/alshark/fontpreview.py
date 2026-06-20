"""Render a font's ASCII grid + a sample line to noredist/fonts/samples/<name>/ for the
VWF font audition. Handles static and variable (multi-axis) fonts. Proportional spacing
(ink width + gap) so the sample previews what the in-game VWF would draw.

  python tools/alshark/fontpreview.py <ttf> <name> --weights 400,500,600
"""
import argparse
import os
from PIL import ImageFont, Image, ImageDraw

ASCII = list(range(0x20, 0x7f))
SAMPLE = "Wuria and Zorias have gone 0123!?"
COLS = 16


def setvar(font, weight, width):
    try:
        axes = font.get_variation_axes()
    except Exception:
        return
    if not axes:
        return
    vals = []
    for a in axes:
        nm = a['name'].decode() if isinstance(a['name'], bytes) else a['name']
        if nm == 'Weight' and weight is not None:
            vals.append(weight)
        elif nm == 'Width':
            vals.append(width)
        else:
            vals.append(a['default'])
    font.set_variation_by_axes(vals)


def render_one(ttf, px, cw, ch, baseline, thr, gap, weight, width):
    font = ImageFont.truetype(ttf, px)
    setvar(font, weight, width)
    rows = (len(ASCII) + COLS - 1) // COLS
    grid = Image.new('1', (COLS * cw, rows * ch), 0)
    widths = {}
    for i, c in enumerate(ASCII):
        tmp = Image.new('L', (cw * 4, ch), 0)
        ImageDraw.Draw(tmp).text((1, baseline), chr(c), fill=255, font=font, anchor='ls')
        bw = tmp.point(lambda p, t=thr: 255 if p >= t else 0, mode='1')
        bb = bw.getbbox()
        if bb is None:
            widths[c] = gap + 3
            continue
        x0, _, x1, _ = bb
        w = min(x1 - x0, cw)
        grid.paste(bw.crop((x0, 0, x0 + w, ch)), ((i % COLS) * cw, (i // COLS) * ch))
        widths[c] = x1 - x0 + gap
    return grid, widths


def sample_strip(grid, widths, cw, ch):
    strip = Image.new('1', (400, ch), 0)
    x = 0
    for s in SAMPLE:
        c = ord(s)
        j = c - 0x20
        col, row = j % COLS, j // COLS
        strip.paste(grid.crop((col * cw, row * ch, col * cw + cw, row * ch + ch)), (x, 0))
        x += widths.get(c, 4)
    return strip.crop((0, 0, max(x, 1), ch))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('ttf')
    ap.add_argument('name')
    ap.add_argument('--weights', default='400')
    ap.add_argument('--px', type=int, default=11)
    ap.add_argument('--cw', type=int, default=10)
    ap.add_argument('--ch', type=int, default=12)
    ap.add_argument('--baseline', type=int, default=9)
    ap.add_argument('--threshold', type=int, default=128)
    ap.add_argument('--gap', type=int, default=1)
    ap.add_argument('--width', type=float, default=100)
    ap.add_argument('--scale', type=int, default=6)
    a = ap.parse_args()
    outdir = os.path.join('noredist', 'fonts', 'samples', a.name)
    os.makedirs(outdir, exist_ok=True)
    weights = [float(w) for w in a.weights.split(',')]
    strips = []
    for wt in weights:
        grid, widths = render_one(a.ttf, a.px, a.cw, a.ch, a.baseline, a.threshold, a.gap,
                                  wt, a.width)
        grid.convert('L').resize((grid.width * a.scale, grid.height * a.scale),
                                 Image.NEAREST).save(os.path.join(outdir, 'grid_%d.png' % wt))
        strips.append(sample_strip(grid, widths, a.cw, a.ch))
    sc = a.scale
    w = max(s.width for s in strips) * sc + 4
    h = len(strips) * (a.ch * sc + 8)
    canvas = Image.new('L', (w, h), 30)
    y = 0
    for s in strips:
        canvas.paste(s.convert('L').resize((s.width * sc, a.ch * sc), Image.NEAREST), (2, y))
        y += a.ch * sc + 8
    canvas.save(os.path.join(outdir, 'sample.png'))
    print('wrote %s/ (sample.png + grid_*.png) weights %s' % (outdir, weights))


if __name__ == '__main__':
    main()
