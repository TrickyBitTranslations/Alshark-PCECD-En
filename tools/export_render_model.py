"""Emit site/data/render.json for the web dialogue simulator.

For every TRANSLATED cutscene line, precompute the display-line model (alshark.render.layout) so the
static site can show a faithful in-game preview with no client-side codec. Also emits `meta` (box
width + VWF widths + name maps) that the JS live-preview (recommendations) consumes so nothing is
hardcoded twice. Runs in CI (site.yml) alongside export_script.

  PYTHONPATH=tools python3 tools/export_render_model.py [work] [out]
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tsv
from alshark import render

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def build(tsv_path):
    lines = {}
    n_ok = n_over = 0
    for r in tsv.read(tsv_path):
        rawh = (r.get('raw_hex') or '').strip()
        en = (r.get('english') or '')
        if not rawh or not en.strip():
            continue
        try:
            model = render.layout(en, bytes.fromhex(rawh))
        except Exception as e:
            # a line that doesn't merge cleanly is a data problem surfaced elsewhere; skip preview
            sys.stderr.write('render skip %s:%s (%s)\n' % (r['block_off'], r['str_off'], e))
            continue
        key = '%s:%s' % (r['block_off'], r['str_off'])
        lines[key] = model
        n_ok += 1
        n_over += any(l['over'] for l in model)
    return lines, n_ok, n_over


def main():
    work = sys.argv[1] if len(sys.argv) > 1 else 'work'
    out = sys.argv[2] if len(sys.argv) > 2 else os.path.join(ROOT, 'site', 'data', 'render.json')
    lines, n_ok, n_over = build(os.path.join(ROOT, 'script', 'cutscene.tsv'))
    doc = {'meta': render.model_meta(), 'lines': lines}
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, 'w', encoding='utf-8') as f:
        json.dump(doc, f, ensure_ascii=False, separators=(',', ':'))
    print('wrote %s (%d lines rendered, %d with an overflow row, %d bytes)'
          % (out, n_ok, n_over, os.path.getsize(out)))


if __name__ == '__main__':
    main()
