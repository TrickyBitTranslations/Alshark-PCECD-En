"""Tier-1 text codec.

Strings are Shift-JIS text mixed with control bytes. In the TSV a control byte is
written as <XX> (hex), matching the markup convention; text is kept faithful both ways
(half-width ASCII stays half-width). widen() bulk-converts ASCII to full-width for authors
who want it. Every row also keeps raw_hex, so untranslated lines round-trip exactly.

The #/$/% style line-break and name codes are left as raw <XX> for now; promote them to
\\n / \\p / {NAME} once the control grammar is documented (see noredist markup notes).
"""
import re

LEAD = lambda c: (0x81 <= c <= 0x9F) or (0xE0 <= c <= 0xEF)
_TOKEN = re.compile(r'<([0-9a-fA-F]{2})>')


def decode(b):
    """Raw entry bytes -> readable string with <XX> control tokens."""
    out = []
    i = 0
    n = len(b)
    while i < n:
        c = b[i]
        if LEAD(c) and i + 1 < n:
            try:
                out.append(b[i:i + 2].decode('shift_jis'))
            except UnicodeDecodeError:
                out.append('<%02x><%02x>' % (c, b[i + 1]))
            i += 2
        elif c < 0x20 or c >= 0x7F:
            out.append('<%02x>' % c)
            i += 1
        else:  # 0x20..0x7e literal ASCII
            out.append(chr(c))
            i += 1
    return ''.join(out)


def widen(s):
    """Helper: convert ASCII letters/digits/punct/space in s to full-width."""
    def w(ch):
        o = ord(ch)
        if ch == ' ':
            return '　'
        if 0x21 <= o <= 0x7E:
            return chr(0xFF00 + (o - 0x20))
        return ch
    return ''.join(w(c) for c in s)


def encode(s):
    """Editable string with <XX> tokens + literal text -> bytes.
    Text is Shift-JIS encoded as written (half-width stays half-width)."""
    out = bytearray()
    pos = 0
    for m in _TOKEN.finditer(s):
        if m.start() > pos:
            out += s[pos:m.start()].encode('shift_jis')
        out += bytes((int(m.group(1), 16),))
        pos = m.end()
    if pos < len(s):
        out += s[pos:].encode('shift_jis')
    return bytes(out)
