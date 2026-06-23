; Alshark engine symbols used by the rebuild (bank 0x6D #-engine render path).
; Logical addresses; bank 0x6D is mapped at $4000-$5FFF (MPR2) during dialogue.

; zero page
.define scriptPtr   $16     ; 16-bit script cursor ($16 lo / $17 hi)
.define fontCodeLo  $F8     ; SJIS trail byte handed to the glyph drawer
.define fontCodeHi  $F9     ; SJIS lead byte

; bank 0x6D byte->SJIS conversion routine ($57D0, dispatch entry $401B)
.define conv_entry    $57D0 ; first instr; the fontpatch hook overwrites it
.define conv_origPath $57E0 ; original hiragana / 2-byte handler (entry after the hook)
.define conv_advance  $5807 ; advance the cursor and return (RTS at $580D)

; bank 0x6D NAME converter ($587E), reached from cutscenes (0x1E slot $401E -> $587E) AND
; directly from menus (status/equip/item). Names are NUL-terminated strings read via ($16);
; $587E handles space/kana/2-byte but sent ASCII letters to its 2-byte default -> garbage.
; We hook its entry, so the fix covers cutscenes and menus alike.
.define nameConvOrig  $587E ; converter entry (orig: LDA ($16) / CMP #$20); we JMP from here
.define nameConvBody  $5882 ; original body just past our 3-byte JMP (orig: BNE $588E)
.define nameAdvRet    $58F4 ; single-byte tail: INC $16 (16-bit) + RTS

; bank 0x6D free slack (was zeros) where the ASCII handler lives
.define slack_5E81    $5E81
.define slack_5EA0    $5EA0

; #-engine glyph render (bank 0x6D)
.define glyphBuf      $4EDA ; 12 rows x 2 bytes; the compositor ($50C0) blits this to VRAM
.define drawHook      $500F ; `JSR $E060` that fills glyphBuf; we overwrite it
.define digitFont     $5B19 ; resident 8x12 digit font, 12 bytes/glyph (0-9), bank 0x6D
.define fontBank      $7F    ; card bank 0x7F (scene-load staging buffer; free mid-scene)
.define fontBase      $CFA0  ; glyphs here when fontBank is in MPR6 (= card_ram 0x2EFA0)
.define fontWidths    $D590  ; 95 advance-widths, right after the 1520B glyph table
.define fontMark      $D600  ; marker byte after the width table (= 0x2F600)
.define glyphRows     $0C    ; rows copied per glyph (full 12-row cell)
.define glyphStride   $10    ; bytes per glyph in the font bank (16, power-of-2)
; VWF advance: the engine tracks cumulative text X in $273F, advancing +$0C/char at 6A:$8115
.define penX          $273F ; engine cumulative text X (work RAM, always mapped)
.define boxAdv        $0C   ; engine's fixed per-char advance (fullwidth = 12 px)
; Menu name VWF: the menu name-read loop ($4057) advances its pixel-X ($00) by a FIXED +12 per
; glyph at $40AE (CLC / LDA #$0C / ADC $00 / STA $00), so long English names overrun the slot into
; BG VRAM. render_hook stashes the glyph width to menuWidth; we re-emit $40AE to advance $00 by
; menuWidth instead (proportional). The name-read routine is MENU-ONLY (cutscene names use 6A:$7FE4)
; and dialogue/cutscene never read menuWidth, so this is scoped to menu names.
.define nameLoopTop   $4080 ; top of the menu name-draw loop (BRA target)
.define nameLoopAdv   $40AE ; the fixed +12 advance; we redirect to a slack trampoline (an INLINE
                            ; re-emit here is +3 bytes vs the original and overruns the loop's exit
                            ; at $40BC = PLA/TAM #$08/RTS, turning it into JMP $4080 = infinite loop)
.define nameLoopExit  $40BC ; the loop's exit (orig PLA/TAM #$08/RTS); BEQ at $4082 targets it
.define nameAdvTramp  $5F43 ; slack trampoline: $00 += menuWidth (VWF) then JMP nameLoopTop (16 bytes)
; item-read ($417E, loop top $41B7) has the same +12 advance at $41E5 with no spare bytes after its
; branch; redirect it to its own slack trampoline (the name fix proved this pattern). Confirmed
; glyph advance - the loop reads/converts/draws each item-name glyph at $41B7.
.define itemLoopAdv    $41E5 ; CLC of the item +12 advance; overwrite with JMP itemAdvTramp
.define itemLoopRejoin $41EC ; original high-byte handling (CLA/ADC $01/STA $01/BRA $41B7)
.define itemAdvTramp   $5F53 ; slack trampoline after nameAdvTramp (16 bytes from $5F43)
; member-picker name loop ($40C0, reads the $412A name copy via the $411E offset table) has the same
; FIXED +12 advance at $410F but was never hooked -> picker names monospaced. Redirect to a trampoline
; (placed in the $5CC0 slack after menu_label_char, since the $5F18 region is full).
.define pickerLoopAdv  $410F ; CLC of the picker +12 advance; overwrite with JMP pickerAdvTramp
.define pickerLoopTop  $40E1 ; the picker loop top (BRA target)
; a 4th name loop ($427E, renders the selected entry of a runtime string list at $7AD6 via the name
; converter $587E) has the same FIXED +12 advance at $42AC, also unhooked -> same monospaced bug.
.define picker2LoopAdv $42AC ; CLC of the 4th-loop +12 advance; overwrite with JMP picker2AdvTramp
.define picker2LoopTop $427E ; the 4th loop top (BRA target)
; render-hook scratch in the PROVEN-safe slack (the fontpatch region; $5F60+ is engine BSS)
.define glyphFlag     $5F40 ; 1 = current glyph is ours (ASCII), 0 = let BIOS draw it
.define glyphIdx      $5F41 ; ASCII index (char - 0x20) of the current glyph
.define menuWidth     $5F42 ; render_hook stashes the current glyph width here for $40AE

; Menu LABEL drawer ($5702 body, loop top $5748): draws the field-menu labels (Status/Item/...)
; from the 0x0d-separated SJIS lists in bank 0x6B. The loop reads each byte from ($16); a byte
; >= $40 is taken as a 2-byte SJIS lead (lead->$F9, trail->$F8, JSR $5003 draw, $16+=2, pen $00+=12);
; a byte < $40 takes the resident digit/half-width path ($57B5: $F8=byte, JSR $503E, $16+=1, $00+=8).
; So ASCII LETTERS ($41-$7A) wrongly hit the 2-byte path -> blank. We intercept the $40 split and
; route printable ASCII (except digits, which keep the digit font for HP/MP numbers) to a 1-byte
; path that flags the glyph as ours (glyphFlag/glyphIdx) so render_hook draws our VWF font, advancing
; pen $00 by the real glyph width (menuWidth). Digits and true SJIS fall through to the originals.
.define menuLabelLoop   $5748 ; top of the label byte loop (our handler JMPs back here)
.define menuLabelSplit  $578C ; the CMP #$40 / BCC $57B5 split; we overwrite with JMP menu_label_char
.define menuLabel1byte  $57B5 ; original digit/half-width path (STA $F8 / JSR $503E ...)
.define menuLabel2byte  $5790 ; original 2-byte SJIS path (STA $F9 / LDY #1 / LDA ($16),Y ...)
.define menuDraw        $5003 ; sets glyphBuf ptr + JSR $E060(->render_hook) + blit; RTS
.define menu_label_slack $5CC0 ; free zero run $5CC0-$5D38 (~0x78 B) in the bank 0x6D code region
