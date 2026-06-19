# Markup codes in the script

The `english` column isn't plain text. The original lines carry control codes the
game needs, written as `<XX>` (one hex byte). Don't strip them out.

## Control codes

`<XX>` is a control byte from the original: colors, name inserts, line and page
breaks, box layout. The full grammar isn't mapped yet, so the rule for now is
simple: **keep every `<XX>` from the original line in your translation, in the same
order**, and write your English in between. The bot rejects a suggestion that drops
one.

Example. Original:

    #<04>$<00>#<05>...some line...

Keep the same codes around the English:

    #<04>$<00>#<05>Good morning.

The `#`, `$`, `%` characters you see are literal markers the engine reads; keep them
too. The one code you don't need to type is the trailing `<00>` that ends a line, the
build adds it for you.

## Text

Type normal letters, numbers, and `. , ! ? -` and spaces. The dialogue font renders
English full-width. If a glyph is missing it shows blank or wrong, so flag anything
exotic in your suggestion.

## Length

Each scene's text shares one 8 KB block in memory. The site shows a budget bar per
scene; keep the scene under its cap. A dialogue row is one box and wraps at about 28
characters, so split a long line into shorter ones rather than overflowing the box.
