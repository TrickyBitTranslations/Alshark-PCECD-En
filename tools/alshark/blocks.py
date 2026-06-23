"""Tier-1 map/event script: 16-bit LE relative pointer-table blocks.

pointer[0] is the table size in bytes, so pointer[0]/2 is the entry count. Entries
follow the table, each ending in 0x00. Blocks sit at 0x800-aligned offsets, separated
by unrelated map/tile data (not free space).
"""
import struct

ALIGN = 0x800


def _hira_count(b):
    """Count 2-byte SJIS hiragana (0x82 9f..f1) as a cheap text-likeness signal."""
    c = 0
    i = 0
    while i < len(b) - 1:
        if b[i] == 0x82 and 0x9F <= b[i + 1] <= 0xF1:
            c += 1
            i += 2
        else:
            i += 1
    return c


def find_blocks(data):
    """Return [(base, ptrs, blocklen)] for every valid pointer-table block."""
    n = len(data)
    blocks = []
    seen = 0
    for base in range(0, n, ALIGN):
        if base < seen:
            continue
        if base + 2 > n:
            break
        p0 = struct.unpack_from('<H', data, base)[0]
        if p0 < 4 or p0 > 0x1800 or p0 % 2:
            continue
        count = p0 // 2
        if count < 2 or count > 400:
            continue
        ptrs = []
        last = -1
        ok = True
        for i in range(count):
            v = struct.unpack_from('<H', data, base + 2 * i)[0]
            if v < last or v > 0x8000:
                ok = False
                break
            ptrs.append(v)
            last = v
        if not ok or len(ptrs) < count or ptrs[0] != p0:
            continue
        if _hira_count(data[base:base + ptrs[-1] + 2]) < count:
            continue
        # block length = end of last entry: first 0x00 at/after ptrs[-1]
        end = base + ptrs[-1]
        while end < n and data[end] != 0x00:
            end += 1
        end += 1  # include terminator
        blocks.append((base, ptrs, end - base))
        seen = base + ptrs[-1]
    return blocks


def split_entries(data, base, ptrs, blocklen):
    """Return raw bytes for each entry (control codes + text + 0x00 terminator)."""
    out = []
    for i in range(len(ptrs)):
        s = base + ptrs[i]
        e = base + ptrs[i + 1] if i + 1 < len(ptrs) else base + blocklen
        out.append(bytes(data[s:e]))
    return out


def _rebuild(entries, offs, ptr_base):
    """Lay out a pointer-table block. entries are in INDEX (pointer-table) order. If offs is
    given (each entry's original str_off) strings are placed in their original PHYSICAL order,
    so an unchanged block round-trips byte-identical even when its pointer table is non-monotonic
    (strings stored out of index order); otherwise strings go in index order. Pointers carry
    ptr_base (0 = relative tier-1, 0xC000 = #-engine)."""
    n = len(entries)
    table_size = 2 * n
    order = sorted(range(n), key=lambda i: offs[i]) if offs is not None else list(range(n))
    pos = [0] * n
    cur = table_size
    for i in order:
        pos[i] = cur
        cur += len(entries[i])
    out = bytearray(cur)
    for i in range(n):
        struct.pack_into('<H', out, 2 * i, ptr_base + pos[i])
    for i in range(n):
        out[pos[i]:pos[i] + len(entries[i])] = entries[i]
    return bytes(out)


def rebuild(entries, offs=None):
    """Rebuilt relative-pointer block (tier-1 map/event). See _rebuild."""
    return _rebuild(entries, offs, 0)


def find_c000_blocks(data):
    """Find #-engine dialogue blocks: pointer tables of ABSOLUTE $C000-based addresses.
    word[0] is the first pointer (== table end), so (word[0]-0xC000)/2 == entry count.
    Returns [(base, ptrs, blocklen)] like find_blocks but with $C000-relative pointers."""
    n = len(data)
    blocks = []
    base = 0
    while base < n:
        w0 = struct.unpack_from('<H', data, base)[0]
        ok = 0xC002 <= w0 <= 0xC800 and w0 % 2 == 0
        cnt = (w0 - 0xC000) // 2 if ok else 0
        if ok and 2 <= cnt <= 400:
            ptrs = []
            for i in range(cnt):
                p = struct.unpack_from('<H', data, base + 2 * i)[0]
                if not (0xC000 <= p < 0xE000):     # valid load-page pointer; NOT required to be
                    ptrs = []                       # sorted - some blocks store strings out of index
                    break                           # order (e.g. 0x7d5000 swaps its last two entries)
                ptrs.append(p)
            if ptrs and ptrs[0] == w0:
                hi = max(ptrs) - 0xC000             # last string physically (may not be ptrs[-1])
                sa = data[base + (ptrs[0] - 0xC000):base + hi + 40]
                if sum(1 for x in sa if 0xA1 <= x <= 0xDF) >= cnt:
                    end = base + hi
                    while end < n and data[end] != 0x00:
                        end += 1
                    end += 1
                    blocks.append((base, ptrs, end - base))
                    base += ((end - base) // ALIGN + 1) * ALIGN
                    continue
        base += ALIGN
    return blocks


def split_c000(data, base, ptrs, blocklen):
    """Entry bytes for a $C000 block (pointers are absolute $C000-based). Pointers are not
    guaranteed sorted, so an entry ends at the next-higher offset physically (or block end),
    NOT at ptrs[i+1] - that keeps out-of-order blocks (e.g. 0x7d5000) split correctly while
    preserving index order (entry i == ptrs[i])."""
    offs = sorted(p - 0xC000 for p in ptrs)
    out = []
    for p in ptrs:
        s = p - 0xC000
        nxt = [o for o in offs if o > s]
        e = min(nxt) if nxt else blocklen
        out.append(bytes(data[base + s:base + e]))
    return out


def rebuild_c000(entries, offs=None):
    """Rebuilt $C000 absolute-pointer block (#-engine). See _rebuild; passing offs keeps
    out-of-order blocks (e.g. 0x7d5000, whose pointer table is non-monotonic) byte-identical
    when unchanged."""
    return _rebuild(entries, offs, 0xC000)


def layout(data):
    """Return per-block layout info: base, used length, gap to next block.
    The gap is occupied by unrelated map data, so it is NOT growth headroom."""
    bs = find_blocks(data)
    rows = []
    for i, (base, ptrs, blen) in enumerate(bs):
        nxt = bs[i + 1][0] if i + 1 < len(bs) else None
        gap = (nxt - (base + blen)) if nxt is not None else None
        rows.append({'base': base, 'entries': len(ptrs), 'used': blen,
                     'next': nxt, 'gap': gap})
    return rows
