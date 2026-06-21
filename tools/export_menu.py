#!/usr/bin/env python3
"""Extract the field-menu / system inline strings (bank 0x6B) -> script/menu.tsv.

These are the menu labels, option lists, pickers, and system messages drawn by the
bank-0x6D label loop ($5748). They live inline in the resident base bank 0x6B
(cooked 0xB000-0xD000 = logical $A000-$BFFF), NUL-terminated glyph runs separated by
0x0D. raw_hex holds the run + its 0x00 terminator (= the writable slot); reinsert pads
English (shorter ASCII) with 0x00 within that slot, so nothing repoints.

Run with PYTHONPATH=tools (or from repo root):  python3 tools/export_menu.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tsv
from alshark import menucodec

# Resident banks that hold field-menu / system inline text, drawn by the bank-0x6D $5748 loop.
# (cooked lo, hi): 0x6A engine messages, 0x6B menu lists + messages, 0x6D render bank (equip/
# status stat labels, skill categories, equip/quit messages, picker + party-name copies).
REGIONS = [(0x9000, 0xb000), (0xb000, 0xd000), (0x15000, 0x17000)]


def export(cooked, out='script/menu.tsv'):
    prev = {}                           # carry over existing english/status by offset
    try:
        for r in tsv.read(out):
            prev[r['block_off']] = (r.get('english', ''), r.get('status', ''))
    except OSError:
        pass
    rows = []
    for lo, hi in REGIONS:
        for off, run in menucodec.find(cooked, lo, hi):
            key = '0x%x' % off
            en, st = prev.get(key, ('', ''))
            rows.append({
                'block_off': key, 'str_off': '0x0', 'speaker': '',
                'text': menucodec.decode(run), 'raw_hex': (run + b'\x00').hex(),
                'english': en, 'status': st,
            })
    tsv.write(out, rows)
    print('wrote %s (%d strings, %d already translated)'
          % (out, len(rows), sum(1 for r in rows if r['english'])))


def main():
    work = sys.argv[1] if len(sys.argv) > 1 else 'work'
    cooked = open(os.path.join(work, 'track02.iso'), 'rb').read()
    export(cooked)


if __name__ == '__main__':
    main()
