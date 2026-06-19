"""Export the game script to script/*.tsv, one row per string entry.

Two tiers:
  system1.tsv   map/event blocks (relative pointer tables)
  cutscene.tsv  #-engine dialogue blocks ($C000 absolute pointer tables)

Columns: block_off, str_off, speaker, text (<XX> tokens), raw_hex, english, status.
Re-running carries over english + status keyed on (block_off, str_off), so it never
wipes translator work.
"""
import argparse
import os

import tsv
from alshark import blocks, textcodec, dialogcodec

# (output, block finder, entry splitter, codec, str_off bias)
TIERS = [
    ("script/system1.tsv", blocks.find_blocks, blocks.split_entries, textcodec, 0),
    ("script/cutscene.tsv", blocks.find_c000_blocks, blocks.split_c000, dialogcodec, 0xC000),
]


def export(data, out, find, split, codec, bias):
    carry = {}
    if os.path.exists(out):
        for r in tsv.read(out):
            carry[(r['block_off'], r['str_off'])] = (r['english'], r['status'])
    rows = []
    bs = find(data)
    for base, ptrs, blen in bs:
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
    for out, find, split, codec, bias in TIERS:
        export(data, out, find, split, codec, bias)


if __name__ == '__main__':
    main()
