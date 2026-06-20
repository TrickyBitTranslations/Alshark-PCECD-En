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

# VWF advance widths (px) for ASCII 0x20-0x7E; the render hook advances the pen by these per
# glyph (Japanese/full-width chars use FULL_PX). fontgen.py regenerates fontwidths.py whenever
# the font is swapped; the fallback keeps wrap working if it hasn't been generated yet.
try:
    from alshark.fontwidths import WIDTHS as VWF_WIDTHS
except ImportError:
    VWF_WIDTHS = [4] * 95
FULL_PX = 12                         # engine full-width advance (6A:$8115 += $0C)
BOX_PX = 216                         # dialogue box width: 18 full-width cells x 12 px
_WTOK = re.compile(r'<[0-9a-fA-F]{2}>|[#%$@<>]|\s+|[^\s#%$@<>]+')


def _cpx(c):
    o = ord(c)
    return VWF_WIDTHS[o - 0x20] if 0x20 <= o <= 0x7E else FULL_PX


def _wpx(seg):
    return sum(_cpx(c) for c in seg)


def wrap(s, width=BOX_PX, name_w=36):
    """Insert @ line-breaks at word boundaries so each rendered line fits the box (px); the
    engine otherwise hard-wraps mid-word. Markup (<XX>, # % < >) counts as zero width,
    $ name inserts as an approximate px width, <05> (text start) and an existing @ reset the
    line. A line already under width keeps any author-placed @, so manual wrapping wins."""
    out, col, space = [], 0, ''
    for a in _WTOK.findall(s):
        if a == '@':
            out.append('@'); col = 0; space = ''
        elif a == '$':
            if space and col:
                out.append(space); col += _wpx(space)
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
            wpx = _wpx(a)
            if col and col + _wpx(space) + wpx > width:
                out.append('@'); col = 0; space = ''
            elif space:
                out.append(space); col += _wpx(space)
            space = ''
            out.append(a); col += wpx
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


# --- cutscene merge ------------------------------------------------------------------
# Scripted #-engine cutscenes carry control codes the interpreter navigates by (CD-stream
# seeks `#<XX 00 YY>`, flow/inline-`%` codes, box `#` commands). Those code bytes are NOT
# all round-trippable through the markup (e.g. a `#<` CD recno byte in 0xA1-0xDF decodes as
# a hiragana), so re-encoding a whole entry from markup corrupts them. merge() instead keeps
# every control-code byte from the original `raw` verbatim and takes ONLY the dialogue text
# from `english`. See noredist/docs/findings/cutscene-engine.md.
# Dialogue = the byte run after `#<05>` (23 05) up to the next `#`/`%`; in it, `$<XX>` name
# inserts and `@` newlines are normal markup. The interpreter has no text-length field, so
# dialogue may be any length as long as the code bytes around it are untouched.

def _raw_segments(raw):
    """Split raw entry bytes into [('op',bytes)|('dlg',bytes)]. A translatable run starts
    after a speaker-open `#<04>` (23 04) or text-start `#<05>` (23 05) and ends at the next
    #/% - so both the speaker name and the dialogue are translatable; codes are 'op'."""
    segs, i, n = [], 0, len(raw)
    while i < n:
        if raw[i] == 0x23 and i + 1 < n and raw[i + 1] in (0x04, 0x05):
            segs.append(('op', raw[i:i + 2]))
            i += 2
            j = i
            while j < n and raw[j] not in (0x23, 0x25):
                j += 1
            segs.append(('dlg', raw[i:j]))
            i = j
        else:
            segs.append(('op', raw[i:i + 1]))
            i += 1
    return segs


def _english_runs(english):
    """Translatable markup runs in an english entry: after each '#<04>'/'#<05>' to next #/%."""
    runs, i, n = [], 0, len(english)
    while i < n:
        a = english.find('#<04>', i)
        b = english.find('#<05>', i)
        j = min(x for x in (a, b) if x >= 0) if (a >= 0 or b >= 0) else -1
        if j < 0:
            break
        k = j + 5
        e = k
        while e < n and english[e] not in '#%':
            e += 1
        runs.append(english[k:e])
        i = e
    return runs


def merge(english, raw):
    """Cutscene-safe encode: control bytes from `raw`, dialogue text from `english`."""
    segs = _raw_segments(raw)
    runs = _english_runs(english)
    n_dlg = sum(1 for t, _ in segs if t == 'dlg')
    if len(runs) != n_dlg:
        raise ValueError('cutscene merge: %d dialogue runs in raw, %d in english'
                         % (n_dlg, len(runs)))
    out = bytearray()
    di = 0
    for t, d in segs:
        if t == 'op':
            out += d
        else:
            out += encode(runs[di])      # encode = wrap + emit; codes already came from raw
            di += 1
    return bytes(out)
