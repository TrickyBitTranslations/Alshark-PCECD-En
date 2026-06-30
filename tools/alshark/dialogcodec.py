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

# Ops that reset the render pen to the left margin (a TRUE line break), used by merge() to
# decide where the carried line-px restarts at 0 and by the line-width simulator
# (check_linewidth.py). CRUX of the cutscene word-wrap fix: consecutive glyph runs separated by
# a NON-reset op share one physical line and the engine hard-wraps at the box edge, so merge()
# must carry the pen across them and break at the box boundary itself. Conservative set - only
# boundaries with clear evidence are listed; everything else (incl. #<00>, the % codes, bare
# <XX> control bytes) defaults to NON-resetting (the run flows straight on).
#   2304 #<04>  title/name bar start  - physically separate window from the body
#   2305 #<05>  body text start       - new box body (task-confirmed reset)
#   2306 #<06>  break code            - dialogue-spacing-jams.md (in-game confirmed)
#   235f #_     break code            - dialogue-spacing-jams.md (in-game confirmed)
#   233e #>     break code            - dialogue-spacing-jams.md (in-game confirmed)
# NOT a reset: 2300 #<00> - empirically the engine flows straight through it (the palm-reading
# bug); it is deliberately excluded so two #<00>-joined runs share a line and wrap at the edge.
RESET_OPS = frozenset({
    bytes.fromhex('2304'), bytes.fromhex('2305'), bytes.fromhex('2306'),
    bytes.fromhex('235f'), bytes.fromhex('233e'),
})


def _cpx(c):
    o = ord(c)
    return VWF_WIDTHS[o - 0x20] if 0x20 <= o <= 0x7E else FULL_PX


def _wpx(seg):
    return sum(_cpx(c) for c in seg)


def wrap(s, width=BOX_PX, name_w=36, start_px=0, return_px=False):
    """Insert @ line-breaks at word boundaries so each rendered line fits the box (px); the
    engine otherwise hard-wraps mid-word. Markup (<XX>, # % < >) counts as zero width,
    $ name inserts as an approximate px width, <05> (text start) and an existing @ reset the
    line. A line already under width keeps any author-placed @, so manual wrapping wins.

    start_px seeds the first line's pen so a run can CONTINUE the previous run's physical line
    (used by merge() to flow text across non-breaking ops like #<00> - see RESET_OPS). When the
    continued run's first word would overflow, wrap inserts the @ at that boundary, which becomes
    the break between the two runs. return_px=True returns (string, end_px) where end_px is the
    pen px of the final line, so the caller can carry it into the next run.

    Anti-widow: when a greedy auto-break leaves a single word alone on a line, the last word of
    the line above is pulled down to join it (if both still fit), so proper nouns like
    "Saxon Canyon" don't split. This only moves an @ and a space, so the byte count is unchanged."""
    # Build lines as token lists. Each line records the separator BEFORE it ('@' or '' for the
    # first line / a <05> reset), its visible px, visible word count, and whether the break that
    # started it was an AUTO wrap (the only kind the anti-widow pass is allowed to rebalance).
    # The first line is seeded with start_px (the carried pen from a continued run): it counts
    # toward width (so the first word can break) but holds no tokens, so the anti-widow guard
    # (prev['words'] >= 2) never reaches into the previous run's text.
    lines = [{'sep': '', 'toks': [], 'px': start_px, 'words': 0, 'auto': False}]
    space = ''

    def cur():
        return lines[-1]

    def newline(sep, auto):
        lines.append({'sep': sep, 'toks': [], 'px': 0, 'words': 0, 'auto': auto})

    for a in _WTOK.findall(s):
        if a == '@':
            newline('@', False); space = ''
        elif a == '$':
            c = cur()
            if c['px'] and c['px'] + _wpx(space) + name_w > width:
                newline('@', True); space = ''   # a $ name insert that overflows breaks first
                c = cur()
            elif space and c['px']:
                c['toks'].append(space); c['px'] += _wpx(space)
            space = ''
            c['toks'].append('$'); c['px'] += name_w; c['words'] += 1
        elif _TOKEN.fullmatch(a):
            cur()['toks'].append(a)
            if a == '<05>':              # text-start marker begins a fresh line (no @)
                newline('', False); space = ''
        elif a in ('#', '%', '<', '>'):
            cur()['toks'].append(a)
        elif a.isspace():
            space = a
        else:                            # a visible word
            wpx = _wpx(a)
            c = cur()
            if c['px'] and c['px'] + _wpx(space) + wpx > width:
                newline('@', True); space = ''
                c = cur()
                c['toks'].append(a); c['px'] += wpx; c['words'] += 1
            else:
                if space:
                    c['toks'].append(space); c['px'] += _wpx(space)
                space = ''
                c['toks'].append(a); c['px'] += wpx; c['words'] += 1

    # anti-widow: pull the previous line's last word down onto a lone-word auto line.
    for i in range(1, len(lines)):
        ln, prev = lines[i], lines[i - 1]
        if not (ln['auto'] and ln['words'] == 1 and prev['words'] >= 2):
            continue
        # find prev's last visible word and the space token just before it
        wi = max(j for j, t in enumerate(prev['toks']) if not _zero_w(t))
        si = wi - 1 if wi > 0 and prev['toks'][wi - 1].isspace() else None
        word = prev['toks'][wi]
        if word == '$':
            continue                     # never split a $<XX> name insert from its index token
        gap = prev['toks'][si] if si is not None else ' '
        if _wpx(word) + _wpx(gap) + ln['px'] > width:
            continue                     # would overflow the joined line; leave the widow
        del prev['toks'][wi]
        if si is not None:
            del prev['toks'][si]
        prev['px'] -= _wpx(word) + _wpx(gap); prev['words'] -= 1
        ln['toks'] = [word, gap] + ln['toks']
        ln['px'] += _wpx(word) + _wpx(gap); ln['words'] += 1

    out = ''.join(ln['sep'] + ''.join(ln['toks']) for ln in lines)
    if return_px:
        return out, lines[-1]['px']
    return out


