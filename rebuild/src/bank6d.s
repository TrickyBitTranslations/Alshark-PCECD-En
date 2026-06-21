; Alshark dialogue overlay - bank 0x6D (#-engine render/conversion bank).
; Card RAM bank 0x6D maps to logical $4000-$5FFF (MPR2); on disc this page is cooked
; offset 0x15000-0x17000. Only $5E81-$5F5E of the slack is PROVEN safe (the shipped
; fontpatch lives there and runs); $5F60+ is engine BSS. So all our code/data stays in
; $5E81-$5F5E. We drop the ASCII->SJIS table (set a fixed fullwidth code instead - the
; render hook overrides the glyph bitmap, and the cell/advance is the same for any
; fullwidth char) to make room for the render hook in the safe region.

.MEMORYMAP
  DEFAULTSLOT 0
  SLOT 0 START $4000 SIZE $2000
.ENDME

.ROMBANKMAP
  BANKSTOTAL 1
  BANKSIZE $2000
  BANKS 1
.ENDRO

.BACKGROUND "incbin/bank6d.bin"

.include "src/include/alshark.inc"

.BANK 0 SLOT 0

; ---- hook: route the byte->SJIS conversion through our ASCII handler ----
.ORG conv_entry - $4000          ; $57D0
  jmp ascii_conv

; ---- ASCII handler: flag the glyph as ours + stash its index, in bank 0x6D slack ----
.ORG slack_5E81 - $4000          ; $5E81
ascii_conv:
  lda (scriptPtr)                ; the script byte
  cmp #$20
  bcc conv_orig                  ; control byte
  cmp #$7F
  bcs conv_orig                  ; kana / 2-byte lead
  sec
  sbc #$20                       ; A = glyph index (char - 0x20)
  sta glyphIdx
  lda #$01
  sta glyphFlag                  ; this glyph is ours
  lda #$60                       ; fullwidth 'A' (SJIS 0x8260) so cell/advance works;
  sta fontCodeLo                 ; the render hook overrides the actual bitmap
  lda #$82
  sta fontCodeHi
  jmp conv_advance               ; advance cursor + return
conv_orig:
  stz glyphFlag                  ; not ours -> BIOS draws it
  jmp conv_origPath              ; original hiragana / 2-byte path

; ---- glyph draw override at $500F: ASCII -> our BM Mini glyph (bank 0x7F), else BIOS ----
.ORG drawHook - $4000            ; $500F (was: JSR $E060)
  jsr render_hook

.ORG $5EB0 - $4000               ; in the proven-safe slack
render_hook:
  lda glyphFlag
  bne rh_ours
  jmp $E060                      ; not ours -> BIOS draws the glyph (Japanese)
rh_ours:
  stz glyphFlag                  ; transient: only the char ascii_conv just flagged is ours
                                 ; (menu / map-name use this hook but not ascii_conv)
  tma #$40
  pha                            ; save MPR6
  lda fontCodeLo
  pha                            ; save $F8
  lda fontCodeHi
  pha                            ; save $F9
  lda #fontBank
  tam #$40                       ; page the font bank (0x7F) into MPR6
  lda glyphIdx                   ; pointer $F8/$F9 = fontBase + idx*glyphStride (16)
  stz fontCodeHi
  asl a
  rol fontCodeHi
  asl a
  rol fontCodeHi
  asl a
  rol fontCodeHi
  asl a
  rol fontCodeHi                 ; A:$F9 = idx*16
  clc
  adc #<fontBase
  sta fontCodeLo
  lda fontCodeHi
  adc #>fontBase
  sta fontCodeHi                 ; $F8/$F9 -> glyph rows in the font bank
  ldx #$00                       ; dest offset in glyphBuf
  ldy #$00                       ; src row 0..glyphRows-1
rh_loop:
  lda (fontCodeLo),y
  sta glyphBuf,x                 ; byte0 = pixels 0-7
  inx
  stz glyphBuf,x                 ; byte1 = 0
  inx
  iny
  cpy #glyphRows                 ; copy all 12 rows (fills the 24-byte $4EDA)
  bne rh_loop
  ; --- VWF: make this glyph's advance its real width instead of the fixed cell ---
  ; the engine adds boxAdv to penX at 6A:$8115 after we return; pre-bias by (width-boxAdv).
  ldx glyphIdx
  lda fontWidths,x               ; advance width (font bank 0x7F, still paged in)
  sta menuWidth                  ; stash for the menu name-loop advance ($40AE); only that
                                 ; (menu-only) site reads it, so harmless to dialogue/cutscene
  clc
  adc penX
  sec
  sbc #boxAdv
  sta penX                       ; penX += width - boxAdv  (engine's +boxAdv nets to width)
  pla
  sta fontCodeHi                 ; restore $F9
  pla
  sta fontCodeLo                 ; restore $F8
  pla
  tam #$40                       ; restore MPR6
  rts

; ---- name converter: hook the converter ENTRY ($587E) so ASCII names render in our font in
; BOTH the #-engine cutscenes (0x1E slot $401E -> $587E) and the menus (status/equip/item call
; $587E directly). Original $587E sent ASCII (0x21-0x7E) to its 2-byte default -> garbage; we
; intercept ASCII, everything else falls into the original body at $5882 (past our 3-byte JMP).
.ORG nameConvOrig - $4000        ; $587E (was: LDA ($16) / CMP #$20)
  jmp name_conv

; ---- menu name VWF: replace the name-loop's fixed +12 X-advance with += menuWidth (real glyph
; width) so English menu names advance proportionally and fit the slot (no BG overflow). Menu-only
; (the name-read routine at $4057); cutscene names draw via 6A:$7FE4.
.ORG nameLoopAdv - $4000         ; $40AE: redirect to a slack trampoline (3 bytes, NO overrun).
  jmp nameAdvTramp               ; an inline re-emit here is +3 bytes vs the original and overruns
                                 ; the loop's exit at $40BC (turning it into JMP $4080 = infinite loop)

.ORG nameLoopExit - $4000        ; $40BC: restore the exit the first cut's inline re-emit clobbered
  pla                            ; (orig PLA / TAM #$08 / RTS) - balances the PHA/TMA at routine entry
  tam #$08
  rts

.ORG $5F18 - $4000               ; proven-safe slack, after render_hook (now ends ~$5F17)
name_conv:
  lda (scriptPtr)                ; the name byte ($16 = name-table pointer)
  cmp #$20
  bcc nc_orig                    ; control byte -> original
  cmp #$7F
  bcs nc_orig                    ; kana / 2-byte -> original
  sec
  sbc #$20                       ; A = glyph index (char - 0x20)
  sta glyphIdx
  lda #$01
  sta glyphFlag                  ; ours -> render_hook draws it
  lda #$60
  sta fontCodeLo                 ; fullwidth cell (0x8260); render hook overrides the bitmap
  lda #$82
  sta fontCodeHi
  jmp nameAdvRet                 ; $58F4: INC $16 (16-bit) + RTS
nc_orig:
  cmp #$20                       ; replay the CMP #$20 our JMP clobbered at $5880
  jmp nameConvBody               ; $5882: rest of the original converter (BNE $588E ...)

; ---- menu name advance trampoline (slack): $00 += menuWidth (VWF) then loop. Redirected from
; $40AE; absolute menuWidth ($5F42, safe). Trampolining (vs an inline re-emit) avoids the +3-byte
; overrun that clobbered the loop's exit and hung the menu.
.ORG nameAdvTramp - $4000        ; $5F43
  clc
  lda $00
  adc menuWidth                  ; $00 += this glyph's real width instead of the fixed +12
  sta $00
  cla
  adc $01
  sta $01
  jmp nameLoopTop                ; $4080
