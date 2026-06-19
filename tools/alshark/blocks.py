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


def rebuild(entries):
    """entries: list of raw bytes. Return rebuilt block (pointer table + entries),
    recomputing the relative pointer table for whatever lengths the entries are."""
    table_size = 2 * len(entries)
    offs = []
    cur = table_size
    for r in entries:
        offs.append(cur)
        cur += len(r)
    out = bytearray()
    for o in offs:
        out += struct.pack('<H', o)
    for r in entries:
        out += r
    return bytes(out)


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
            last = -1
            for i in range(cnt):
                p = struct.unpack_from('<H', data, base + 2 * i)[0]
                if p < last or not (0xC000 <= p < 0xE000):
                    ptrs = []
                    break
                ptrs.append(p)
                last = p
            if ptrs and ptrs[0] == w0:
                sa = data[base + (ptrs[0] - 0xC000):base + (ptrs[-1] - 0xC000) + 40]
                if sum(1 for x in sa if 0xA1 <= x <= 0xDF) >= cnt:
                    end = base + (ptrs[-1] - 0xC000)
                    while end < n and data[end] != 0x00:
                        end += 1
                    end += 1
                    blocks.append((base, ptrs, end - base))
                    base += ((end - base) // ALIGN + 1) * ALIGN
                    continue
        base += ALIGN
    return blocks


def split_c000(data, base, ptrs, blocklen):
    """Entry bytes for a $C000 block (pointers are absolute $C000-based)."""
    out = []
    for i in range(len(ptrs)):
        s = base + (ptrs[i] - 0xC000)
        e = base + (ptrs[i + 1] - 0xC000) if i + 1 < len(ptrs) else base + blocklen
        out.append(bytes(data[s:e]))
    return out


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