def _zero_w(t):
    """A wrap token that occupies no line width (markup / control), so it isn't a 'word'."""
    return t in ('#', '%', '<', '>') or bool(_TOKEN.fullmatch(t))


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


def _encode_raw(s):
    """Markup -> bytes, no word-wrap (caller wraps if it wants to)."""
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


def encode(s):
    return _encode_raw(wrap(s))


def _encode_run(s, start_px):
    """Wrap a single glyph run CONTINUING the previous run's line at start_px, encode it, and
    return (bytes, end_px). end_px is the pen px at the end of the run, threaded into the next
    run by merge(). A break inserted in the run's first line lands as a leading @, which is the
    break between the carried line and this run - exactly the cross-run wrap the engine needs."""
    if s and not s.strip():          # a run that is ONLY whitespace is a structural byte the engine
        return _encode_raw(s), start_px + _wpx(s)   # navigates by (e.g. the palm-reading choice's
                                     # 0x20 between %<02> and <1f>), NOT display text - keep verbatim.
                                     # (Trailing spaces ON text runs stay droppable - they're padding.)
    wrapped, end_px = wrap(s, start_px=start_px, return_px=True)
    return _encode_raw(wrapped), end_px


# --- cutscene merge ------------------------------------------------------------------
# Scripted #-engine cutscenes carry control codes the interpreter navigates by: box `#`
# commands (2 bytes, or 5 for the CD-stream seek `#< XX 00 YY`), variable-length `%` codes,
# and inline `$` name inserts / `@` newlines. Those code bytes are NOT all round-trippable
# through the markup (a `#<` CD recno byte in 0xA1-0xDF decodes as a hiragana), so re-encoding
# a whole entry corrupts them. merge() keeps every control code byte from the original `raw`
# verbatim and substitutes only the glyph runs from `english`. A glyph run is any maximal run
# of drawable bytes (text + inline `$`/`@`) BETWEEN control codes - the interpreter has no
# text-length field, so a run may follow ANY command (#<05>, #!, #_, ...) and be any length.
# See noredist/docs/findings/cutscene-engine.md.

