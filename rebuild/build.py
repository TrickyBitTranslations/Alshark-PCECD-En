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
         ('bank6b.bin', 0x0b000, 0x2000), ('bank68.bin', 0x2be1000, 0x2000)]

# asm source (in src/) -> cooked disc offset of the bank's first byte.
BANKS = [
    ('bank6d.s', 0x15000),   # #-engine render/conversion bank ($4000-$5FFF): VWF render hook
    ('boot.s',   0x00000),   # boot/WRAM image ($2000-$3FFF): per-transition font reload
    ('bank6b.s', 0x0b000),   # field banner bank ($A000-$BFFF): proportional location-name banner
    ('bank68.s', 0x2be1000), # anime cutscene PLAYER ($4000-$5FFF, recno $57C2): IRQ vblank-path hook
]

# raw blobs spliced onto disc: (cooked offset, incbin file). The VWF font (committed asset).
FONT_OFF = 0xa1a000            # cooked; = abs LBA $00223A, loaded to card bank 0x7F $CFA0
# Anime-cutscene subtitle blob: the FULL recno/play-ordered line table, spliced sector-aligned at the
# disc free pool (0x9dd906 region). recno = cooked/2048 = 0x9de000/2048 = 0x13BC; bank68.s CD_READs it
# once at cutscene init (before music) into card bank 0x7D, lifting the resident ~160B table cap. See
# noredist/docs/findings/cutscene-player.md "STREAMED-SUBTITLE BUILD PHASE".
SUBS_BLOB_OFF = 0x9de000       # cooked; sector-aligned (0x9de000/2048 = 0x13BC); 0x7D dest, 8KB free
BLOBS = [(FONT_OFF, 'vwf_glyphs.bin'), (FONT_OFF + 0x5f0, 'vwf_widths.bin'),  # 1520B glyphs
         (SUBS_BLOB_OFF, 'cutscene_subs_blob.bin')]


def carve(cooked):
    """Slice the original banks the asm .BACKGROUNDs out of the user's cooked disc."""
    os.makedirs(os.path.join(HERE, 'incbin'), exist_ok=True)
    for name, off, ln in CARVE:
        open(os.path.join(HERE, 'incbin', name), 'wb').write(cooked[off:off + ln])
    gen_hud_idx()                  # incbin/hud_en_idx.bin for boot.s copy_hud_names (must precede assembly)
    gen_cutscene_text()            # incbin/cutscene_subs_blob.bin (font + line table, spliced on disc at 0x9DE000)


def blob_patches():
    return [(off, open(os.path.join(HERE, 'incbin', n), 'rb').read()) for off, n in BLOBS]


# Character/item name table (bank 0x7A $D066 = cooked 0x784066): NUL-terminated, scan-indexed
# strings, edited via script/names.tsv (entries 0..25 are the cast; 26+ weapons/items). Scan
# indexing needs no repointing, so entries grow/shrink freely; the table must fit before the
# next block at 0x785000.
NAME_TBL = 0x784066


# The menu reads weapon/armor/item names from a HARDCODED base pointer (original $7157, which
# points at entry 27 - the "------" item-ID-0 placeholder; item IDs in the game data are numbered
# relative to it) loaded at code $4191/$4204 in bank 0x6D. Our English cast names are longer, so the
# item region shifts; we repoint that base to entry 27's actual logical address. (Earlier this said
# entry 28 and was off by one - it shifted EVERY item name back by one entry, first item -> blank.)
# The cast is read from $7066 (table start, scan-indexed) so it needs no fix-up. A9 <lo> 85 16 A9 <hi> 85 17.
ITEM_BASE_SITES = (0x191, 0x204)   # bank-0x6D offsets of the LDA #lo of each item-base load
BANK6D_OFF = 0x15000               # cooked offset of bank 0x6D

# The SHOP / buy menu reads item names through a SEPARATE base load in bank 0x6A (cooked 0x9a76), which
# maps the name table at MPR6 ($C000-$DFFF), so its pointer is the $Dxxx form of the same base
# ($D066 + off_item = item_base + $6000). Original $D157 (un-repointed) = entry 26 in our longer table,
# so the shop list (and the item it actually sells) was shifted -1. Repoint it too. Same byte pattern.
SHOP_BASE_SITE = 0x9a76            # cooked offset of bank 0x6A's item-name base load (A9 <lo> 85 16 A9 <hi> 85 17)


