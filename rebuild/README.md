# Alshark rebuild (wla-dx HuC6280)

Builds the Alshark English translation by reassembling the banks we modify. Each original
bank is kept as `.BACKGROUND` and only the routines we change are overwritten (so the diff
is ours, not a whole-bank rewrite); then the variable-width font and translated script are
spliced in and a patched disc / CHD is written.

This repo ships everything needed to build **except the game disc** - bring your own. Cook it
to `../work/track02.iso` first (see `tools/cook.py`); `build.py` carves the original bank
bytes out of that disc at build time, so they are never committed.

## Layout

    src/            wla-dx HuC6280 sources (one .s per bank) + include/
    src/include/    engine symbols / the fixed font ABI (alshark.inc)
    incbin/         vwf_*.bin (VWF font, committed); bank*.bin/boot.bin carved at build (ignored)
    tools/          huc6280dis.py (disassembler) + huc6280_ops.json (wla opcode table)
    build.py        carve -> assemble -> splice font + script -> patched disc/CHD
    build/          output (ignored)

## Prereqs

- `wla-huc6280` + `wlalink` on PATH. Build from https://github.com/vhelin/wla-dx
  (`cmake -DCMAKE_BUILD_TYPE=Release . && make`, copy `binaries/wla-huc6280` + `wlalink`
  to `~/.local/bin`). cmake via `pip install cmake` if not packaged.
- Python 3 (the `tools/alshark` package is used for EDC/ECC + script reinsertion).
- `chdman` for `--chd`.
- `../work/track02.iso` - your disc, cooked (see `tools/cook.py`).

## Use

    make            # carve + assemble + report
    make chd        # also build build/Alshark (rebuild).chd
    make disc       # also write build/Alshark.bin + .cue (EDC/ECC fixed)
    make selftest   # disassembler reproduces the ORIGINAL bank bytes byte-identical

## What it changes

| src       | card bank | logical     | cooked disc     | what                                  |
|-----------|-----------|-------------|-----------------|---------------------------------------|
| bank6d.s  | 0x6D      | $4000-$5FFF | 0x15000-0x17000 | #-engine conversion + VWF render hook |
| boot.s    | (WRAM)    | $2000-$3FFF | 0x00000-0x02000 | loader hook: per-transition font reload |

Plus raw blobs: the VWF font (`incbin/vwf_glyphs.bin` + `vwf_widths.bin`) baked at cooked
0xa1a000, and the translated #-engine script spliced from `../script/cutscene.tsv`.

The variable-width English dialogue font lives in card bank 0x7F and is rendered by the
bank-0x6D hook; the on-disc/asm layout is fixed (see `src/include/alshark.inc`) so swapping
the font is a one-command regenerate - see `../tools/alshark/fontgen.py` and the font
pipeline notes. (Detailed RE write-ups are kept out of this public tree.)

## Disassembler (tools/huc6280dis.py)

Emits wla-dx-syntax asm from bank bytes; the opcode table (`huc6280_ops.json`) is wla-dx's
own, so output re-assembles to the same bytes. Relative branches get label targets (absolute
jmp/jsr take raw addresses); unencodable spans fall back to `.db`. Validated by
`make selftest` (each original bank round-trips byte-identical). Listing example:
`python3 tools/huc6280dis.py incbin/bank6d.bin 4000 57d0 5810`.
