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

## Party-name array  (cooked 0x19afb)  -- TRANSLATED, but NOT the HUD source
A 9-entry array of 8-byte null-terminated name fields: シオン/ショーコ/カル/Ｓ・カル/ジョー/
ウェルダ/ギーデル/ルシア/マモン -> Sion/Shoko/Kal/S. Kal/Joe/Welda/Giedel/Lucia/Mamon.
Translated in battle.tsv (each field = name + 0x00 pad to 8). Confirmed in-emu that this
loads to card 0xEAFB (now reads "Sion..."). NOTE the simple `card = cooked - 0xB000` rule
does NOT hold up here - card 0xEAFB is a separate load, not cooked 0x1AAFB (which is code).

## TODO
- **Battle HUD party names** (right panel, シオン/ショーコ) - NOT FIXED. They do **not**
  read from the 0x19afb array (card 0xEAFB is "Sion" now, HUD still shows シオン), and there
  is no other clean `シオン` name copy left in card RAM (only sentence literals at C4ED,
  1257C). So the HUD name is loaded/cached separately (likely pre-rendered to VRAM at battle
  start, or read from a system-bank/ROM copy). To find it: set a read-bp during a HUD redraw
  (e.g. when PP/MP changes mid-battle) and trace the source. Same likely applies to the
  level-up name blank.
- **Other party-array copies** at cooked 0xbe1c and 0x1512d (field/other contexts) - still JP.

## Battle strings (script/battle.tsv)
| cooked   | what                | class        | status |
|----------|---------------------|--------------|--------|
| 0x19400  | "Failed"            | message-box  | EN     |
| 0x19407  | can't-use-skill     | message-box  | EN     |
| 0x1df90  | can't-use-item-here | message-box  | EN (verified) |
| 0x1956b  | reward window       | result-win   | EN (verified) |
| 0x19469  | level-up window     | result-win   | EN (verified) |
| 0x19530  | learned-skill       | result-win   | EN (offset-preserved) |
| 0x19afb  | party-name array x9 | name fields  | EN (loads to card 0xEAFB; not the HUD source) |
