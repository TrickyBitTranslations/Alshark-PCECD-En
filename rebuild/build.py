#!/usr/bin/env python3
"""Build the Alshark English translation.

Carves the original banks from your cooked disc, assembles the rebuild banks with wla-dx,
splices in the VWF font + translated script, and writes the patched disc / CHD. This repo
ships everything needed to build EXCEPT the game disc - bring your own and cook it to
work/track02.iso first (see tools/cook.py).

  build.py            assemble + report
  build.py --disc     also write a patched BIN/CUE (build/) with fixed EDC/ECC
  build.py --chd      also build the CHD
  build.py --selftest disassembler round-trip vs the original banks (regression)
"""
import argparse
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..'))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
from alshark.cdecc import fix_mode1

SEC = 2352
DATA = 16
TRACK2 = 3590

# Original banks the asm .BACKGROUNDs, carved from the cooked disc into incbin/ at build time
# (game bytes - never committed): (incbin file, cooked offset, length).
CARVE = [('bank6d.bin', 0x15000, 0x2000), ('boot.bin', 0x00000, 0x2000),
         ('bank6b.bin', 0x0b000, 0x2000)]

# asm source (in src/) -> cooked disc offset of the bank's first byte.
BANKS = [
    ('bank6d.s', 0x15000),   # #-engine render/conversion bank ($4000-$5FFF): VWF render hook
    ('boot.s',   0x00000),   # boot/WRAM image ($2000-$3FFF): per-transition font reload
    ('bank6b.s', 0x0b000),   # field banner bank ($A000-$BFFF): proportional location-name banner
]

# raw blobs spliced onto disc: (cooked offset, incbin file). The VWF font (committed asset).
FONT_OFF = 0xa1a000            # cooked; = abs LBA $00223A, loaded to card bank 0x7F $CFA0
BLOBS = [(FONT_OFF, 'vwf_glyphs.bin'), (FONT_OFF + 0x5f0, 'vwf_widths.bin')]  # 1520B glyphs


def carve(cooked):
    """Slice the original banks the asm .BACKGROUNDs out of the user's cooked disc."""
    os.makedirs(os.path.join(HERE, 'incbin'), exist_ok=True)
    for name, off, ln in CARVE:
        open(os.path.join(HERE, 'incbin', name), 'wb').write(cooked[off:off + ln])
    gen_hud_idx()                  # incbin/hud_en_idx.bin for boot.s copy_hud_names (must precede assembly)


def blob_patches():
    return [(off, open(os.path.join(HERE, 'incbin', n), 'rb').read()) for off, n in BLOBS]


# Character/item name table (bank 0x7A $D066 = cooked 0x784066): NUL-terminated, scan-indexed
# strings, edited via script/names.tsv (entries 0..25 are the cast; 26+ weapons/items). Scan
# indexing needs no repointing, so entries grow/shrink freely; the table must fit before the
# next block at 0x785000.
NAME_TBL = 0x784066


# The menu reads weapon/armor/item names from a HARDCODED base pointer (original $7157 = the
# offset of entry 28, the first item, right after the Japanese cast) loaded at code $4191/$4204
# in bank 0x6D. Our English cast names are longer, so the item region shifts; we repoint that
# base to entry 28's actual logical address. The cast itself is read from $7066 (table start,
# scan-indexed) so it needs no fix-up. Both sites: A9 <lo> 85 16 A9 <hi> 85 17.
ITEM_BASE_SITES = (0x191, 0x204)   # bank-0x6D offsets of the LDA #lo of each item-base load
BANK6D_OFF = 0x15000               # cooked offset of bank 0x6D


