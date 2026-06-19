"""#-engine dialogue codec (the $C000-pointer blocks).

Text is 2-byte Shift-JIS (kanji/katakana) plus single-byte hiragana: bytes 0xA1-0xDF are
the half-width-katakana codes with the font remapped to hiragana glyphs, so they decode
to hiragana. Control bytes are kept as [XX] tokens; the #/$/% grammar is not decoded yet.
Every row also stores raw_hex, so untranslated lines round-trip byte-exact regardless.

English is written as plain ASCII (1 byte per char); the font patch (alshark.fontpatch)
renders 0x20-0x7E as text, and encode() word-wraps it to the dialogue box. Avoid a bare
# $ % @ in english since those are the engine's control bytes.
"""
import re
import unicodedata

LEAD = lambda c: (0x81 <= c <= 0x9F) or (0xE0 <= c <= 0xEF)
_TOKEN = re.compile(r'<([0-9a-fA-F]{2})>')

BOX_CELLS = 18                       # the dialogue box is 18 full-width glyphs wide
_WTOK = re.compile(r'<[0-9a-fA-F]{2}>|[#%$@<>]|\s+|[^\s#%$@<>]+')


def wrap(s, width=BOX_CELLS, name_w=6):
    """Insert @ line-breaks at word boundaries so each rendered line fits the box; the
    engine otherwise hard-wraps mid-word. Markup (<XX>, # % < >) counts as zero width,
    $ name inserts as an approximate width, <05> (text start) and an existing @ reset the
    line. A line already under width keeps any author-placed @, so manual wrapping wins."""
    out, col, space = [], 0, ''
    for a in _WTOK.findall(s):
        if a == '@':
            out.append('@'); col = 0; space = ''
        elif a == '$':
            if space and col:
                out.append(space); col += len(space)
            space = ''
            out.append('$'); col += name_w
        elif _TOKEN.fullmatch(a):
            out.append(a)
            if a == '<05>':              # text-start marker begins a fresh line
                col = 0; space = ''
        elif a in ('#', '%', '<', '>'):
            out.append(a)
        elif a.isspace():
            space = a
        else:                            # a visible word
            if col and col + len(space) + len(a) > width:
                out.append('@'); col = 0; space = ''
            elif space:
                out.append(space); col += len(space)
            space = ''
            out.append(a); col += len(a)
    return ''.join(out)


def _sb_hira(b):
    full = unicodedata.normalize('NFKC', bytes([b]).decode('shift_jis'))
    return ''.join(chr(ord(c) - 0x60) if 0x30A1 <= ord(c) <= 0x30F6 else c for c in full)


# reverse map: hiragana letter (or dakuten mark) -> its single-byte code, so encode is the
# inverse of decode for hiragana. Only the kana slots are remapped; punctuation in the
# 0xA1-0xA5 range stays as its 2-byte Shift-JIS form (that is how the source stores it).
_SB = {}
for _b in range(0xA1, 0xE0):
    _s = _sb_hira(_b)
    if len(_s) == 1 and (0x3041 <= ord(_s) <= 0x3096 or ord(_s) in (0x309B, 0x309C)):
        _SB.setdefault(_s, _b)
_SB.setdefault('゙', 0xDE)   # combining voiced mark -> dakuten byte
_SB.setdefault('゚', 0xDF)   # combining semi-voiced mark -> handakuten byte


def decode(b):
    out = []
    i = 0
    while i < len(b):
        c = b[i]
        if LEAD(c) and i + 1 < len(b):
            try:
                out.append(b[i:i + 2].decode('shift_jis'))
            except UnicodeDecodeError:
                out.append('<%02x><%02x>' % (c, b[i + 1]))
            i += 2
        elif 0xA1 <= c <= 0xDF:
            out.append(_sb_hira(c))
            i += 1
        elif 0x20 <= c <= 0x7E:
            out.append(chr(c))          # ASCII: # $ % control markers and their args
            i += 1
        else:
            out.append('<%02x>' % c)
            i += 1
    return ''.join(out)


def _enc_text(seg):
    out = bytearray()
    for ch in seg:
        if ch in _SB:
            out.append(_SB[ch])          # hiragana -> single-byte (engine form)
        else:
            out += ch.encode('shift_jis')
    return bytes(out)


def encode(s):
    s = wrap(s)
    out = bytearray()
    pos = 0
    for m in _TOKEN.finditer(s):
        if m.start() > pos:
            out += _enc_text(s[pos:m.start()])
        out += bytes((int(m.group(1), 16),))
        pos = m.end()
    if pos < len(s):
        out += _enc_text(s[pos:])
    return bytes(out)
