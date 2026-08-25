"""Tier-1 text codec.

Strings are Shift-JIS text mixed with control bytes. In the TSV a control byte is
written as <XX> (hex), matching the markup convention; text is kept faithful both ways
(half-width ASCII stays half-width). widen() bulk-converts ASCII to full-width for authors
who want it. Every row also keeps raw_hex, so untranslated lines round-trip exactly.

The #/$/% style line-break and name codes are left as raw <XX> for now; promote them to
\\n / \\p / {NAME} once the control grammar is fully documented (see docs/markup.md).
"""
import re

LEAD = lambda c: (0x81 <= c <= 0x9F) or (0xE0 <= c <= 0xEF)
_TOKEN = re.compile(r'<([0-9a-fA-F]{2})>')

# Row 13 (0x8740-0x879C) is NEC's special-character row: roman numerals, circled digits,
# unit abbreviations, No./TEL. Python's shift_jis omits it, so those bytes used to surface
# in the TSV as two <XX> tokens - which reads as mojibake to a translator, and made the
# suggestion validator demand that half a character be "preserved unchanged".
#
# cp932 has the row, but is not a safe blanket swap: it also remaps wave dash and minus
# (54 rows across the TSVs), breaking their byte-exact round-trip. So take from cp932 only
# the pairs shift_jis cannot decode AND whose character shift_jis cannot re-encode. That
# excludes row 13's duplicates of JIS row 2 (the math symbols), which have two possible
# encodings and so stay escaped - one byte sequence per character, round-trip preserved.
NEC_ROW = {}
for _lo in range(0x40, 0x9D):
    _pair = bytes((0x87, _lo))
    try:
        _ch = _pair.decode('cp932')
    except UnicodeDecodeError:
        continue
    try:
        _ch.encode('shift_jis')
    except UnicodeEncodeError:
        NEC_ROW[_pair] = _ch
NEC_REV = {v: k for k, v in NEC_ROW.items()}


def sjis_encode(text):
    """Shift-JIS encode, routing the NEC row-13 characters back to their exact bytes."""
    out = bytearray()
    for ch in text:
        pair = NEC_REV.get(ch)
        out += pair if pair is not None else ch.encode('shift_jis')
    return bytes(out)


def decode(b):
    """Raw entry bytes -> readable string with <XX> control tokens."""
    out = []
    i = 0
    n = len(b)
    while i < n:
        c = b[i]
        if LEAD(c) and i + 1 < n:
            pair = b[i:i + 2]
            try:
                out.append(pair.decode('shift_jis'))
            except UnicodeDecodeError:
                ch = NEC_ROW.get(pair)
                out.append(ch if ch is not None else '<%02x><%02x>' % (c, b[i + 1]))
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
            out += sjis_encode(s[pos:m.start()])
        out += bytes((int(m.group(1), 16),))
        pos = m.end()
    if pos < len(s):
        out += sjis_encode(s[pos:])
    return bytes(out)