def name_patch(cooked):
    import tsv
    rows = list(tsv.read(os.path.join(ROOT, 'script', 'names.tsv')))
    blob = bytearray()
    off28 = None
    for k, r in enumerate(rows):
        if k == 28:
            off28 = len(blob)               # byte offset of the first item entry in the table
        en = r.get('english', '')
        blob += (en.encode('latin-1') if en else bytes.fromhex(r['raw_hex']))
        blob += b'\x00'
    if NAME_TBL + len(blob) > 0x785000:
        raise SystemExit('name table overflow: %d > %d' % (len(blob), 0x785000 - NAME_TBL))
    patches = [(NAME_TBL, bytes(blob))]
    item_base = 0x7066 + off28              # table base $7066 (MPR3) + first-item offset
    lo, hi = item_base & 0xff, item_base >> 8
    for site in ITEM_BASE_SITES:
        patches.append((BANK6D_OFF + site + 1, bytes([lo])))   # LDA #lo operand
        patches.append((BANK6D_OFF + site + 5, bytes([hi])))   # LDA #hi operand
    return patches


# Field-menu / system text: inline SJIS strings in bank 0x6B (labels, option lists, pickers,
# messages) - extracted to script/menu.tsv by tools/export_menu.py, drawn by the bank-0x6D label
# loop ($5748, patched in bank6d.s to render ASCII in our VWF font). Each row's raw_hex is the
# original glyph run + its 0x00 terminator (= the writable slot); we splice English ASCII (1 byte/
# char, '|'=0x0D separator), NUL-terminated, zero-padded to the slot - shorter than the SJIS, so it
# fits in place with no repointing. Rows without an english value are left byte-exact.
def menu_patch(cooked):
    import tsv
    from alshark import menucodec
    patches = []
    for r in tsv.read(os.path.join(ROOT, 'script', 'menu.tsv')):
        off = int(r['block_off'], 16)
        raw = bytes.fromhex(r['raw_hex'])               # run + 0x00 terminator
        if cooked[off:off + len(raw)] != raw:
            raise SystemExit('menu.tsv 0x%x not as extracted' % off)
        en = r.get('english', '')
        if not en:
            continue
        new = menucodec.encode(en) + b'\x00'
        if len(new) > len(raw):
            raise SystemExit('menu.tsv 0x%x overflows: %d > %d' % (off, len(new), len(raw)))
        new += b'\x00' * (len(raw) - len(new))          # pad to the slot (stays in span)
        patches.append((off, new))
    return patches


# Battle prose strings (failure / level-up / rewards / can't-use), edited via
# script/battle.tsv. These live inline among engine code with no pointer table, so
# each english keeps every control byte as <XX> markup (textcodec round-trips exactly)
# and is spliced into the original 0x00-terminated span, padded to length - nothing
# outside the span moves. Drawn by the same bank-6D label loop, so ASCII renders VWF.
def battle_patch(cooked):
    import tsv
    from alshark import textcodec
    patches = []
    for r in tsv.read(os.path.join(ROOT, 'script', 'battle.tsv')):
        off = int(r['block_off'], 16)
        raw = bytes.fromhex(r['raw_hex'])               # original span incl. 0x00
        if cooked[off:off + len(raw)] != raw:
            raise SystemExit('battle.tsv 0x%x not as extracted' % off)
        en = r.get('english', '')
        if not en:
            continue
        new = textcodec.encode(en)                      # markup already ends with <00>
        if len(new) > len(raw):
            raise SystemExit('battle.tsv 0x%x overflows: %d > %d' % (off, len(new), len(raw)))
        new += b'\x00' * (len(raw) - len(new))          # pad within the span
        patches.append((off, new))
    return patches


# Battle party-name array (cooked 0x19afb): 9 entries, 8-byte name field + 0x00 terminator,
# stride 9. Driven from script/names.tsv (via alshark.cast) so it stays in sync with the main
# name table and the HUD names - a translator edits names.tsv only. ASCII, padded with 0x00.
PARTY_ARRAY = 0x19afb


def party_array_patch(cooked):
    from alshark import cast
    patches = []
    for i, name in enumerate(cast.party_names(ROOT)):
        off = PARTY_ARRAY + i * 9
        if len(name) > 8:
            raise SystemExit('party name %r > 8 bytes for the array field' % name)
        if cooked[off + 8] != 0x00:
            raise SystemExit('party array 0x%x not as expected' % off)
        patches.append((off, name.encode('latin-1').ljust(8, b'\x00')))
    return patches


