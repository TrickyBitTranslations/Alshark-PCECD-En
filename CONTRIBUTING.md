# Contributing translations

Thanks for helping translate Alshark. You don't need the game or any tools, just a
GitHub account.

## Suggest a line

1. Open the [translation site](https://trickybittranslations.github.io/Alshark-PCECD-En/)
   or browse `script/*.tsv` here.
2. Find an untranslated line. Hit **Suggest** on the site (it prefills a GitHub
   issue), or open a Translation suggestion issue and fill in the script file, the
   line id (`block_off str_off`), and your English.
3. A bot checks it (markup, control codes, scene byte budget) and comments the
   result. Fix anything it flags by editing the issue.
4. A maintainer applies valid suggestions with a `/apply` comment, which writes your
   line into the TSV and marks it human-reviewed.

## Rules

- Keep every `<XX>` control code from the original line. See [docs/markup.md](docs/markup.md).
- One line per suggestion. Keep it under the scene's byte budget (shown on the site).
- Match the plain, in-character voice of the game; no localization liberties without
  a note.

## The script files

- `system1.tsv` - map and event text.
- `cutscene.tsv` - story and NPC dialogue.
- `names.tsv` - character and item names (shown in cutscenes and the status/equip/item
  menus). Entries 0-25 are the cast; 28+ are weapons/items. These render with the
  proportional font and fit their slots, so English of normal length is fine.

Each row is `block_off, str_off, speaker, text, raw_hex, english, status`. You only
touch `english`. `status` is `human` (a person wrote or reviewed it) or `ignore` (too
trivial to need review); blank means machine/unreviewed.