def _pct_len(d, i):
    """Byte length of the `%`(0x25) code at d[i] (subcommand + params). Conservative: only the
    verified subcommands; raises on an unhandled one (so it's measured + added, never silently
    corrupting). Length-prefixed codes (`% S L <L bytes>`) are 3 + L."""
    s = d[i + 1]
    if s >= 0x80:                          # box terminator (e.g. %<ff>), no params
        return 2
    # inline-length / relative-skip handlers: % S L <L bytes> (handler reads L, then L more).
    # 0x10/0x11/0x12 (inline-glyph display - shop item/price) and 0x21/0x25/0x26 are ALSO
    # length-prefixed: the L byte is the data byte count, so length = 3 + L. (The handler renders
    # those L bytes as a variable number of 1/2-byte glyphs - that glyph COUNT is not the byte
    # length, which is what made these look uncrackable - but the byte length is plain 3+L.)
    # Verified: re-encode round-trips byte-exact for 67/70 such rows; the other 3 only drop a
    # trailing pad space. Cracking these unlocks the shop / inn / item-get dialogue.
    if s in (0x04, 0x05, 0x07, 0x08, 0x10, 0x11, 0x12, 0x13, 0x14, 0x15, 0x16, 0x19, 0x1a,
             0x1c, 0x1d, 0x21, 0x25, 0x26):
        return 3 + d[i + 2]
    # fixed length = 2 + the param bytes the handler reads via $9911/$9916
    FIXED = {0x00: 4, 0x01: 3, 0x02: 2, 0x06: 5, 0x09: 4, 0x0a: 4, 0x0b: 5, 0x0c: 5,
             0x0d: 6, 0x0e: 2, 0x0f: 3, 0x17: 4, 0x18: 5, 0x1b: 4,
             0x1f: 4, 0x20: 6}
    if s in FIXED:
        return FIXED[s]
    if s == 0x03:                          # conditional: 3 if the peeked byte is 0, else 5
        return 3 if d[i + 3] == 0 else 5
    if s == 0x1e:                          # skip L, +2 params, a NUL-terminated run, +2 params
        j = i + 3 + d[i + 2] + 2
        while j < len(d) and d[j] != 0x00:
            j += 1
        return j - i + 3
    raise ValueError('dialogcodec: unhandled %%<%02x> at 0x%x - measure its length + add it'
                     % (s, i))


def tokenize(b):
    """Split entry bytes into [('op',codes)|('dlg',glyphrun)]. dlg = a maximal run of drawable
    bytes (2-byte SJIS / 1-byte kana / ASCII) plus inline `$`(24 XX) and `@`(40); op = `#`
    commands (5 if `#<` CD-seek else 2), `%` codes (_pct_len), and any non-drawable byte."""
    segs, i, n = [], 0, len(b)
    run = bytearray()

    def flush():
        if run:
            segs.append(('dlg', bytes(run)))
            del run[:]

    while i < n:
        c = b[i]
        if c == 0x23:                                   # # command
            flush()
            ln = 5 if (i + 1 < n and b[i + 1] == 0x3c) else 2
            segs.append(('op', b[i:i + ln])); i += ln
        elif c == 0x25:                                 # % code
            flush()
            ln = _pct_len(b, i)
            segs.append(('op', b[i:i + ln])); i += ln
        elif c == 0x24:                                 # $ name insert (inline)
            run += b[i:i + 2]; i += 2
        elif c == 0x40:                                 # @ newline (inline)
            run += b[i:i + 1]; i += 1
        elif 0x81 <= c <= 0x9f or 0xe0 <= c <= 0xef:    # 2-byte SJIS
            run += b[i:i + 2]; i += 2
        elif 0xa1 <= c <= 0xdf or 0x20 <= c <= 0x7e:    # 1-byte kana / ASCII glyph
            run += b[i:i + 1]; i += 1
        else:                                           # control byte (<0x20 etc.) -> opaque
            flush()
            segs.append(('op', b[i:i + 1])); i += 1
    flush()
    return segs


def merge(english, raw):
    """Cutscene-safe encode: control bytes from `raw`, glyph runs from `english`."""
    raw_segs = tokenize(raw)
    en_dlg = [d for t, d in tokenize(_encode_raw(english)) if t == 'dlg']
    n_dlg = sum(1 for t, _ in raw_segs if t == 'dlg')
    if len(en_dlg) != n_dlg:
        raise ValueError('cutscene merge: %d glyph runs in raw, %d in english'
                         % (n_dlg, len(en_dlg)))
    out = bytearray()
    di = 0
    pen = 0                          # carried line position (px) across glyph runs
    for t, d in raw_segs:
        if t == 'op':
            out += d
            if d in RESET_OPS:       # true line break: the next run starts at the left margin
                pen = 0
        else:
            enc, pen = _encode_run(decode(en_dlg[di]), pen)
            out += enc
            di += 1
    return bytes(out)
