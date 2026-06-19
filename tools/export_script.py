"""Export the game script to script/*.tsv, one row per string entry.

Two tiers:
  system1.tsv   map/event blocks (relative pointer tables)
  cutscene.tsv  #-engine dialogue blocks ($C000 absolute pointer tables)

Columns: block_off, str_off, speaker, text (<XX> tokens), raw_hex, english, status.
Re-running carries over english + status keyed on (block_off, str_off), so it never
wipes translator work.
"""
import argparse
import json
import os

import tsv
from alshark import blocks, textcodec, dialogcodec

PAGE = 0x2000   # a block loads into one 8KB logical page

# (output, block finder, entry splitter, codec, str_off bias)
TIERS = [
    ("script/system1.tsv", blocks.find_blocks, blocks.split_entries, textcodec, 0),
    ("script/cutscene.tsv", blocks.find_c000_blocks, blocks.split_c000, dialogcodec, 0xC000),
]


def block_budget(data, base, blen):
    """Max in-place size for a block: its bytes plus the trailing zero padding before
    the next data (scene code / map data), capped at the 8KB page. Needs the disc, so
    it is computed here and committed (script/budgets.json) for the CI checks."""
    e = base + blen
    z = 0
    while e + z < len(data) and data[e + z] == 0:
        z += 1
    return min(blen + z, PAGE)


def export(data, out, find, split, codec, bias, budgets):
    carry = {}
    if os.path.exists(out):
        for r in tsv.read(out):
            carry[(r['block_off'], r['str_off'])] = (r['english'], r['status'])
    rows = []
    bs = find(data)
    for base, ptrs, blen in bs:
        budgets['%s:0x%x' % (os.path.basename(out), base)] = block_budget(data, base, blen)
        for i, raw in enumerate(split(data, base, ptrs, blen)):
            bo, so = '0x%x' % base, '0x%x' % (ptrs[i] - bias)
            en, st = carry.get((bo, so), ('', ''))
            rows.append({
                'block_off': bo, 'str_off': so, 'speaker': '',
                'text': codec.decode(raw), 'raw_hex': raw.hex(),
                'english': en, 'status': st or ('ignore' if raw == b'\x00' else ''),
            })
    tsv.write(out, rows)
    print(f"wrote {out}: {len(rows)} rows from {len(bs)} blocks")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--work', default='work')
    args = ap.parse_args()
    data = open(os.path.join(args.work, 'track02.iso'), 'rb').read()
    budgets = {}
    for out, find, split, codec, bias in TIERS:
        export(data, out, find, split, codec, bias, budgets)
    with open('script/budgets.json', 'w') as f:
        json.dump(budgets, f, separators=(',', ':'), sort_keys=True)
    print(f"wrote script/budgets.json: {len(budgets)} block budgets")


if __name__ == '__main__':
    main()
