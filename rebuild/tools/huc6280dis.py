#!/usr/bin/env python3
"""Minimal HuC6280 disassembler that emits wla-dx-syntax asm.

Opcode table (huc6280_ops.json) is wla-dx's own instruction table, so output
re-assembles to the same bytes. Verify with build.py (byte-identical guard);
this is a drafting aid, not a source of truth.

wla quirk: relative branches (BNE/BBR/...) need a LABEL target, not a raw address
(absolute JMP/JSR take raw addresses fine). So we two-pass: place labels at branch
targets that land on an instruction boundary; branches whose target is out of range
or misaligned (mostly disassembled-as-data) are emitted as raw `.db` bytes.

  huc6280dis.py <bin> <org_hex> [start_hex] [end_hex]   # listing
"""
import json
import os
import sys

OPS = json.load(open(os.path.join(os.path.dirname(__file__), 'huc6280_ops.json')))
ALWAYS_ABS = {'JMP', 'JSR'}


def s8(b):
    return b - 256 if b >= 128 else b


def _decode(data, i):
    """Return (length, opcode_entry_or_None, rawbytes) for the instr at index i."""
    op = data[i]
    e = OPS.get('%02X' % op)
    if e is None or i + e['len'] > len(data):
        return 1, None, [op]
    return e['len'], e, list(data[i:i + e['len']])


def _target(e, raw, pc):
    """Branch/BBR target address, or None if not a relative-branch instr."""
    if e['type'] == 9:
        return (pc + 2 + s8(raw[1])) & 0xFFFF
    if e['type'] == 8:
        return (pc + 3 + s8(raw[2])) & 0xFFFF
    return None


def fmt(e, raw, pc, label=None):
    """Format one instruction. label = target label name for branches."""
    mnem, typ = e['tmpl'], e['type']
    base, _, dec = mnem.partition(' ')
    if typ == 9:
        return '%-5s %s' % (base, label)
    if typ == 8:
        return '%-5s $%02X,%s' % (base, raw[1], label)
    if typ == 4:
        a, b, c = (raw[1] | raw[2] << 8, raw[3] | raw[4] << 8, raw[5] | raw[6] << 8)
        return '%-5s $%04X,$%04X,$%04X' % (base, a, b, c)
    if typ in (5, 6):
        if typ == 6 and (raw[2] | raw[3] << 8) <= 0xFF:
            return None                  # abs TST, no .W form -> caller emits .db
        addr = '$%02X' % raw[2] if typ == 5 else '$%04X' % (raw[2] | raw[3] << 8)
        tail = ',X' if dec.endswith(',X') else ''
        return '%-5s #$%02X,%s%s' % (base, raw[1], addr, tail)
    if typ == 7:
        out = dec.replace('#x', '#$%02X' % raw[1]).replace('x', '$%02X' % raw[1])
        return ('%-5s %s' % (base, out)) if dec else base
    if typ == 2:
        val = raw[1] | raw[2] << 8
        if val <= 0xFF and '(' not in dec and base not in ALWAYS_ABS:
            base += '.W'
        return '%-5s %s' % (base, dec.replace('?', '$%04X' % val))
    return base


def decode_all(data, org, start=None, end=None):
    """Linear decode -> list of dicts {pc,len,e,raw}. boundary set + labelable map."""
    i = (start - org) if start is not None else 0
    stop = (end - org) if end is not None else len(data)
    lo, hi = org + i, org + stop
    instrs, boundary = [], set()
    while i < stop:
        n, e, raw = _decode(data, i)
        pc = org + i
        boundary.add(pc)
        instrs.append({'pc': pc, 'len': n, 'e': e, 'raw': raw})
        i += n
    labels = {}
    for ins in instrs:
        if ins['e'] is None:
            continue
        t = _target(ins['e'], ins['raw'], ins['pc'])
        if t is not None and lo <= t < hi and t in boundary:
            labels[t] = 'L%04X' % t
    return instrs, labels


def to_source(data, org, start=None, end=None):
    """Return asm lines (labels + instructions) for the range."""
    instrs, labels = decode_all(data, org, start, end)
    out = []
    for ins in instrs:
        pc, e, raw = ins['pc'], ins['e'], ins['raw']
        if pc in labels:
            out.append(labels[pc] + ':')
        if e is None:
            out.append('.db $%02X' % raw[0])
            continue
        t = _target(e, raw, pc)
        text = None if (t is not None and t not in labels) else fmt(e, raw, pc, labels.get(t))
        if text is None:                              # unlabelable branch / unencodable
            text = '.db ' + ','.join('$%02X' % b for b in raw)
        out.append(text)
    return out


def main():
    data = open(sys.argv[1], 'rb').read()
    org = int(sys.argv[2], 16)
    start = int(sys.argv[3], 16) if len(sys.argv) > 3 else None
    end = int(sys.argv[4], 16) if len(sys.argv) > 4 else None
    instrs, labels = decode_all(data, org, start, end)
    for ins in instrs:
        pc, e, raw = ins['pc'], ins['e'], ins['raw']
        lbl = (labels[pc] + ':') if pc in labels else ''
        if e is None:
            text = '.db $%02X' % raw[0]
        else:
            t = _target(e, raw, pc)
            text = None if (t is not None and t not in labels) else fmt(e, raw, pc, labels.get(t))
            if text is None:
                text = '.db ' + ','.join('$%02X' % b for b in raw)
        print('%-8s $%04X: %-12s %s' % (lbl, pc,
              ' '.join('%02X' % b for b in raw), text))


if __name__ == '__main__':
    main()