def name_patch(cooked):
    import tsv
    rows = list(tsv.read(os.path.join(ROOT, 'script', 'names.tsv')))
    blob = bytearray()
    off_item = None
    for k, r in enumerate(rows):
        if k == 27:
            off_item = len(blob)            # byte offset of the item-base entry (orig $7157 = entry 27)
        en = r.get('english', '')
        blob += (en.encode('latin-1') if en else bytes.fromhex(r['raw_hex']))
        blob += b'\x00'
    if NAME_TBL + len(blob) > 0x785000:
        raise SystemExit('name table overflow: %d > %d' % (len(blob), 0x785000 - NAME_TBL))
    patches = [(NAME_TBL, bytes(blob))]
    item_base = 0x7066 + off_item           # table base $7066 (MPR3) + item-base entry offset
    lo, hi = item_base & 0xff, item_base >> 8
    for site in ITEM_BASE_SITES:
        patches.append((BANK6D_OFF + site + 1, bytes([lo])))   # LDA #lo operand
        patches.append((BANK6D_OFF + site + 5, bytes([hi])))   # LDA #hi operand
    shop_base = item_base + 0x6000          # bank 0x6A maps the table at MPR6 ($Cxxx), not MPR3 ($7xxx)
    patches.append((SHOP_BASE_SITE + 1, bytes([shop_base & 0xff])))   # LDA #lo operand
    patches.append((SHOP_BASE_SITE + 5, bytes([shop_base >> 8])))     # LDA #hi operand
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

# The level-up / battle name window (bank 0x6F routine @ $8A97) copies LEN_TBL[$8AEF] bytes of the name
# from the array, then pads to 8 with $01. Those lengths are the JAPANESE byte-counts, so our shorter
# English names OVER-copy and drag the array's NUL padding into the result string -> the $5748 drawer
# hits the NUL and the level-up window terminates right after the name (only the name shows). Rewrite the
# length table with the English byte-lengths. The offset table @ 0x19ae3 maps each of the 12 slots to its
# array entry (= byte offset / 9), so names with multiple slots stay consistent.
NAME_OFF_TBL = 0x19ae3
NAME_LEN_TBL = 0x19aef


