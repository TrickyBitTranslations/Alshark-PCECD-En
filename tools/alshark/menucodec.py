"""Field-menu / system text codec (bank 0x6B inline strings).

The menu engine ($5702 byte loop at $5748) draws short inline strings stored in the
resident base bank 0x6B: a run of glyphs (2-byte Shift-JIS, or single-byte half-width
kana 0xA1-0xDF) with 0x0D separators between options/lines, NUL-terminated. There is no
pointer table and no #/% control grammar - just glyphs + 0x0D + 0x00. Each run is
introduced in the display list by a small header (e.g. `10 08` option list, `08 08`
message); the header is NOT part of the run and is left untouched.

The bank-0x6D label drawer was patched (see bank6d.s menu_label_char) to render printable
ASCII in the VWF font, so English here is single-byte ASCII (shorter than the SJIS it
replaces -> fits in place, padded with 0x00, no repointing). 0x0D shows as '|' in the TSV.
"""
SEP = 0x0D


def _is_lead(b):
    return 0x81 <= b <= 0x9f or 0xe0 <= b <= 0xef


def _is_trail(b):
    return 0x40 <= b <= 0x7e or 0x80 <= b <= 0xfc


def _glyph_len(d, i):
    """Length (1/2) of a drawable glyph at i, else 0."""
    b = d[i]
    if _is_lead(b) and i + 1 < len(d) and _is_trail(d[i + 1]):
        return 2
    if 0xa1 <= b <= 0xdf:                 # single-byte half-width kana
        return 1
    return 0


def find(data, lo, hi, min_glyphs=2):
    """Yield (offset, run_bytes) for each NUL-terminated drawable run in data[lo:hi].
    run_bytes excludes the 0x00 terminator. A run = glyphs + 0x0D separators, ending at
    0x00, with >= min_glyphs glyphs (filters stray layout bytes that look like one kana)."""
    i = lo
    while i < hi:
        g = _glyph_len(data, i)
        if g:
            start, ng = i, 0
            while i < hi:
                g = _glyph_len(data, i)
                if g:
                    i += g
                    ng += 1
                elif data[i] == SEP:
                    i += 1
                else:
                    break
            if i < hi and data[i] == 0x00 and ng >= min_glyphs:
                yield start, bytes(data[start:i])
            continue
        i += 1


def decode(run):
    """Run bytes -> readable text ('|' = 0x0D separator; <XX> = stray byte)."""
    out, i = [], 0
    while i < len(run):
        b = run[i]
        if b == SEP:
            out.append('|')
            i += 1
        elif _is_lead(b) and i + 1 < len(run) and _is_trail(run[i + 1]):
            out.append(run[i:i + 2].decode('shift_jis', 'replace'))
            i += 2
        elif 0xa1 <= b <= 0xdf:
            out.append(bytes([b]).decode('shift_jis', 'replace'))
            i += 1
        elif 0x20 <= b <= 0x7e:
            out.append(chr(b))
            i += 1
        else:
            out.append('<%02X>' % b)
            i += 1
    return ''.join(out)


def encode(english):
    """English markup -> bytes. ASCII passes through; '|' -> 0x0D separator."""
    out = bytearray()
    for ch in english:
        if ch == '|':
            out.append(SEP)
        else:
            c = ord(ch)
            out.append(c if 0x20 <= c <= 0x7e else 0x3f)   # '?' for anything non-ASCII
    return bytes(out)
