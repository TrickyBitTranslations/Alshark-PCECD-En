"""Conformance: the browser render.js must reproduce the Python engine model exactly.

Runs alshark.render.layout (source of truth) and site/render.js (via node) over every cutscene line,
and diffs the display-line model. Non-ASCII glyphs are normalized to '?' on both sides (they are
width-equivalent placeholders in JS and never appear in an English run), so this asserts the wrap /
line-break / name-insert fidelity that the preview depends on. Exit 1 on any drift.

  python3 tools/test_render_conformance.py        # needs `node` on PATH
"""
import json
import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__))))
import tsv
from alshark import render

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def norm(model):
    if model is None:
        return None
    return [{'text': ''.join(c if ord(c) < 128 else '?' for c in ln['text']),
             'px': ln['px'], 'over': ln['over']} for ln in model]


def main():
    rows = [r for r in tsv.read(os.path.join(ROOT, 'script', 'cutscene.tsv'))
            if (r.get('raw_hex') or '').strip() and (r.get('english') or '').strip()]
    inp = {'meta': render.model_meta(), 'lines': []}
    py = []
    for r in rows:
        try:
            m = render.layout(r['english'], bytes.fromhex(r['raw_hex']))
        except Exception:
            m = None
        py.append(norm(m))
        inp['lines'].append({'english': r['english'], 'raw_hex': r['raw_hex']})

    with tempfile.NamedTemporaryFile('w', suffix='.json', delete=False, encoding='utf-8') as f:
        json.dump(inp, f, ensure_ascii=False)
        path = f.name
    try:
        raw = subprocess.check_output(['node', os.path.join(ROOT, 'site', 'render.js'), path])
    finally:
        os.unlink(path)
    js = [norm(m) for m in json.loads(raw)]

    bad = 0
    for i, (a, b) in enumerate(zip(py, js)):
        if a != b:
            bad += 1
            if bad <= 6:
                en = inp['lines'][i]['english'][:48]
                print('MISMATCH #%d  %r' % (i, en))
                print('  py:', a if a is None else a[:4])
                print('  js:', b if b is None else b[:4])
    print('render conformance: checked %d lines, %d mismatch(es)' % (len(py), bad))
    sys.exit(1 if bad else 0)


if __name__ == '__main__':
    main()