def party_array_patch(cooked):
    from alshark import cast
    names = list(cast.party_names(ROOT))
    patches = []
    for i, name in enumerate(names):
        off = PARTY_ARRAY + i * 9
        if len(name) > 8:
            raise SystemExit('party name %r > 8 bytes for the array field' % name)
        if cooked[off + 8] != 0x00:
            raise SystemExit('party array 0x%x not as expected' % off)
        patches.append((off, name.encode('latin-1').ljust(8, b'\x00')))
    off_tbl = cooked[NAME_OFF_TBL:NAME_OFF_TBL + 12]        # slot -> array entry (offset / 9)
    patches.append((NAME_LEN_TBL, bytes(len(names[b // 9]) for b in off_tbl)))
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


# Anime-cutscene subtitle text. build.py pre-renders each line to a proportional 1bpp pixel strip and packs
# the play-ordered strips into the blob streamed to card bank 0x7D (the runtime expands them to VRAM tiles).
SUBS_UNDER_OFF = 0x1F00         # 0x7D runtime scratch (image cells saved from under the band); table must stay below
SUBS_MAX_TILES = 30            # one line spans the free tile gap $7C5-$7E2 (30 tiles); centred in the 32-col band


def _vwf_widths(glyphs):
    """Per-glyph advance width (ink width + 1px gap) for the 95 sub_glyphs (ASCII $20-$7E, 8 rows each, 1bpp,
    bit 0x80=leftmost). A blank glyph (space) advances 3px."""
    w = []
    for i in range(len(glyphs) // 8):
        g = glyphs[i * 8:i * 8 + 8]
        ink = max((c + 1 for row in g for c in range(8) if row & (0x80 >> c)), default=0)
        w.append(ink + 1 if ink else 3)
    return w


def _vwf_strip(text, glyphs, widths):
    """Pre-render a subtitle line to a proportional 1bpp pixel strip: place each glyph at a pixel cursor,
    advancing by its width, then slice into 8x8 tiles. Returns (n_tiles, strip_bytes), n_tiles*8 bytes,
    tile-major then row (strip[t*8+r] = row r of tile t, bit 0x80=leftmost)."""
    total = sum(widths[min(max(ord(c) - 0x20, 0), len(widths) - 1)] for c in text)
    n_tiles = min(SUBS_MAX_TILES, max(1, (total + 7) // 8))
    W = n_tiles * 8
    pix = [bytearray(W) for _ in range(8)]               # pix[row][col] = 0/1
    x = 0
    for ch in text:
        i = min(max(ord(ch) - 0x20, 0), len(widths) - 1)
        g = glyphs[i * 8:i * 8 + 8]
        for r in range(8):
            for c in range(8):
                if g[r] & (0x80 >> c) and x + c < W:
                    pix[r][x + c] = 1
        x += widths[i]
    strip = bytearray()
    for t in range(n_tiles):
        for r in range(8):
            byte = 0
            for c in range(8):
                if pix[r][t * 8 + c]:
                    byte |= (0x80 >> c)
            strip.append(byte)
    return n_tiles, bytes(strip)


def gen_cutscene_text():
    """From script/cutscene_subs.tsv (recno_hex<TAB>line), build the streamed subtitle blob loaded into card
    bank 0x7D (verified free during the cutscene). Layout in 0x7D (= $A000 when MPR-swapped in):
      $A000 ($0000): the play-ordered line table - per line: n_tiles (1 B) then the PROPORTIONAL pixel strip
                     (n_tiles*8 B, 1bpp pre-rendered); terminator n_tiles=0. vblank_hook walks to the current
                     line by play-count, copies its strip out, and expands the 1bpp rows into 4bpp VRAM tiles.
      $BF00 ($1F00): runtime scratch (not baked) - the image BAT cells saved from under the band, so the band
                     is drawn non-destructively (restored, not cleared-to-black, when it moves).
    Spliced on disc at SUBS_BLOB_OFF, CD_READ once at cutscene init. Play order = ascending recno (crater
    voice clips are contiguous, so recno sorts = clip order)."""
    glyphs = open(os.path.join(HERE, 'incbin', 'sub_glyphs.bin'), 'rb').read()   # 95 glyphs x 8 (subfont.py)
    widths = _vwf_widths(glyphs)
    rows = []
    for ln in open(os.path.join(ROOT, 'script', 'cutscene_subs.tsv'), encoding='utf-8'):
        ln = ln.rstrip('\n')
        if not ln or ln.lstrip().startswith('#') or '\t' not in ln:
            continue
        k, text = ln.split('\t', 1)
        rows.append((int(k, 16), text))                  # recno = play ORDER (subtitle keyed by play count)
    rows.sort()                                          # ascending recno = play order (= clip order)
    table = bytearray()
    for recno, text in rows:
        n_tiles, strip = _vwf_strip(text, glyphs, widths)
        table += bytes([n_tiles]) + strip
    table += bytes(1)                                    # terminator (n_tiles = 0)
    if len(table) > SUBS_UNDER_OFF:                      # the table must stay clear of the 0x7D under-buffer
        raise SystemExit('cutscene subtitle table %d B overruns the 0x7D under-buffer at %#x'
                         % (len(table), SUBS_UNDER_OFF))
    open(os.path.join(HERE, 'incbin', 'cutscene_subs_blob.bin'), 'wb').write(table)


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
    cmd = ['wla-huc6280', '-k', '-I', 'incbin', '-o', obj, os.path.join('src', src)]
    _run(cmd)
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
    """English boot save-menu (Start/Copy/Delete + the copy/delete/error dialogs), COLD-SAFE.

    The menu is the System Card BRAM-style UI (banks 0x68-0x6C). The earlier version relocated the
    strings to $4A60 in bank 0x68 and "verified it free" - but only in the WARM menu. Bank 0x68 is
    DUAL-SOURCE: boot loads it from disc 0x2be1000 (so the warm menu showed the text) while the
    post-death COLD path reloads bank 0x68 from cooked 0x5000, where $4A60 is real code. So after
    die -> title -> Run the strings rendered empty and the credit black-screened. Fix: relocate into
    BANK 0x69 (disc 0x4801000) - the one save-menu bank with a single cold-reloaded source (its
    descriptor table already survives the cold path). The free space is the JP strings we repoint
    away from: the 6 JP dialog strings are back-to-back (430 contiguous bytes at $69BF), and ALL 7
    strings (option + dialogs) pack into that one region. (NB: a 40B disc-zero gap at $79CD is NOT
    usable - it's a runtime glyph/BG staging buffer.) Full bank map: noredist/docs/findings/savemenu-banks.md.

    The option box still needs widening to fit "Start/Copy/Delete"; those two descriptor bytes
    (0x48018b5/b7) live in bank 0x69, so they are cold-safe. Two dialogs are trimmed a few chars to
    fit the 430B region. The "TrickyBit" credit is NOT here - its 384B of pre-baked tiles do not fit
    bank 0x69, so it must be re-rendered from the menu font (Stage 2), not DMA'd as tiles.
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

    # the option box is narrow (widened below); the 6 dialog boxes are already wide (~13 chars/line).
    option = (0x48018ad, ['Start', 'Copy', 'Delete'])
    dialogs = [
        (0x48018dd, ['Copy slot has', 'data. Erase', 'it to copy.']),                  # msg3
        (0x48018ed, ['Backup RAM is', 'full. Erase', 'a file.']),                      # msg4 (trimmed)
        (0x48018fd, ['No data.', 'Cannot copy.']),                                     # msg5 (trimmed)
        (0x480190d, ['Erase this', 'save data?', '    Yes  No']),                      # msg6 (Yes col4 / No col9)
        (0x480191d, ['Backup RAM', 'is full.', 'Erase files,', 'then restart.']),      # msg7 (trimmed)
        (0x480192d, ['A BIOS error.', 'Please reset.']),                              # msg8 (trimmed)
    ]
    # cold-safe homes in bank 0x69 (disc 0x4801000, org $6000):
    # ALL strings go into the 6 freed JP dialog strings = 430 contiguous bytes at $69BF (disc
    # 0x48019bf). That region is genuinely free at RUNTIME (display-only string data; confirmed by
    # reading it back live). The earlier 40-byte "gap" at $79CD was zero on disc but is a runtime
    # glyph/BG STAGING buffer -> putting the option there showed as BG garbage and ate the text.
    # "zero on disc" != "free at runtime". Dialogs are trimmed a few chars to leave room for the option.
    REGION_DISC, REGION_CAP = 0x48019bf, 430
    def log(d):
        return 0x6000 + (d - 0x4801000)
    if cooked[0x48018ad:0x48018af] != b'\x77\x69':        # sanity: option entry pointer = $6977
        raise SystemExit('save-menu option entry pointer not as expected')
    patches, off = [], 0
    for entry, lines in [option] + dialogs:               # pack option + dialogs into the freed region
        blob = msg(lines)
        if off + len(blob) > REGION_CAP:
            raise SystemExit('save-menu strings overflow bank-0x69 region (%d > %d)' % (off + len(blob), REGION_CAP))
        d = REGION_DISC + off
        patches.append((d, blob))                                          # English string (overwrites freed JP)
        patches.append((entry, bytes([log(d) & 0xff, log(d) >> 8])))       # repoint the descriptor
        off += len(blob)
    # widen ONLY the option box (dialog boxes are already wide): row stride MUST match the width
    patches.append((0x48018b5, b'\x40\x01'))     # option box row stride 0x0060 -> 0x0140 ($8D*0x20)
    patches.append((0x48018b7, b'\x0d'))         # option box width param 0x06 -> 0x0d ($8D = 10)
    return patches


def formation_patch(cooked):
    """In-game formation (party-order) menu (the "Plan" submenu) at cooked 0xb3f9. It's drawn by the
    bank-0x6D VWF loop like the other field menus, but export_menu.py's run finder skips it: the block
    interleaves SJIS glyphs with raw ASCII spaces (0x20) and slot digits (0x31-0x35), which break run
    detection. The full-width spaces position the two columns, so translate ONLY the three text
    segments IN PLACE, padded with spaces (a 0x00 pad would terminate the block and hide the columns)."""
    import alshark.menucodec as menucodec
    segs = [
        (0xb3f9, '隊列を変更します。', 'Formation'),           # title; kept short + single-word so the confirm prompt (drawn over it) fully covers it
        (0xb426, '＜現隊列＞', '<Current>'),                                  # ＜現隊列＞
        (0xb433, '＜新隊列＞', '<New>'),                                      # ＜新隊列＞
        (0xb4a8, 'これでよろしいですか？', 'Confirmation?'),                  # confirm prompt; single word (no spaces) so it cleanly covers the "Formation" title it draws over (spaces don't clear)
    ]
    patches = []
    for off, jp, en in segs:
        jb = jp.encode('shift_jis')
        if cooked[off:off + len(jb)] != jb:
            raise SystemExit('formation menu seg 0x%x not as expected' % off)
        eb = menucodec.encode(en)
        if len(eb) > len(jb):
            raise SystemExit('formation menu %r too long (%d > %d)' % (en, len(eb), len(jb)))
        patches.append((off, eb + b'\x20' * (len(jb) - len(eb))))   # space-pad, NOT 0x00
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


def title_credit_patch(cooked):
    """Add a 'TrickyBit' translator credit to the title screen as BG tiles - no code hook.
    The title routine (bank 0x69 $6000, both warm + post-death paths) uploads its BG tilemap from
    $72CD -> VRAM $0000 (0x700 B, 32x28) and its BG tiles from $79CD -> VRAM $1000 (0x2300 B, spanning
    into bank 0x6A). The baked copyright is tiles 0x1D5-0x1F9 on BAT rows 22 + 24; tiles 0x1FA+ are
    free and BAT rows 25-27 are blank. So we drop the pre-rendered credit glyph tiles
    (script/title_credit.bin: 4bpp, all four planes = the glyph -> color 15 white in palette 0,
    matching the copyright) into the free tile slots and write their tile numbers into a blank BAT
    row - both regions the title already uploads. Cold-safe: it rides the exact data that draws the
    (verified-present) copyright on every path to the title. Regenerate the tiles with
    tools/alshark/gen_title_credit.py."""
    blob = open(os.path.join(ROOT, 'script', 'title_credit.bin'), 'rb').read()
    n = len(blob) // 32
    if n == 0 or len(blob) % 32:
        raise SystemExit('title-credit: bad tile blob (%d bytes)' % len(blob))
    TILE0 = 0x1FA                              # first free BG tile after the copyright (last is 0x1F9)
    TILE_DISC = 0x480490D                      # disc offset of tile 0x1FA in the BG-tile source ($79CD)
    BAT_DISC = 0x48022CD                       # BAT source ($72CD bank 0x69) -> VRAM $0000
    ROW, NCOL = 26, 32                         # blank BAT row below the copyright; tilemap is 32 wide
    if any(cooked[TILE_DISC:TILE_DISC + n * 32]):
        raise SystemExit('title-credit: BG tile slots 0x%X+ are not free' % TILE0)
    row = cooked[BAT_DISC + ROW * 64:BAT_DISC + ROW * 64 + 64]
    if any((row[i] | (row[i + 1] << 8)) not in (0x0000, 0x0100) for i in range(0, 64, 2)):
        raise SystemExit('title-credit: BAT row %d is not blank' % ROW)
    col = (NCOL - n) // 2                      # center the credit
    patches = [(TILE_DISC, blob)]              # the glyph tiles
    for i in range(n):                         # the BAT row: palette 0 | tile number, per column
        e = TILE0 + i
        patches.append((BAT_DISC + ROW * 64 + (col + i) * 2, bytes([e & 0xff, e >> 8])))
    return patches


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
    patches += formation_patch(cooked)  # English in-game formation (party-order) menu
    patches += title_credit_patch(cooked)  # 'TrickyBit' translator credit on the title (BG tiles)
    import reinsert               # splice English from cutscene.tsv into the #-engine blocks
    cut, flagged = reinsert.build(args.work, os.path.join(ROOT, 'script', 'cutscene.tsv'))
    for base, o, n in flagged:
        print('  cutscene OVERFLOW block %08x: %d -> %d' % (base, o, n))
    patches += cut
    if args.disc or args.chd:
        write_disc(patches, args.chd)


if __name__ == '__main__':
    main()
