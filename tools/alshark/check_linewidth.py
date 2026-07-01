"""Line-width simulator + round-trip check for the #-engine dialogue codec.

Walks each merged cutscene entry the way the engine flows text: accumulate glyph px, reset the
pen at line-break ops and `@`, hard-wrap at BOX_PX. Reports the max line px per box and flags
rows that overflow.

Run from repo root:  python3 tools/alshark/check_linewidth.py
"""
import csv
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from alshark import dialogcodec as dc

TSV = os.path.join(os.path.dirname(__file__), '..', '..', 'script', 'cutscene.tsv')


def _op_resets(op_bytes):
    """True if this op resets the render pen to the left margin (a true line break); see
    dialogcodec.RESET_OPS."""
    return op_bytes in dc.RESET_OPS


def line_pxs(entry):
    """Walk a merged entry's tokens, simulate the engine line flow, return the rendered line
    widths (px). A line ends at a reset op or `@`; an over-wide line hard-wraps at BOX_PX like
    the engine and is flagged as an overflow."""
    pens = []          # completed line widths
    pen = 0
    overflowed = False  # did this line need a hard wrap (i.e. exceed BOX_PX)?
    over_lines = []

    def endline():
        nonlocal pen, overflowed
        pens.append((pen, overflowed))
        pen = 0
        overflowed = False

    for t, d in dc.tokenize(entry):
        if t == 'op':
            if _op_resets(d):
                endline()
            continue
        # dlg run: decode to chars, advance pen per glyph, break on @, hard-wrap at BOX_PX
        for ch in dc.decode(d):
            if ch == '@':
                endline()
                continue
            if ch in ('#', '%', '$', '<', '>'):
                # markup that survived into a dlg run counts as zero width ($ name handled below)
                continue
            w = dc._cpx(ch)
            if pen + w > dc.BOX_PX:
                # engine hard-wraps here
                overflowed = True
                endline()
                overflowed = True   # the NEW line is the overflow continuation
            pen += w
    endline()
    return pens


def max_overflow(entry):
    """Return (max_line_px, any_overflow) for an entry."""
    pens = line_pxs(entry)
    mx = max((p for p, _ in pens), default=0)
    over = any(o for _, o in pens)
    return mx, over


def main():
    rows = []
    with open(TSV, encoding='utf-8') as f:
        r = csv.DictReader(f, delimiter='\t')
        for i, row in enumerate(r, start=2):   # tsv line numbers (header is line 1)
            rows.append((i, row))

    n_total = 0
    n_translated = 0
    overflow_rows = []
    roundtrip_fail = []

    for ln, row in rows:
        rawh = (row.get('raw_hex') or '').strip()
        eng = row.get('english') or ''          # NOT stripped: reinsert.py passes it verbatim,
        eng_present = bool(eng.strip())          # and a trailing-space glyph run is a real dlg run
        status = (row.get('status') or '').strip().lower()
        if not rawh:
            continue
        n_total += 1
        try:
            raw = bytes.fromhex(rawh)
        except ValueError:
            continue

        if not eng_present or status in ('ignore', 'skip'):
            # untranslated: merge must be a no-op vs raw (round-trip safety)
            try:
                merged = dc.merge(eng, raw) if eng_present else raw
            except Exception as e:
                roundtrip_fail.append((ln, 'merge raised: %s' % e))
                continue
            if not eng_present and merged != raw:
                roundtrip_fail.append((ln, 'untranslated row changed'))
            continue

        n_translated += 1
        try:
            merged = dc.merge(eng, raw)
        except Exception as e:
            overflow_rows.append((ln, -1, 'merge raised: %s' % e))
            continue
        mx, over = max_overflow(merged)
        if over or mx > dc.BOX_PX:
            overflow_rows.append((ln, mx, row.get('speaker', '')))

    print('rows with raw_hex: %d   translated: %d' % (n_total, n_translated))
    print('round-trip failures (untranslated rows that changed): %d' % len(roundtrip_fail))
    for ln, why in roundtrip_fail:
        print('   line %d: %s' % (ln, why))
    print('OVERFLOW rows (line > BOX_PX=%d after merge): %d' % (dc.BOX_PX, len(overflow_rows)))
    for ln, mx, who in overflow_rows:
        print('   line %d  maxpx=%s  %s' % (ln, mx, who))


if __name__ == '__main__':
    main()
