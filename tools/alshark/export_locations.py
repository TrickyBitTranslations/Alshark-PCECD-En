#!/usr/bin/env python3
"""Extract the field location-name banners (the place-name shown on town entry) to a TSV.

Each map block is 0x6000 bytes; its location name is an inline string at block+0x32,
encoded as half-width katakana (0xA1-0xDF, 1 byte) + optional full-width SJIS suffix
(の町/の村/の試練/... 2 bytes), 0x00-terminated. Blocks with no valid name at +0x32 are
non-town maps and are skipped. The banner draws via bank 0x6B $AB0B using our VWF font.

  PYTHONPATH=tools python3 tools/alshark/export_locations.py work/track02.iso > script/locations.tsv

Columns match the other script TSVs (block_off = the name's cooked offset).
"""
import sys
from alshark import textcodec

NAME_OFF = 0x32          # location name is inline at map-block + 0x32
PTR_OFF = 0x2E           # the banner's name pointer at map-block + 0x2E (= $C032 when un-relocated)
PTR_VAL = b'\x32\xc0'    # default pointer value ($C032)

_HW = "｡｢｣､･ｦｧｨｩｪｫｬｭｮｯｰｱｲｳｴｵｶｷｸｹｺｻｼｽｾｿﾀﾁﾂﾃﾄﾅﾆﾇﾈﾉﾊﾋﾌﾍﾎﾏﾐﾑﾒﾓﾔﾕﾖﾗﾘﾙﾚﾛﾜﾝﾞﾟ"
HK = {0xa1 + i: c for i, c in enumerate(_HW)}


def _is_hk(b):
    return 0xa1 <= b <= 0xdf


def _is_fw(b):
    return 0x81 <= b <= 0x9f or 0xe0 <= b <= 0xef


def name_at(data, o):
    """The 0x00-terminated location name at offset o, or None if not a valid name."""
    j = o
    while _is_hk(data[j]) or _is_fw(data[j]):
        j += 2 if _is_fw(data[j]) else 1
    return data[o:j] if data[j] == 0 and 2 <= j - o <= 24 else None


def decode(b):
    out = []
    i = 0
    while i < len(b):
        if _is_hk(b[i]):
            out.append(HK[b[i]])
            i += 1
        else:
            out.append(textcodec.decode(b[i:i + 2]))
            i += 2
    return "".join(out)


def main():
    data = open(sys.argv[1], "rb").read()
    # Disc-wide scan: a location banner has the default name pointer $C032 at block+0x2E and a
    # valid inline name at block+0x32. Map blocks are 0x1000-aligned (filters stray $C032 matches).
    print("block_off\tstr_off\tspeaker\ttext\traw_hex\tenglish\tstatus")
    seen = set()
    i = data.find(PTR_VAL)
    while i != -1:
        base = i - PTR_OFF
        if base >= 0 and base & 0xFFF == 0 and base not in seen:
            nm = name_at(data, base + NAME_OFF)
            if nm:
                seen.add(base)
                print("0x%x\t0x0\t\t%s\t%s\t\t" % (base + NAME_OFF, decode(nm), nm.hex()))
        i = data.find(PTR_VAL, i + 1)


if __name__ == "__main__":
    main()
