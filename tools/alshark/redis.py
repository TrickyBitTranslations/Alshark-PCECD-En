#!/usr/bin/env python3
"""Static RE helper for the Alshark menu banks - locate data, find xrefs, disassemble.

WHY THIS EXISTS: the in-game menus CACHE draws (only render on a fresh load) and REMAP banks
mid-draw, so live debugger breakpoints on logical addresses frequently never fire and live
disassembly doesn't match the running PC. Chasing a render with breakpoints burns huge effort.
The disc bytes + a disassembler are the reliable ground truth. Reach for THIS first; use the
emulator only to CONFIRM a finished hypothesis (with a save-state for retryable fresh draws).

  PYTHONPATH=tools python3 tools/alshark/redis.py find <hex|@text>     # locate bytes / SJIS in banks
  PYTHONPATH=tools python3 tools/alshark/redis.py xref <logical_hex>   # JSR/JMP callers of an address
  PYTHONPATH=tools python3 tools/alshark/redis.py dis  <bank> <start_hex> [end_hex]  # disassemble

Banks (cooked start, logical org): 6a=0x9000/$4000  6b=0xb000/$6000  6d=0x15000/$4000.
Workflow: find the data -> xref the routine that reads it / the render entry -> dis each caller
loop -> spot the fixed advance or the bug -> apply the established hook (see vwf-implementation.md).
"""
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ISO = os.path.join(ROOT, 'work', 'track02.iso')
HUC = os.path.join(ROOT, 'rebuild', 'tools', 'huc6280dis.py')
# name: (cooked_start, length, logical_org)
BANKS = {'6a': (0x9000, 0x2000, 0x4000), '6b': (0xb000, 0x2000, 0x6000), '6d': (0x15000, 0x2000, 0x4000)}


def _data():
    return open(ISO, 'rb').read()


def _dis(bank, start, end):
    """Disassemble a bank logical range via the huc6280dis CLI (address+bytes+mnemonic output)."""
    s, ln, org = BANKS[bank]
    p = os.path.join(tempfile.gettempdir(), 'alshark_%s.bin' % bank)
    open(p, 'wb').write(_data()[s:s + ln])
    r = subprocess.run([sys.executable, HUC, p, '%x' % org, '%x' % start, '%x' % end],
                       capture_output=True, text=True)
    return r.stdout


def _bank_of(cooked):
    for n, (s, ln, org) in BANKS.items():
        if s <= cooked < s + ln:
            return n, org + (cooked - s)
    return None, None


def cmd_find(arg):
    data = _data()
    pat = arg[1:].encode('shift_jis') if arg.startswith('@') else bytes.fromhex(arg)
    i, n = 0, 0
    while n < 64:
        i = data.find(pat, i)
        if i == -1:
            break
        bank, log = _bank_of(i)
        loc = '%s:$%04x' % (bank, log) if bank else '(non-bank)'
        print('cooked 0x%-7x  %s' % (i, loc))
        i += 1
        n += 1


def cmd_xref(arg):
    """Find JSR ($20) / JMP ($4C) to a logical target, in the code banks; show a disasm snippet
    so display-list DATA that merely looks like an opcode is easy to reject."""
    tgt = int(arg, 16)
    data = _data()
    lo, hi = tgt & 0xff, tgt >> 8
    for op, nm in ((0x20, 'JSR'), (0x4c, 'JMP')):
        pat = bytes([op, lo, hi])
        i = 0
        while True:
            i = data.find(pat, i)
            if i == -1:
                break
            bank, log = _bank_of(i)
            if bank:
                snip = [ln for ln in _dis(bank, log, log + 3).splitlines() if ln.strip()]
                ctx = snip[0].split(None, 2)[-1].strip() if snip else ''
                print('%s $%04x  <- %s:$%04x   %s' % (nm, tgt, bank, log, ctx))
            i += 1


def cmd_dis(bank, start, end=None):
    a = int(start, 16)
    b = int(end, 16) if end else a + 0x40
    print(_dis(bank.lower(), a, b), end='')


def main():
    a = sys.argv[1:]
    if not a:
        print(__doc__)
        return
    if a[0] == 'find':
        cmd_find(a[1])
    elif a[0] == 'xref':
        cmd_xref(a[1])
    elif a[0] == 'dis':
        cmd_dis(a[1], a[2], a[3] if len(a) > 3 else None)
    else:
        print(__doc__)


if __name__ == '__main__':
    main()
