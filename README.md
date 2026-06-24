# Alshark - English fan translation (work in progress)

**UPDATE: 06/23/26** - We're close to releasing a '0.1' release of the translation patch.
The goal is for it to have all known script blocks translated, all critical ui translated
(with some small interaction presentation bugs here and there that don't prevent usage/
progression), and our current blocker list cleared out. We really could use help bashing
on this build to see what things look like.

Tooling and translation data for an English patch of **Alshark** (アルシャーク), a
PC Engine Super CD-ROM2 RPG (Right Stuff / Victor Entertainment, 1994).

**Progress and how to help: https://trickybittranslations.github.io/Alshark-PCECD-En/**

No game data is included. This repo holds only original tooling, the translation script, 
and the site. Once we're ready, the patch will be available via Releases.

## Status

Translation and build pipelines are solid and functional. Game-side, a custom font has
been added to assist in the variable width font feature we've added. Dialog text is 
crisp, clear, and makes efficient use of the space.

Most UI screens are translated at this point, with most of them also using the VFW
renderer. 

**The entire script has been extracted, and a starting machine translation is
being put together as a starting point.

From here, we're hoping japanese speakers who want to help with the translation will
load up the [Script Site](https://trickybittranslations.github.io/Alshark-PCECD-En/)
and begin submitting translation improvements.**

There's a lot of bug hunting still to do. It's a fairly long game, and save states 
aren't a reliable way to test because of how text gets loaded into RAM. The game may 
have already copied strings off the disc to RAM by the time you create the save state, 
so any text in that region will keep showing the old values.

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
python3 tools/reinsert.py --chd  # -> build/Alshark (patched).chd  (script tiers only)
```

## Releases

The **complete** build (engine/UI asm patches + custom font + all script tiers) is
`rebuild/build.py` - it applies the bank patches and splices in `cutscene.tsv`.
`rebuild/release.py` wraps it to publish an **xdelta patch of the changed bytes only** -
never the game. Players bring their own JP Alshark CD, apply the patch, and play.

```sh
python rebuild/release.py --check                # validate translations (no game data)
python rebuild/release.py                         # build the EN CD -> rebuild/build/
python rebuild/release.py --release --tag v0.1    # build + xdelta + publish a GitHub release
```

The ~160 KB patch (`dist/alshark-en.xdelta`) is made with `xdelta3` from `extracted/Alshark.bin`
(JP) to `rebuild/build/Alshark.bin` (EN), and published alongside our `.cue` and the JP file's
SHA-256. Release notes are gathered from `Release-note:` trailers on commits since the last tag,
so opt a change into the notes with e.g.:

    Release-note: Battle menus and item names are now in English

Needs `xdelta3` (`sudo apt-get install -y xdelta3`) and a logged-in `gh`.
