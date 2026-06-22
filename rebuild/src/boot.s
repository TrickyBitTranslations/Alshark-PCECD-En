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
  jsr copy_hud_names              ; refresh the English battle-HUD name table in $690A (bank 0x78)
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

; ---- battle HUD party names: the draw reads its name table at $690A (bank 0x78), which is
; resident and combat-stable but loaded from disc 0x3f790a (shared with the field - can't patch
; on disc). So we overwrite the card copy here: this hook runs at every transition (when the font
; reloads). hud_idx holds 72 font-glyph indices (9 members x 8 tiles); we expand each to a
; (index, $70) tile-ref into $690A. Idempotent; $690A then stays English through combat. ----
copy_hud_names:
  tma #$08                        ; save MPR3
  pha
  lda #$78
  tam #$08                        ; page bank 0x78 into MPR3 ($6000-$7FFF)
  ldx #$47                        ; 72 indices, X = 71..0
chn_lp:
  txa
  asl a                          ; A = X*2 = dest offset into the 144-byte table
  tay
  lda.w hud_idx,x
  sta $690A,y                     ; tile-ref low byte = glyph index
  lda #$70
  iny
  sta $690A,y                     ; tile-ref high byte = palette $70
  dex
  bpl chn_lp
  pla
  tam #$08                        ; restore MPR3
  rts
hud_idx:
  .incbin "incbin/hud_en_idx.bin"