# Battle HUD party names (right panel). The names are a table of 8x8 font tile-refs (8 per
# member) referencing an 8x8 half-width font (disc 0x39000, VRAM tile 0x200+index, katakana only).
# script/hud_names_patch.json (built by tools/alshark/hudnames.py) injects English 8x8 glyphs into
# spare font slots AND holds the English tile-ref table.
#
# The draw reads its name table at $690A (bank 0x78) - resident and COMBAT-STABLE (verified: a
# card-RAM write breakpoint on $690A never fires across boot/field/battle), but loaded from disc
# 0x3f790a, which is shared with the field (patching it on disc corrupts the field). Every spare
# card slack we tried was a work buffer or sprite-graphics source. So: leave the disc original
# (field clean) and overwrite the card copy of $690A at runtime from the font-reload hook (boot.s
# copy_hud_names, runs at every transition, combat-stable WRAM). hud_patch here only injects the
# font glyphs; gen_hud_idx() builds the 72 glyph indices boot.s copies in. See docs/battle-text-map.md
# and memory verify-slack-empirically.
def gen_hud_idx():
    """Write incbin/hud_en_idx.bin: 72 font-glyph indices (9 members x 8 tiles) for boot.s."""
    import json
    table = [(off, bytes.fromhex(hx))
             for off, hx in json.load(open(os.path.join(ROOT, 'script', 'hud_names_patch.json')))
             if off >= 0x3f0000]
    blob = b''.join(b for _, b in sorted(table))   # 9 x 16-byte (index,$70) entries = 144 bytes
    if len(blob) != 144:
        raise SystemExit('HUD name table is %d bytes, expected 144' % len(blob))
    idx = bytes(blob[i] for i in range(0, 144, 2))  # drop the $70 palette byte -> 72 indices
    open(os.path.join(HERE, 'incbin', 'hud_en_idx.bin'), 'wb').write(idx)


def hud_patch(cooked):
    import json
    patches = []
    for off, hx in json.load(open(os.path.join(ROOT, 'script', 'hud_names_patch.json'))):
        if off < 0x3b000:
            patches.append((off, bytes.fromhex(hx)))   # English font glyphs -> spare disc font slots
    return patches


