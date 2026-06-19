"""Reinsert translated tier-1 script into a patched disc.

Rebuilds each block from script/system1.tsv (english where present, original bytes
otherwise), repoints the table, splices it back into the cooked data track, recomputes
Mode-1 EDC/ECC, and (optionally) builds the CHD.

With no translations the output is byte-identical to the source (lossless round-trip).
A block whose rebuilt size exceeds its original byte slot is flagged, not forced; those
get relocated (see noredist reloc notes) once their loader is mapped.
"""
import argparse
import collections
import os
import shutil
import subprocess

import tsv
from alshark import blocks, textcodec
from alshark.cdecc import fix_mode1

SEC = 2352
DATA = 16
TRACK2 = 3590


def load_blocks(tsv_path):
    """Return {base:int -> [(english, raw_bytes)] in entry order} from the TSV.
    File order is the block's entry order, so rows are kept as read."""
    out = collections.OrderedDict()
    for r in tsv.read(tsv_path):
        out.setdefault(int(r['block_off'], 16), []).append(
            (r.get('english', ''), bytes.fromhex(r['raw_hex'])))
    return out


def entry_bytes(english, raw):
    if not english:
        return raw
    b = textcodec.encode(english)
    if not b.endswith(b'\x00'):
        b += b'\x00'          # entries are 0x00-terminated; keep that invariant
    return b


def build(work, tsv_path):
    """Return (patches, flagged). patches = [(cooked_off, new_bytes)]."""
    cooked = open(os.path.join(work, 'track02.iso'), 'rb').read()
    patches, flagged = [], []
    for base, items in sorted(load_blocks(tsv_path).items()):
        orig = blocks.rebuild([raw for _, raw in items])
        assert cooked[base:base + len(orig)] == orig, f"block {base:#x} not as extracted"
        new = blocks.rebuild([entry_bytes(en, raw) for en, raw in items])
        if new == orig:
            continue
        if len(new) > len(orig):
            flagged.append((base, len(orig), len(new)))
            continue
        patches.append((base, new))      # shorter is fine; original tail left untouched
    return patches, flagged


def apply(patches, extracted, out_bin, out_cue):
    shutil.copyfile(os.path.join(extracted, 'Alshark.bin'), out_bin)
    affected = set()
    with open(out_bin, 'r+b') as f:
        for off, new in patches:
            for i in range(len(new)):
                csec, _ = divmod(off + i, 2048)
                affected.add(TRACK2 + csec)
            csec, ci = divmod(off, 2048)
            f.seek((TRACK2 + csec) * SEC + DATA + ci)
            f.write(new)                  # contiguous; never spans a block past its slot
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
        bad = 0
        for base, items in sorted(load_blocks(args.tsv).items()):
            new = 2 * len(items) + sum(len(entry_bytes(en, raw)) for en, raw in items)
            if new > 0x2000:
                print(f"OVERFLOW block {base:08x}: {new} bytes > 8192 page cap")
                bad += 1
        print(f"check: {bad} block(s) over the 8KB page cap")
        raise SystemExit(1 if bad else 0)

    patches, flagged = build(args.work, args.tsv)
    print(f"{len(patches)} block(s) changed, {len(flagged)} flagged for relocation")
    for base, o, n in flagged:
        print(f"  OVERFLOW block {base:08x}: {o} -> {n} bytes (+{n - o})")
    if not patches:
        print("no in-place changes (lossless round-trip)")
        return

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
