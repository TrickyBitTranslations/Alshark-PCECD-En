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

BANK6B = (0xB000, 0xD000)               # cooked range of bank 0x6B


def export(cooked, out='script/menu.tsv'):
    rows = []
    for off, run in menucodec.find(cooked, *BANK6B):
        rows.append({
            'block_off': '0x%x' % off,
            'str_off': '0x0',
            'speaker': '',
            'text': menucodec.decode(run),
            'raw_hex': (run + b'\x00').hex(),
            'english': '',
            'status': '',
        })
    tsv.write(out, rows)
    print('wrote %s (%d strings)' % (out, len(rows)))


def main():
    work = sys.argv[1] if len(sys.argv) > 1 else 'work'
    cooked = open(os.path.join(work, 'track02.iso'), 'rb').read()
    export(cooked)


if __name__ == '__main__':
    main()
