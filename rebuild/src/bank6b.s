; Alshark location-name banner - bank 0x6B (field town-entry banner draw at $AB0B).
; The banner already renders in our VWF font, but with a FIXED 12px cell: the per-char advance
; ($AB91: pen += 12) and the centering ($AB34: ((12 - charcount)/2)*12). We make it proportional
; for our RELOCATED maps, and leave every other map (overworld, etc.) running the original code.
;
; Source: location_patch (build.py) relocates each translated map's English name into free space
; in the map block (the page loaded to bank 0x76 at $C000) as [start_x][name\0], and repoints the
; map's name pointer at $C02E to it. start_x = precomputed centered left edge (8 + (144-width)/2).
; Un-relocated maps keep the default pointer $C032, which we use as the discriminator.
;
; Both hooks live in the proven-safe slack at $BF7B (133 bytes).

.MEMORYMAP
  DEFAULTSLOT 0
  SLOT 0 START $A000 SIZE $2000
.ENDME

.ROMBANKMAP
  BANKSTOTAL 1
  BANKSIZE $2000
  BANKS 1
.ENDRO

.BACKGROUND "incbin/bank6b.bin"

.include "src/include/alshark.inc"

.BANK 0 SLOT 0

; ---- hook the TII at $AB20 (7 bytes) so the whole original routine stays intact for non-our
;      maps. We replicate the TII, then branch: ours -> English/proportional; else -> original. ----
.ORG $AB20 - $A000               ; was: TII $C02E,$2016,#$0002
  jmp banner_hook

; ---- per-char advance ($AB91): ours -> += real glyph width (menuWidth); else -> original +12 ----
.ORG $AB90 - $A000               ; was: CLC / LDA #$0C / ADC $00 ...
  jmp banner_adv

.ORG $BF7B - $A000               ; bank-tail slack (verified: no code reads/writes it)
banner_hook:
  lda $C02E                      ; replicate the TII the original did ($C02E -> $2016)
  sta $2016
  lda $C02F
  sta $2017
  lda $C02E                      ; discriminator: un-relocated maps keep the default $C032
  cmp #$32
  bne bh_reloc
  lda $C02F
  cmp #$C0
  bne bh_reloc
  jmp $AB27                      ; not ours -> run the original banner code, fully intact
bh_reloc:
  lda $C02E                      ; our relocated pointer -> [start_x][name\0]
  sta scriptPtr
  lda $C02F
  sta $17
  lda (scriptPtr)                ; start_x = precomputed centered left edge
  sta $00
  stz $01
  inc scriptPtr                  ; step past start_x -> the name string
  bne bh_nohi
  inc $17
bh_nohi:
  lda scriptPtr                  ; keep $2016 (the banner stashes the pointer there) in sync
  sta $2016
  lda $17
  sta $2017
  lda #$08                       ; replay the setup the skipped $AB50-$AB58 did
  sta $04
  stz $05
  lda #$0F
  sta $2745
  jmp $AB62                      ; into the existing per-char draw loop

banner_adv:
  lda $C02E                      ; same discriminator
  cmp #$32
  bne ba_reloc
  lda $C02F
  cmp #$C0
  bne ba_reloc
  clc                            ; not ours -> original fixed +12 advance
  lda #$0C
  adc $00
  sta $00
  cla
  adc $01
  sta $01
  jmp $AB62
ba_reloc:
  tma #$04                       ; menuWidth ($5F42) is bank 0x6D; the draw dispatch restored
  pha                            ; MPR2 to the field bank, so page bank 0x6D ($2682) back in
  lda $2682
  tam #$04
  lda menuWidth                  ; real width of the glyph just drawn
  tax
  pla
  tam #$04                       ; restore the field's MPR2
  clc
  txa
  adc $00
  sta $00
  cla
  adc $01
  sta $01
  jmp $AB62
