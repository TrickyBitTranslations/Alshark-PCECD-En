"""Reinsert translated script into a patched disc.

Rebuilds each block from its TSV (english where present, original bytes otherwise),
repoints the table, splices it into the cooked data track, recomputes Mode-1 EDC/ECC,
and (optionally) builds the CHD. Handles both tiers:
  system1.tsv   relative-pointer blocks, 0x00-terminated entries
  cutscene.tsv  $C000 absolute-pointer blocks (#-engine)

With no translations the output is byte-identical to the source (lossless round-trip).
A block whose rebuilt size exceeds its original byte slot is flagged, not forced; those
get relocated (proven recno-patch, see noredist reloc notes) once their loader is mapped.
"""
import argparse
import collections
import json
import os
import shutil
import subprocess

import tsv
from alshark import blocks, textcodec, dialogcodec, fontpatch
from alshark.cdecc import fix_mode1

SEC = 2352
DATA = 16
TRACK2 = 3590
PAGE = 0x2000


def load_budgets():
    """{tsvname:0xblock -> max in-place bytes} committed by export_script (the trailing
    free padding before scene code / next data). Falls back to the 8KB page."""
    try:
        return json.load(open('script/budgets.json'))
    except OSError:
        return {}


def budget_for(budgets, tsv_path, base):
    return budgets.get('%s:0x%x' % (os.path.basename(tsv_path), base), PAGE)

# tsv name -> (rebuild fn, codec, append 0x00 terminator)
TIERS = {
    'system1.tsv': (blocks.rebuild, textcodec, True),
    'cutscene.tsv': (blocks.rebuild_c000, dialogcodec, False),
}


def tier_for(tsv_path):
    return TIERS.get(os.path.basename(tsv_path), TIERS['system1.tsv'])


def load_blocks(tsv_path):
    """{base:int -> [(english, raw_bytes)] in entry order}. File order is entry order."""
    out = collections.OrderedDict()
    for r in tsv.read(tsv_path):
        out.setdefault(int(r['block_off'], 16), []).append(
            (r.get('english', ''), bytes.fromhex(r['raw_hex'])))
    return out


def entry_bytes(english, raw, codec, auto_term):
    if not english:
        return raw
    b = codec.encode(english)
    if auto_term and not b.endswith(b'\x00'):
        b += b'\x00'
    return b


def build(work, tsv_path):
    """Return (patches, flagged). patches = [(cooked_off, new_bytes)]."""
    rebuild, codec, auto_term = tier_for(tsv_path)
    budgets = load_budgets()
    cooked = open(os.path.join(work, 'track02.iso'), 'rb').read()
    patches, flagged = [], []
    for base, items in sorted(load_blocks(tsv_path).items()):
        orig = rebuild([raw for _, raw in items])
        assert cooked[base:base + len(orig)] == orig, f"block {base:#x} not as extracted"
        new = rebuild([entry_bytes(en, raw, codec, auto_term) for en, raw in items])
        if new == orig:
            continue
        limit = budget_for(budgets, tsv_path, base)
        if len(new) > limit:
            flagged.append((base, limit, len(new)))
            continue
        patches.append((base, new))      # grows only into free padding; never past it
    return patches, flagged


def apply(patches, extracted, out_bin, out_cue):
    shutil.copyfile(os.path.join(extracted, 'Alshark.bin'), out_bin)
    affected = set()
    with open(out_bin, 'r+b') as f:
        for off, new in patches:
            for i, b in enumerate(new):   # per-byte: a patch may span 2048-byte sectors
                csec, ci = divmod(off + i, 2048)
                rs = TRACK2 + csec
                affected.add(rs)
                f.seek(rs * SEC + DATA + ci)
                f.write(bytes([b]))
        for rs in sorted(affected):
            f.seek(rs * SEC)
            s = bytearray(f.read(SEC))
            fix_mode1(s)
            f.seek(rs * SEC)
            f.write(s)
    shutil.copyfile(os.path.join(extracted, 'Alshark.cue'), out_cue)
    return affected


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--work', default='work')
    ap.add_argument('--tsv', default='script/system1.tsv')
    ap.add_argument('--extracted', default='extracted')
    ap.add_argument('--out', default='build')
    ap.add_argument('--chd', action='store_true', help='also build the CHD')
    ap.add_argument('--check', action='store_true',
                    help='fit-check the TSV (no game data needed); exit 1 on overflow')
    args = ap.parse_args()

    if args.check:                       # CI backstop: fit check from the TSV alone
        _, codec, auto_term = tier_for(args.tsv)
        budgets = load_budgets()
        bad = 0
        for base, items in sorted(load_blocks(args.tsv).items()):
            new = 2 * len(items) + sum(
                len(entry_bytes(en, raw, codec, auto_term)) for en, raw in items)
            limit = budget_for(budgets, args.tsv, base)
            if new > limit:
                print(f"OVERFLOW block {base:08x}: {new} bytes > {limit} budget")
                bad += 1
        print(f"check {os.path.basename(args.tsv)}: {bad} block(s) over budget")
        raise SystemExit(1 if bad else 0)

    block_patches, flagged = build(args.work, args.tsv)
    print(f"{len(block_patches)} block(s) changed, {len(flagged)} flagged for relocation")
    for base, o, n in flagged:
        print(f"  OVERFLOW block {base:08x}: {o} -> {n} bytes (+{n - o})")

    # the font patch (single-byte ASCII -> text) is always part of a built disc
    patches = block_patches + fontpatch.patches()
    os.makedirs(args.out, exist_ok=True)
    out_bin = os.path.join(args.out, 'Alshark.bin')
    out_cue = os.path.join(args.out, 'Alshark.cue')
    aff = apply(patches, args.extracted, out_bin, out_cue)
    print(f"wrote {out_bin} ({len(aff)} sectors refreshed)")
    if args.chd:
        chd = os.path.join(args.out, 'Alshark (patched).chd')
        subprocess.run(['chdman', 'createcd', '-i', out_cue, '-o', chd, '-f'], check=True)
        print(f"wrote {chd}")


if __name__ == '__main__':
    main()
