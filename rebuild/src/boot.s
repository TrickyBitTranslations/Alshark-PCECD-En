; Alshark boot/WRAM image - disc cooked 0x0000-0x2000, loaded to WRAM $2000-$3FFF.
; NOTE: the low part of this image (the IPL boot program, ~disc 0x0-0x800, incl the $2Bxx
; vsync handler at disc 0x326) is CHECKSUMMED by the System Card - patching it = "load
; error". The $34xx loader region (disc 0x14xx) is loaded later by the game, NOT checksummed,
; so it is safe to patch (our earlier $34C2 hook booted fine).
;
; Placement: card RAM has no permanently-free bank (every bank reloads on transitions).
; Bank 0x7F's tail ($CFA0+) is a scene-load staging buffer: wiped during a transition's
; load, free for the rest of the scene. We re-copy our VWF font into it after a transition.
; We do it by hooking the resident loader's CD read ($34E3 = JSR $E009), which fires on the
; engine/area/map loads that wipe the buffer. The font read runs SEQUENTIALLY right after
; the loader's own read (CD idle -> no deadlock, no IRQ), gated by a marker so it only
; re-copies when the buffer was actually wiped. Font baked at cooked 0xa1a000 (recno $1434).

.MEMORYMAP
  DEFAULTSLOT 0
  SLOT 0 START $2000 SIZE $2000
.ENDME

.ROMBANKMAP
  BANKSTOTAL 1
  BANKSIZE $2000
  BANKS 1
.ENDRO

.BACKGROUND "incbin/boot.bin"

.BANK 0 SLOT 0

; ---- hook the loader's CD read ($34E3 = disc 0x14E3): JSR $E009 -> JSR my_read ----
.ORG $14E3                        ; disc 0x14E3 == WRAM $34E3
  jsr my_read

; ---- my_read + font_load (disc 0x1BC6 == WRAM $3BC6, free loader slack) ----
.ORG $1BC6                        ; WRAM $3BC6
my_read:
  jsr $E009                       ; the loader's own read (CD now idle afterwards)
  pha                             ; save its result code
  ldx #$07                        ; save the 8-byte descriptor $F8-$FF (loader may use it)
ms_sv:
  lda $F8,x
  sta.w desc_save,x
  dex
  bpl ms_sv
  tma #$40
  pha
  lda #$7F
  tam #$40                        ; page font bank 0x7F into MPR6
  lda $D600                       ; marker (after the glyph + width tables)
  cmp #$A5
  beq mr_have                     ; font still present
  jsr font_load                   ; buffer was wiped -> re-copy the font in
mr_have:
  pla
  tam #$40                        ; restore MPR6
  ldx #$07                        ; restore the descriptor
ms_rs:
  lda.w desc_save,x
  sta $F8,x
  dex
  bpl ms_rs
  pla                             ; restore the loader's result code
  rts                             ; -> $34E6

; copies the font into bank 0x7F $CFA0 (MPR6 already 0x7F, CD idle) and sets the marker.
font_load:
  lda #$01
  sta $F8                         ; sector count = 1
  stz $F9
  lda #$A0
  sta $FA
  lda #$CF
  sta $FB                         ; dest = $CFA0
  stz $FC                         ; recno hi (track-relative; no seek)
  lda #$14
  sta $FD
  lda #$34
  sta $FE                         ; recno = $001434 (cooked 0xa1a000 / 2048)
  lda #$01
  sta $FF                         ; flag = read
  jsr $34B2                       ; copy descriptor $20F8 -> BIOS param block $34AA
  jsr $E009                       ; CD_READ -> DMA font into bank 0x7F $CFA0
  lda #$A5
  sta $D600                       ; set marker
  rts

desc_save:
  .db $00, $00, $00, $00, $00, $00, $00, $00