# Field location-name banners (town-entry place names). Each map block's name is an inline
# half-width-katakana string at block+0x32 in tight slots; English (with suffix) doesn't fit.
# So we RELOCATE: write [start_x][english\0] into free space in the map block's bank-0x76 page
# and repoint the map's name pointer at block+0x2E to it. start_x is the precomputed centered left
# edge (8 + (144 - pixel_width)/2). The bank-0x6B hook (bank6b.s) reads start_x + draws the name
# proportionally. Names from script/locations.tsv. Pure data here; see docs/battle-text-map.md.
def location_patch(cooked):
    import tsv
    widths = open(os.path.join(HERE, 'incbin', 'vwf_widths.bin'), 'rb').read()
    px = lambda s: sum(widths[ord(c) - 0x20] for c in s)
    patches = []
    for r in tsv.read(os.path.join(ROOT, 'script', 'locations.tsv')):
        en = r.get('english', '').strip()
        if not en:
            continue
        base = int(r['block_off'], 16) - 0x32              # map block start
        if cooked[base + 0x2E:base + 0x30] != b'\x32\xc0':  # sanity: name pointer = $C032
            raise SystemExit('location 0x%x name pointer not as expected' % base)
        best = (0, 0)                                       # biggest zero run in the bank-0x76 page
        i = base + 0x50
        while i < base + 0x2000:
            if cooked[i] == 0:
                j = i
                while j < base + 0x2000 and cooked[j] == 0:
                    j += 1
                if j - i > best[1]:
                    best = (i - base, j - i)
                i = j
            else:
                i += 1
        foff = best[0] + 2                                  # small margin into the free run
        blob = bytes([8 + (144 - px(en)) // 2]) + en.encode('latin-1') + b'\x00'
        if best[1] < len(blob) + 2 or foff + len(blob) > 0x2000:
            raise SystemExit('location %r: no room in map block' % en)
        addr = 0xC000 + foff
        patches.append((base + foff, blob))                # [start_x][name\0] in free space
        patches.append((base + 0x2E, bytes([addr & 0xff, addr >> 8])))  # repoint name pointer
    return patches


def assemble(src):
    """Assemble one src/*.s -> build/<name>.bin, return the bytes."""
    name = os.path.splitext(src)[0]
    obj = os.path.join('build', name + '.o')
    out = os.path.join('build', name + '.bin')
    link = os.path.join('build', name + '.link')
    _run(['wla-huc6280', '-k', '-I', 'incbin', '-o', obj, os.path.join('src', src)])
    with open(os.path.join(HERE, link), 'w') as f:
        f.write('[objects]\n%s\n' % obj)
    _run(['wlalink', '-b', link, out])
    return open(os.path.join(HERE, out), 'rb').read()


def _run(cmd):
    """Run a build command, hiding the expected .BACKGROUND-overwrite notices."""
    r = subprocess.run(cmd, cwd=HERE, capture_output=True, text=True)
    noise = ('MEM_INSERT', 'Writing a byte', 'Writing two bytes')
    out = '\n'.join(l for l in (r.stdout + r.stderr).splitlines()
                    if l.strip() and not l.lstrip().startswith(noise)
                    and not l.lstrip().startswith('^'))
    if r.returncode != 0:
        raise SystemExit('%s failed:\n%s' % (cmd[0], out))
    if out:
        print(out)


def assemble_banks(cooked):
    """Assemble every bank; report how much each diverges from the original disc bytes."""
    os.makedirs(os.path.join(HERE, 'build'), exist_ok=True)
    patches = []
    for src, off in BANKS:
        b = assemble(src)
        chg = sum(1 for j in range(len(b)) if b[j] != cooked[off + j])
        print('%-12s %d bytes @ cooked 0x%06x  (%d bytes changed vs original)'
              % (src, len(b), off, chg))
        patches.append((off, b))
    return patches


def save_menu_patch(cooked):
    """English boot save-menu option buttons: 開始/複写/削除 -> Start/Copy/Delete.

    The boot save/title menu is the System Card BRAM-style UI (banks 0x68-0x6C). Its option box
    is described by a 0x10-byte entry at disc 0x48018ad: [ptr][params]. A glyph compositor (bank
    0x68 $43EB) builds each char into a VRAM tile region; $663B lays text out horizontally
    (X += per char, 0x52 'R' = newline, 0x45 'E' = end). The font has full-width SJIS Latin (that's
    what ＤＡＴＡ/ＬＶ are), so English must be full-width (half-width ASCII renders as garbage).
    To fit "Start/Copy/Delete" the box must be widened, which means THREE coupled entry fields:
      - entry+0xa (disc 0x48018b7) = box width param; live $8D = param - 3. 0x0d -> $8D = 10 cells.
      - entry+0x8 (disc 0x48018b5/6) = glyph/BAT ROW STRIDE in bytes; must equal $8D*0x20 (0x140),
        or the staging row stride mismatches the render and the text transposes/garbles.
      - tile-base (entry+0x4/0x6) is LEFT at the original 0x44d: its region has slack up to the
        DATA-1 box (tile 0x500), so the widened 10x6 box (-> tiles 0x44d..0x4c5) stays clear of it.
        (Relocating the tile-base instead just collided with the DATA-1/DATA-2 boxes.)
    The option string itself is relocated to verified-free bank-0x68 space ($4a60, disc 0x2be1a60,
    write-bp-confirmed unused across the whole menu) and the entry pointer repointed there.
    Pure data patch, no asm. See memory title-menu-todo for the full RE.
    """
    def fw(s):                                   # ASCII -> full-width SJIS (this menu has no half-width)
        out = []
        for c in s:
            if c == ' ':
                out.append('　')             # space -> full-width space
            elif 0x21 <= ord(c) <= 0x7e:
                out.append(chr(ord(c) + 0xFEE0))
            else:
                out.append(c)
        return ''.join(out).encode('shift_jis')

    def msg(lines):                              # 0x52 'R' = newline between lines, 0x45 'E' = end
        return b'\x52'.join(fw(l) for l in lines) + b'\x45'

    # (entry addr in the descriptor table, English lines). Option box = narrow (needs widen below);
    # the dialog boxes are already wide (W=23, $8D=20, ~13 full-width chars/line, 3 lines / 4 for msg7)
    # and share one tile region (modal), so they only need string relocation + repoint.
    items = [
        (0x48018ad, ['Start', 'Copy', 'Delete']),                              # option box
        (0x48018dd, ['Copy slot has', 'data. Erase', 'it to copy.']),          # msg3 copy-target-has-data
        (0x48018ed, ['Backup RAM is', 'full. Erase a', 'file to copy.']),      # msg4 RAM-full on copy
        (0x48018fd, ['No data here.', 'Cannot copy.']),                        # msg5 no-data on copy
        (0x480190d, ['Erase this', 'save data?', '  Yes    No']),              # msg6 delete-confirm
        (0x480191d, ['Backup RAM', 'is too full.', 'Erase files,', 'then restart.']),  # msg7 RAM-insufficient
        (0x480192d, ['A BIOS error', 'occurred.', 'Please reset.']),           # msg8 BIOS-error
    ]
    BASE_DISC, BASE_LOG, FREE = 0x2be1a60, 0x4a60, 1440   # verified-free bank-0x68 slack (write-bp)
    if cooked[0x48018ad:0x48018af] != b'\x77\x69':        # sanity: option entry pointer = $6977
        raise SystemExit('save-menu option entry pointer not as expected')
    if any(cooked[BASE_DISC:BASE_DISC + FREE]):           # the relocation home must be clear
        raise SystemExit('save-menu relocation space at 0x%x is not free' % BASE_DISC)
    patches, off = [], 0
    for entry, lines in items:
        blob = msg(lines)
        addr = BASE_LOG + off
        patches.append((BASE_DISC + off, blob))                    # English string in free space
        patches.append((entry, bytes([addr & 0xff, addr >> 8])))   # repoint the entry's string ptr
        off += len(blob)
    if off > FREE:
        raise SystemExit('save-menu strings (%d bytes) exceed free space (%d)' % (off, FREE))
    # widen ONLY the option box (dialog boxes are already wide): row stride MUST match the width
    patches.append((0x48018b5, b'\x40\x01'))     # option box row stride 0x0060 -> 0x0140 ($8D*0x20)
    patches.append((0x48018b7, b'\x0d'))         # option box width param 0x06 -> 0x0d ($8D = 10)
    return patches


def write_disc(patches, want_chd):
    extracted = os.path.join(ROOT, 'extracted')
    out = os.path.join(HERE, 'build')
    out_bin = os.path.join(out, 'Alshark.bin')
    out_cue = os.path.join(out, 'Alshark.cue')
    shutil.copyfile(os.path.join(extracted, 'Alshark.bin'), out_bin)
    shutil.copyfile(os.path.join(extracted, 'Alshark.cue'), out_cue)
    affected = set()
    with open(out_bin, 'r+b') as f:
        for off, new in patches:
            for i, byte in enumerate(new):
                csec, ci = divmod(off + i, 2048)
                rs = TRACK2 + csec
                affected.add(rs)
                f.seek(rs * SEC + DATA + ci)
                f.write(bytes([byte]))
        for rs in sorted(affected):
            f.seek(rs * SEC)
            s = bytearray(f.read(SEC))
            fix_mode1(s)
            f.seek(rs * SEC)
            f.write(s)
    print('wrote %s (%d sectors refreshed)' % (out_bin, len(affected)))
    if want_chd:
        chd = os.path.join(out, 'Alshark (rebuild).chd')
        subprocess.run(['chdman', 'createcd', '-i', out_cue, '-o', chd, '-f'],
                       check=True)
        print('wrote %s' % chd)


def selftest():
    """Prove the disassembler reproduces each original bank byte-identical:
    disassemble the carved incbin -> wla -> compare. Guards that we own every byte."""
    sys.path.insert(0, os.path.join(HERE, 'tools'))
    import huc6280dis as dis
    hdr = ['.MEMORYMAP', '  DEFAULTSLOT 0', '  SLOT 0 START $4000 SIZE $2000',
           '.ENDME', '.ROMBANKMAP', '  BANKSTOTAL 1', '  BANKSIZE $2000',
           '  BANKS 1', '.ENDRO', '.BANK 0 SLOT 0', '.ORG $0000']
    for src, off in BANKS:
        name = os.path.splitext(src)[0]
        data = open(os.path.join(HERE, 'incbin', name + '.bin'), 'rb').read()
        s = os.path.join('build', '_dis_' + name + '.s')
        with open(os.path.join(HERE, s), 'w') as f:
            f.write('\n'.join(hdr + dis.to_source(data, 0x4000)) + '\n')
        _run(['wla-huc6280', '-o', 'build/_dis_%s.o' % name, s])
        with open(os.path.join(HERE, 'build', '_dis_%s.link' % name), 'w') as f:
            f.write('[objects]\nbuild/_dis_%s.o\n' % name)
        _run(['wlalink', '-b', 'build/_dis_%s.link' % name,
              'build/_dis_%s.bin' % name])
        out = open(os.path.join(HERE, 'build', '_dis_%s.bin' % name), 'rb').read()
        if out != data:
            i = next(j for j in range(len(out)) if out[j] != data[j])
            raise SystemExit('%s selftest DIFFERS at $%04X' % (name, 0x4000 + i))
        print('%-12s disassembler round-trip: byte-identical (%d B)' % (src, len(data)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--work', default=os.path.join(ROOT, 'work'))
    ap.add_argument('--disc', action='store_true', help='also write patched BIN/CUE')
    ap.add_argument('--chd', action='store_true', help='also build the CHD')
    ap.add_argument('--selftest', action='store_true',
                    help='disassembler round-trip vs original (regression)')
    args = ap.parse_args()

    iso = os.path.join(args.work, 'track02.iso')
    if not os.path.exists(iso):
        raise SystemExit('missing %s - cook your disc first (see tools/cook.py)' % iso)
    cooked = open(iso, 'rb').read()
    carve(cooked)

    if args.selftest:
        selftest()
        return
    patches = assemble_banks(cooked)
    patches += blob_patches()    # bake the VWF font at cooked 0xa1a000
    patches += name_patch(cooked)   # English character names
    patches += menu_patch(cooked)   # English field-menu labels
    patches += battle_patch(cooked)  # English battle prose (failure/level-up/rewards)
    patches += party_array_patch(cooked)  # battle party-name array (from names.tsv)
    patches += hud_patch(cooked)     # English HUD-name font glyphs (table copied in via boot.s)
    patches += location_patch(cooked)  # English town-entry banners (relocated + proportional)
    patches += save_menu_patch(cooked)  # English boot save-menu option buttons (Start/Copy/Delete)
    import reinsert               # splice English from cutscene.tsv into the #-engine blocks
    cut, flagged = reinsert.build(args.work, os.path.join(ROOT, 'script', 'cutscene.tsv'))
    for base, o, n in flagged:
        print('  cutscene OVERFLOW block %08x: %d -> %d' % (base, o, n))
    patches += cut
    if args.disc or args.chd:
        write_disc(patches, args.chd)


if __name__ == '__main__':
    main()
