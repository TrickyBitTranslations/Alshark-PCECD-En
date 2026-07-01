"""Preview render model for the web dialogue simulator.

Turns a cutscene entry (english markup + original raw bytes) into the ordered display LINES the
#-engine flows on screen: it runs dialogcodec.merge() (so the exact same boundary-spacing and
box-width word-wrap as the shipped game), then walks the merged bytes splitting on the pen-reset
ops and inline `@`, measuring each line with the real VWF widths and substituting `$<XX>` name
inserts with the English name.

This is the single source of truth for the preview. The JS port (site/render.js) must produce the
same line list; tools/test_render_conformance.py runs both over every line and fails CI on drift.
"""
import os
import re

from alshark import dialogcodec as dc
import tsv

_NAME_TXT = None
_NAME = re.compile(r'\$<([0-9a-fA-F]{2})>|<[0-9a-fA-F]{2}>|.', re.DOTALL)


def name_text_map():
    """{name-insert index -> English name} from names.tsv (same keying as dialogcodec._name_w_map,
    which gives the widths). `$<00>` etc. render the party member's English name in game."""
    global _NAME_TXT
    if _NAME_TXT is None:
        _NAME_TXT = {}
        p = os.path.join(os.path.dirname(__file__), '..', '..', 'script', 'names.tsv')
        try:
            for r in tsv.read(p):
                en = (r.get('english') or '').strip()
                if en:
                    _NAME_TXT[int(r['str_off'])] = en
        except Exception:
            pass
    return _NAME_TXT


def layout(english, raw, width=dc.BOX_PX):
    """Return the display lines for an entry: [{'text': str, 'px': int, 'over': bool}, ...].

    `text` is the visible glyphs only (control codes stripped, `$<XX>` -> the English name); `px` is
    the rendered width; `over` flags a line the engine would have to hard-wrap (px > box). Trailing
    blank lines are dropped. Untranslated (blank english) previews the raw as-is."""
    merged = dc.merge(english, raw) if (english and english.strip()) else raw
    names = name_text_map()
    lines = []
    text, px = [], 0

    def endline():
        lines.append({'text': ''.join(text), 'px': px, 'over': px > width})
        text.clear()
        return 0

    for t, d in dc.tokenize(merged):
        if t == 'op':
            if d in dc.RESET_OPS:
                px = endline()
            continue
        for m in _NAME.finditer(dc.decode(d)):
            tok = m.group(0)
            if tok == '@':                                   # inline line break
                px = endline()
            elif m.group(1) is not None:                     # $<XX> name insert
                nm = names.get(int(m.group(1), 16), '{%s}' % m.group(1))
                text.append(nm); px += dc._wpx(nm)
            elif tok[0] == '<' or tok in '#%$>':             # zero-width markup / control
                continue
            else:                                            # a visible glyph
                text.append(tok); px += dc._cpx(tok)
    endline()
    while lines and lines[-1]['text'] == '':
        lines.pop()
    return lines


def _sjis_tables():
    """The non-ASCII chars that appear in cutscene english + their engine bytes, so the JS port
    encodes/decodes them exactly like the Python codec (Shift-JIS / the single-byte hiragana form) -
    otherwise its byte boundaries drift and wrap/merge diverge. Derived from the codec, not hardcoded.
      enc: char -> engine byte hex          (dialogcodec._enc_text)
      sb:  0xA1-0xDF byte -> decoded char   (single-byte hiragana table)
      dw:  2-byte SJIS hex -> decoded char  (only the chars that occur)"""
    chars = set()
    p = os.path.join(os.path.dirname(__file__), '..', '..', 'script', 'cutscene.tsv')
    try:
        for r in tsv.read(p):
            for ch in (r.get('english') or ''):
                if ord(ch) > 0x7e:
                    chars.add(ch)
    except Exception:
        pass
    enc = {ch: dc._enc_text(ch).hex() for ch in chars}
    sb = {c: dc.decode(bytes([c])) for c in range(0xa1, 0xe0)}
    dw = {}
    for ch in chars:
        b = dc._enc_text(ch)
        if len(b) == 2:
            dw[b.hex()] = ch
    return enc, sb, dw


def model_meta():
    """Constants the JS port needs so nothing is hardcoded twice: box width, full-width advance,
    the ASCII VWF advance table, the name-insert maps, and the non-ASCII byte tables."""
    enc, sb, dw = _sjis_tables()
    return {
        'boxPx': dc.BOX_PX,
        'fullPx': dc.FULL_PX,
        'widths': list(dc.VWF_WIDTHS),          # ASCII 0x20-0x7E advance px
        'nameW': dc._name_w_map(),              # {index -> px}
        'nameText': name_text_map(),            # {index -> English name}
        'nameWDefault': 36,
        'enc': enc, 'sb': sb, 'dw': dw,         # non-ASCII char <-> engine bytes (JS parity)
    }
