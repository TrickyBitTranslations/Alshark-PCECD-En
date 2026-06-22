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

## TODO - still Japanese (map the same way before translating)
- **Level-up window** @ cooked 0x19469 (card 0xE469): 7 stat numbers (MaxPP, MaxMP,
  IQ, R_Str, L_Str, Agl, Drb) + a name slot (the `　　　　` blank). Find its inserter
  (likely bank 0x6E too) and its 7 `TII` dests + the name-insertion offset.
- **Learned-skill window** @ cooked 0x19530 (card 0xE530): a skill-name slot
  (the `　　　　　　　　` blank, runtime-written). Find the name-insertion offset.
- **Party HUD names** (right panel, シオン/ショーコ): drawn from a hardcoded JP name
  copy, not the $D066 table. 5 raw `シオン` copies exist in card RAM
  (C4ED, E409, E571, EAFB, 1257C) - E409/E571 are the message literals; find which
  feeds the HUD and translate that source (4-byte "Sion" fits the 6-byte slot).

## Battle strings (script/battle.tsv)
| cooked   | what                | class        | status |
|----------|---------------------|--------------|--------|
| 0x19400  | "Failed"            | message-box  | EN     |
| 0x19407  | can't-use-skill     | message-box  | EN     |
| 0x1df90  | can't-use-item-here | message-box  | EN (verified) |
| 0x1956b  | reward window       | result-win   | EN (offset-preserved) |
| 0x19469  | level-up window     | result-win   | JP (TODO) |
| 0x19530  | learned-skill       | result-win   | JP (TODO) |
