; Alshark location-name banner - bank 0x6B (field town-entry banner draw at $AB0B).
; The banner already renders in our VWF font, but with a FIXED 12px cell: the per-char advance
; ($AB91: pen += 12) and the centering ($AB34: ((12 - charcount)/2)*12). We make it proportional
; for our RELOCATED maps, and leave every other map (overworld, etc.) running the original code.
;
; Source: location_patch (build.py) relocates each translated map's English name into free space
; in the map block (the page loaded to bank 0x76 at $C000) as [$01][start_x][name\0], and repoints
; the map's name pointer at $C02E to it. start_x = centered left edge (8 + (144-width)/2).
; Discriminator: deref $C02E and test the first byte for the $01 marker. A stock pointer's target
; starts with start_x ($08-$50) or an SJIS lead ($81+), never $01, so every un-relocated map
; (overworld included) falls through to the original code. (The old "$C02E == $C032" test mis-fired
; on maps whose stock name pointer wasn't $C032 - they took our path and sprayed glyphs on the map.)
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

; ---- formation party-name copy ($A26B): the per-member loop copies a FIXED 8 bytes of the name
;      from ($20) into the list template at ($78). Our English names are NUL-padded (short), so the
;      copy drags NUL bytes mid-template; the menu-label drawer ($5748) treats NUL as end-of-string
;      and stops after the first member (only Sion shows). JP names fill 8 bytes with a trailing
;      full-width space (no NUL), so JP is fine. Redirect to a copy that maps NUL -> space. ----
.ORG $A26B - $A000               ; was: LDX #$08 / CLY (head of the 8-byte copy loop)
  jmp $3CA0                       ; form_name_copy lives in boot.s WRAM loader slack ($3CA0); this
                                 ; bank's tail slack ($BF7B) is full, WRAM is reachable here (MPR1=F8)

; ---- formation "placed" mark ($A369): when a member is assigned to <New>, $A369 redraws their
;      <Current> name DIMMED (palette 7) at $A3AC, then the white <New> copy at $A3CB. That dim copy
;      is drawn by $3063 and lands OFFSET from the original name (which the template drew via the
;      $5748 menu drawer) - different drawer + proportional font - so you get a black-over-white
;      double image instead of a clean dim. Suppress the dim draw (NOP the JSR); the placed member
;      still appears in <New>, and <Current> stays clean. ----
.ORG $A3AC - $A000               ; was: JSR $3063 (dim placed-mark draw)
  nop
  nop
  nop

.ORG $BF7B - $A000               ; bank-tail slack (verified: no code reads/writes it)
banner_hook:
  lda $C02E                      ; name pointer -> scriptPtr ($16/$17 = $2016/$2017); this also
  sta scriptPtr                  ; replicates the TII the original did ($C02E -> $2016)
  lda $C02F
  sta $17
  lda (scriptPtr)                ; deref the pointer: first byte of the target data
  cmp #$01                       ; our marker? a stock pointer's first byte is start_x ($08-$50)
  bne bh_orig                    ; or an SJIS lead ($81+), never $01
  lda #$01
  sta.w banner_flag                ; ours -> banner_adv advances proportionally
  inc scriptPtr                  ; skip the marker -> start_x
  bne bh_m1
  inc $17
bh_m1:
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
bh_orig:
  stz.w banner_flag                ; not ours -> banner_adv uses the original +12 advance
  jmp $AB27                      ; run the original banner code, fully intact

banner_adv:
  lda.w banner_flag                ; set once by banner_hook: 1 = ours, 0 = stock
  beq ba_orig
  tma #$04                       ; ours -> proportional. menuWidth ($5F42) is bank 0x6D; the draw
  pha                            ; dispatch restored MPR2 to the field bank, so page 0x6D ($2682) back
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
ba_orig:
  clc                            ; stock -> original fixed +12 advance
  lda #$0C
  adc $00
  sta $00
  cla
  adc $01
  sta $01
  jmp $AB62

banner_flag: .db $00             ; 1 = current map is ours (proportional), 0 = stock (+12)
