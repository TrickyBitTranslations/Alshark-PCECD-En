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

; ---- new-game state-init fix: stop the init copying our loader-slack code onto the save state ----
; The init ($3B40) does TAI (zero $269D-$2F57, which covers the WHOLE template destination $2829-$2C8D)
; then TII $3B53,$2829,#$0465 (copy the new-game template back over it). Our code at $3BC6-$3CC4 lives in
; that template's zero region, so the copy paints it onto the fresh inventory ($28F9). But the TAI already
; zeroed everything, and the template before the real data ($3CC5+) is just a 2-byte header ($2829=$0131)
; plus zeros - so we replace the one TII with: copy ONLY the real data, then write the header back. Now
; $282B-$299A (inventory included) just keeps the TAI's zeros and our code is never copied. The extra
; instructions spill into the now-dead template head ($3B53+), which nothing reads. Works in boot AND
; new-game (pure WRAM, no bank). See noredist/docs/findings/inventory-corruption.md.
.ORG $1B4B                        ; disc 0x1B4B == WRAM $3B4B (the init's template-copy TII)
  tii $3CC5, $299B, 755           ; copy only the real init data $3CC5-$3FB7 -> $299B-$2C8D (skip $2829-$299A)
  lda #$31
  sta $2829                       ; restore header lo
  inc $282A                       ; $282A is TAI-zeroed -> $01, giving the stock header $0131
  rts

; ---- blit_hud_glyphs: stream the relocated battle-HUD name glyphs to free VRAM $7E00.
; The glyphs must NOT live in the $2000 font page ($C0-$EB there are the enemy/party SHADOW
; sprites - injecting painted our glyph over the shadow = the enemy "white box" bug). Instead
; hudnames.py emits a 32-tile plane0 blob (rebuild/incbin/hud_glyphs.bin) that rides the bank-0x7F
; font asset (loaded to $CFA0+0x680 = $D620). This runs from my_read while MPR6=0x7F: for each of
; 32 tiles it writes 16 VRAM words - plane0 row + $FF (plane1), rows 0-7 twice (planes 2&3 = 0&1) -
; matching the katakana glyph format. VRAM $7E0-$7FF is above the HUD font's used range and is never
; cleared by battle (verified). copy_hud_names points the name table at these tiles (high byte $75).
; See noredist/docs/findings/enemy-shadow-tile-corruption.md.
.ORG $1B60                        ; WRAM $3B60 (free run $3B5B-$3BC4, ahead of the loader slack)
blit_hud_glyphs:
  lda $16
  pha
  lda $17
  pha                             ; preserve the loader's $16/$17
  lda #$00
  sta $F7
  sta.w $0000                     ; select VDC reg 0 (MAWR)  (.W = absolute VDC port, not ZP $2000)
  stz.w $0002                     ; MAWR lo = $00
  lda #$7E
  sta.w $0003                     ; MAWR hi = $7E -> VRAM write addr = $7E00
  lda #$02
  sta $F7
  sta.w $0000                     ; select VDC reg 2 (VWR)
  lda #$20
  sta $16
  lda #$D6
  sta $17                         ; $16/$17 = $D620 (glyph blob in bank 0x7F)
  ldx #$20                        ; 32 tiles
bhg_tile:
  cly
bhg_lo:
  lda ($16),y
  sta.w $0002                     ; VWR lo = plane0 row
  lda #$FF
  sta.w $0003                     ; VWR hi = $FF -> write word, VDC auto-increments MAWR
  iny
  cpy #$08
  bne bhg_lo
  cly
bhg_hi:
  lda ($16),y
  sta.w $0002                     ; planes 2&3 = copy of planes 0&1
  lda #$FF
  sta.w $0003
  iny
  cpy #$08
  bne bhg_hi
  lda $16
  clc
  adc #$08
  sta $16                         ; advance to next tile's 8 plane0 bytes
  bcc bhg_next
  inc $17
bhg_next:
  dex
  bne bhg_tile
  pla
  sta $17
  pla
  sta $16                         ; restore $16/$17
  rts

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
  jsr blit_hud_glyphs             ; MPR6 still 0x7F: stream HUD glyphs from 0x7F -> VRAM $7E00
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
  sta $690A,y                     ; tile-ref low byte = glyph tile
  cmp #$6F                        ; the blank-space tile ($26F) keeps high $70; real glyphs use $75
  beq chn_sp
  lda #$75                        ; -> draw's +2 builds BAT $77xx = tile $7xx (relocated glyph VRAM)
  bra chn_hi
chn_sp:
  lda #$70                        ; -> draw's +2 builds BAT $72xx = tile $26F (stock blank)
chn_hi:
  iny
  sta $690A,y                     ; tile-ref high byte
  dex
  bpl chn_lp
  pla
  tam #$08                        ; restore MPR3
  rts
hud_idx:
  .incbin "incbin/hud_en_idx.bin"

; ---- NUL->space party-name copy for the Plan->Formation list. Bank 0x6B's per-member loop
; (6B:$A26B) copies a FIXED 8 bytes of the name into the list template at ($78); our English names
; are NUL-padded (short) so it drags NULs mid-template and the menu-label drawer ($5748) treats NUL
; as end-of-string -> only the 1st member shows. JP names fill 8 bytes with a trailing full-width
; space (no NUL), so JP is fine. Bank 0x6B's own tail slack is full (banner), so the routine lives
; here in the loader free-slack (WRAM, MPR1=F8, mapped during the copy; combat-stable like the font/
; HUD hooks above). bank6b.s jmps here; we map NUL->space and rejoin the original at $A276 (which
; writes the row 0x0D + advances to the next slot, reloading A/X/Y - no need to preserve them). ----
.ORG $1CA0                        ; WRAM $3CA0 (free space inside the 255-byte $3BC6 loader-slack run)
form_name_copy:
  ldx #$08
  cly
fnc_loop:
  lda ($20),y
  bne fnc_keep
  lda #$20                       ; NUL -> space
fnc_keep:
  sta ($78),y
  iny
  dex
  bne fnc_loop
  jmp $A276

; ---- anime-cutscene subtitle hook (UNIVERSAL, via a DISC PATCH of the shared player code) ----
; The cutscene player (bank 0x68: the $467A VDC-IRQ handler etc.) is a SINGLE copy on disc at recno
; $57C2 (cooked 0x2BE1000), loaded to $4000 for EVERY anime cutscene - so bank68.s patches it directly.
; No runtime hook-install (the $2202-wrap, $3ACC/$7F0A code hooks, and TIMER watchdog all failed:
; per-cutscene bundled code at non-fixed offsets, IRQ2 never fires, the System Card doesn't route the
; timer IRQ to $2204). bank68.s redirects the IRQ handler's vblank path ($4689 = the INC $2241
; frame-counter bump) to vblank_hook below; we do per-frame subtitle work, replay INC $2241, and
; continue at $468C - running in the cutscene's own VDC IRQ, every frame, for all anime cutscenes.
; See noredist/docs/findings/cutscene-player.md. The renderer (vblank_hook) and its glyph tiles now
; live in bank68.s (the player's own slack, mapped during cutscenes) - nothing for it is needed here.
