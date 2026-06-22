# Battle text map (inline strings + runtime insertion offsets)

Battle text is **inline data interleaved with engine code** - there is no pointer
table (the tier-1 block finder finds nothing here). Strings are edited via
`script/battle.tsv` and spliced in place by `battle_patch()` in `rebuild/build.py`,
preserving every control byte as `<XX>` markup (textcodec round-trips exactly).

## Address mapping
- This battle code/text is the **bank 0x6F resident region**. Runtime card-RAM
  address and cooked-disc offset relate by: **card = cooked - 0xB000**
  (e.g. cooked 0x1942b = card 0xE42b; cooked 0x1956b = card 0xE56b).
- Bank windows seen at runtime: MPR2=$4000 = bank 0x6D (the label drawer),
  MPR3=$6000 = bank 0x6E (battle logic / inserters), MPR4=$8000 = bank 0x6F
  (the resident strings).

## Renderer
- All of it is drawn by the **bank 0x6D label loop at `$5748`** (the same routine
  we VWF-hooked for the field menu via `menu_label_char`). Confirmed by read-bp:
  command menu AND the reward window both break at PC `$574A`, MPR2=0x6D.
- `<0d>` = line break; `<00>` = terminator. ASCII (1 byte) renders proportional
  (VWF); SJIS (>=$40, 2 bytes) renders full-width; **digits 0x30-0x39 render via
  the original fixed-width digit font** (the VWF hook excludes them).

## Two string classes (this is the gotcha)
1. **Message-box strings** - free-flowing prose, no runtime insertion. Safe to
   translate to any-length English; renders VWF. (Failure, can't-use, etc.)
2. **Result-window strings** - the level-up and reward windows. Engine code writes
   numbers (and names) into the string at **hardcoded absolute offsets** before the
   draw. Changing the byte layout moves the text out from under those writes ->
   garbled numbers cascading into VRAM/background corruption. **Each segment's byte
   length MUST equal the Japanese**, so the insertion slots stay put.

## Reward window  (string @ cooked 0x1956b, card 0xE56b)  -- MAPPED
Inserter: **bank 0x6E, ~`$7EF0`**. For each value it converts to 5 decimal digits
(`JSR $8039`) then `TII $26B2,<dest>,#$0005` into the string:
| value   | TII dest | card    | cooked   | string offset |
|---------|----------|---------|----------|---------------|
| Exp     | `$8590`  | 0xE590  | 0x19590  | 37            |
| Credits | `$85A2`  | 0xE5A2  | 0x195A2  | 55            |
| Scrap   | `$85B4`  | 0xE5B4  | 0x195B4  | 73            |

JP segment byte lengths (split on `<0d>`): **[24, 17, 17, 17, 14]**
(seg = 6-byte header + 18 text; then 12-byte label + 5-byte `00000` x3; then 14).
English must match these lengths (pad labels with spaces); `00000` stays at 37/55/73.
Status: translated offset-preserving in battle.tsv (verify in-game).

## Level-up window  (string @ cooked 0x19469, card 0xE469)  -- DONE
7 stat-number slots (logical $849C/$84AE/$84C0/$84D2/$84E4/$84F6/$8508 = cooked
0x1949C..0x19508, spacing 18) + a name blank at logical $846F (cooked 0x1946F, the
`　　　　` run). JP segment byte lengths: **[18,18,0,17,17,17,17,17,17,17,16,10]**.
Translated offset-preserving (stat labels left as the game's full-width Latin so number
columns stay aligned); verified clean in-game. The name blank still shows JP (see HUD names).

## Learned-skill window  (string @ cooked 0x19530, card 0xE530)  -- DONE
Segments [22,16,12]; the 16-byte `　　　　　　　　` is a runtime skill-name blank.
Translated offset-preserving (skill-name blank kept). Not yet visually verified (needs a
skill-learn event) but same proven method.

## Party-name array  (cooked 0x19afb)  -- DONE, driven by names.tsv
A 9-entry array of 8-byte null-terminated name fields (stride 9): シオン/ショーコ/カル/Ｓ・カル/
ジョー/ウェルダ/ギーデル/ルシア/マモン. Patched by `party_array_patch()` in build.py from
**script/names.tsv** (via `alshark.cast.party_names`) - ASCII, padded to 8. Loads to card 0xEAFB.
NOTE the simple `card = cooked - 0xB000` rule does NOT hold here - card 0xEAFB is a separate load.

## Battle HUD party names (right panel)  -- DONE, data patch (NO code/BIOS work)
Earlier notes here wrongly concluded this needed the System Card BIOS. It does not. The HUD
name is **background tiles**, and the names are stored as **pre-built tile-ref data**, not text:
- **Name writer**: bank 0x73 `$5E22` loop copies **8 tile-refs per member** from a table to the
  BAT (`LDX #$08`). The per-member source table is at **cooked 0x3f790a** (16 bytes = 8 tile-refs
  of `(font_index, 0x70)` each; member m at +m*16). (`$5D2F` nearby draws the box/bars frame -
  that's what the misleading $E036/$4089 traces were catching.)
- **Font**: an 8x8 half-width tile font at **cooked 0x39000** (32 bytes/glyph, VRAM tile
  0x200+index, planes: per row [plane0,0xFF] x8 then repeated). Indices map to JIS X 0201
  (index = SJIS half-width code - 0xA0); it is **katakana-only, no Latin**. The load covers
  indices 0x00-0xF7 (VRAM tiles 0x200-0x2F7).
- **Fix (pure data)**: render English glyphs from our font, inject into spare font slots, and
  rewrite the name table. `tools/alshark/hudnames.py` renders each name PROPORTIONALLY in 04b-03,
  slices it into 8x8 tiles, and writes `script/hud_names_patch.json`; `hud_patch()` splices it.
  Names come from **script/names.tsv** (same source as the array). Verified in-game.
- **Spare-slot gotcha**: font slots 0x70-0xA3 are blank but USED as HUD box/bar/gauge graphics
  (referencing them showed glyphs as garbage in the bottom-right). Use the clean blank run
  **0xC0-0xEB** (44 slots), well clear of all HUD graphics.
The level-up / learned-skill name blanks are a separate (result-window) mechanism, already
offset-preserved above.

## TODO - other
- **Party-array copies** at cooked 0xbe1c and 0x1512d (field/other contexts) - still JP. Could be
  driven from names.tsv the same way as 0x19afb if a context needs them.

## Battle strings (script/battle.tsv)
| cooked   | what                | class        | status |
|----------|---------------------|--------------|--------|
| 0x19400  | "Failed"            | message-box  | EN     |
| 0x19407  | can't-use-skill     | message-box  | EN     |
| 0x1df90  | can't-use-item-here | message-box  | EN (verified) |
| 0x1956b  | reward window       | result-win   | EN (verified) |
| 0x19469  | level-up window     | result-win   | EN (verified) |
| 0x19530  | learned-skill       | result-win   | EN (offset-preserved) |
| 0x19afb  | party-name array x9 | name fields  | EN (from names.tsv via party_array_patch) |
| 0x3f790a | HUD name tile-refs   | tile table   | EN (from names.tsv via hudnames.py + hud_patch) |
