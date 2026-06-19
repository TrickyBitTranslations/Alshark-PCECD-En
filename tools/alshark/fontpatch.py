"""Render single-byte ASCII as in-game text.

The #-engine turns each script byte into a font code in $F8/$F9 (sub-fn 0x1B, bank 0x6D
$57D0). Plain ASCII (0x20-0x7E) was parsed as 2-byte SJIS leads and drew garbage, which
forced English to be stored 2 bytes per character. This hook routes 0x20-0x7E through a
committed ASCII->SJIS table so English stores 1 byte per character. The hiragana path and
2-byte SJIS are left untouched, so untranslated Japanese still renders.

The routine sits in free space in bank 0x6D and falls back to the original handler for
every non-ASCII byte:

    $5E81  LDA ($16)        ; the script byte
           CMP #$20 / BCC ->orig      ; control bytes: original handler
           CMP #$7F / BCS ->orig      ; >0x7E (kana, 2-byte leads): original handler
           SBC #$20 / ASL / TAX
           LDA TABLE,X -> $F8 ; LDA TABLE+1,X -> $F9
           JMP $5807         ; advance cursor, return
    orig:  JMP $57E0         ; original hiragana / 2-byte path
"""

# cooked data-track offsets (track 2, 2048-byte sectors)
HOOK = 0x167D0          # $57D0: overwrite LDA ($16) with a jump into the routine
ROUTINE = 0x16E81       # logical $5E81, free space in bank 0x6D
TABLE = 0x16EA0         # logical $5EA0, the 95-entry ASCII->SJIS map

HOOK_BYTES = bytes([0x4C, 0x81, 0x5E])          # JMP $5E81
ROUTINE_BYTES = bytes.fromhex(
    "B216C9209016C97FB01238E9200AAABDA05E85F8BDA15E85F94C07584CE057")

# ASCII with no direct fullwidth SJIS via the codec -> closest fullwidth form
_ALT = {'"': '”', "'": '’', '-': '−', '~': '〜'}


def table_bytes():
    """95 entries for ASCII 0x20-0x7E -> fullwidth SJIS, ordered as the engine reads
    them ($F8 = trail byte, $F9 = lead byte)."""
    out = bytearray()
    for c in range(0x20, 0x7f):
        ch = '　' if c == 0x20 else _ALT.get(chr(c), chr(0xff00 + (c - 0x20)))
        sj = ch.encode('shift_jis')
        out += bytes([sj[1], sj[0]])
    return bytes(out)


def patches():
    """(cooked_offset, bytes) splices that enable single-byte English. Always applied;
    harmless on untranslated data (only changes how 0x20-0x7E draw)."""
    return [(HOOK, HOOK_BYTES), (ROUTINE, ROUTINE_BYTES), (TABLE, table_bytes())]
