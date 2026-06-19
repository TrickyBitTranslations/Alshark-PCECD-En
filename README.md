# Alshark - English fan translation (work in progress)

Tooling and translation data for an English patch of **Alshark** (アルシャーク), a
PC Engine Super CD-ROM2 RPG (Right Stuff / Victor Entertainment, 1994).

**Progress and how to help: https://trickybittranslations.github.io/Alshark-PCECD-En/**

No game data is included. Bring your own `Alshark (Japan).chd` and a PC Engine Super
System Card BIOS. This repo holds only original tooling, the translation script, and
the site.

## Status

The edit pipeline round-trips byte-perfect on the main story script (32 blocks, 940
strings) and English renders in-game via the existing font. What is left is mostly
content: the other two text tiers, fitting longer lines, and the translation itself.

## How text is stored

Three systems:

1. Map/event script: pointer-table blocks in the data track, plain Shift-JIS. Cleanest
   tier, handled end to end.
2. Cutscene dialogue (`#` engine): full-width SJIS, with hiragana stored as single
   bytes in the half-width katakana range.
3. Menu engine (`C`/`R`/`E` codes): full-width SJIS with ASCII control codes.

## Tools (`tools/`)

| Script | Purpose |
|---|---|
| `cook.py` | CHD to cooked data track (`work/track02.iso`) |
| `export_script.py` | Script to `script/system1.tsv` + `script/cutscene.tsv` |
| `reinsert.py` | Translated TSV back to a patched CHD (`--check` to fit-check) |
| `tsv.py` | Shared TSV read/write |
| `alshark/` | Engine internals: `cdecc` (EDC/ECC), `blocks`, `textcodec`, `dialogcodec` |

Needs Python 3 and `chdman` (`mame-tools`, or `brew install rom-tools`).

## Typical loop

```sh
python3 tools/cook.py            # CHD -> work/track02.iso
python3 tools/export_script.py   # -> script/system1.tsv + cutscene.tsv
# fill in the english column, then:
python3 tools/reinsert.py --chd  # -> build/Alshark (patched).chd
```
