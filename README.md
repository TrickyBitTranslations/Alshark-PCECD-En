# Alshark - English fan translation (work in progress)

[![Discord](https://img.shields.io/badge/Discord-Join%20the%20server-5865F2?logo=discord&logoColor=white)](https://discord.gg/EZV2RQjCfH)

**UPDATE: 07/01/26** - I'll keep releasing early alpha versions over the next
few weeks. These are NOT stable, will likely invalidate the BRAM save, and
will undoubtedly have bugs. Use at your own risk!

Tooling and translation data for an English patch of **Alshark** (アルシャーク), a
PC Engine Super CD-ROM2 RPG (Right Stuff / Victor Entertainment, 1994).

**Progress and how to help: https://trickybittranslations.github.io/Alshark-PCECD-En/**

No game data is included. This repo holds only original tooling, the translation script, 
and the site.

## Status

Translation and build pipelines are solid and functional. Game-side, a custom font has
been added enabling variable width font rendering.

Most UI screens are translated at this point, with most of them also using the VFW
renderer. In some places monospacing is still used, and we'll probably eventually
deal with it.

**The entire script has been extracted, and a starting machine translation is
being put together as a starting point.

From here, we're hoping japanese speakers who want to help with the translation will
load up the [Script Site](https://trickybittranslations.github.io/Alshark-PCECD-En/)
and begin submitting translation improvements.**

There's a lot of bug hunting still to do. It's a fairly long game, and save states 
aren't a reliable way to test because of how text gets loaded into RAM. The game may 
have already copied strings off the disc to RAM by the time you create the save state, 
so any text in that region will keep showing the old values. Be mindful of this when
submitting issues!

## Tools (`tools/`)

| Script | Purpose |
|---|---|
| `cook.py` | CHD to cooked data track (`work/track02.iso`) |
| `export_script.py` | Script to `script/system1.tsv` + `script/cutscene.tsv` |
| `reinsert.py` | Translated TSV back to a patched CHD (`--check` to fit-check) |
| `tsv.py` | Shared TSV read/write |
| `alshark/` | Engine internals: `cdecc` (EDC/ECC), `blocks`, `textcodec`, `dialogcodec` |

## Releases

The **complete** build (engine/UI asm patches + custom font + all script tiers) is
`rebuild/build.py` - it applies the bank patches and splices in `cutscene.tsv`.
`rebuild/release.py` wraps it to publish an **xdelta patch of the changed bytes only**.

```sh
python rebuild/release.py --check                # validate translations (no game data)
python rebuild/release.py                         # build the EN CD -> rebuild/build/
```

The ~160 KB patch (`dist/alshark-en.xdelta`) is made with `xdelta3` from `extracted/Alshark.bin`
(JP) to `rebuild/build/Alshark.bin` (EN), and published alongside our `.cue` and the JP file's
SHA-256.
