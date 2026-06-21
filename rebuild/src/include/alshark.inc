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
.define nameAdvTramp  $5F43 ; slack trampoline: $00 += menuWidth (VWF) then JMP nameLoopTop
; render-hook scratch in the PROVEN-safe slack (the fontpatch region; $5F60+ is engine BSS)
.define glyphFlag     $5F40 ; 1 = current glyph is ours (ASCII), 0 = let BIOS draw it
.define glyphIdx      $5F41 ; ASCII index (char - 0x20) of the current glyph
.define menuWidth     $5F42 ; render_hook stashes the current glyph width here for $40AE
