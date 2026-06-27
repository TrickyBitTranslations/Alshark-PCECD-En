; Alshark anime-cutscene subtitle engine - patched into the bank 0x68 cutscene PLAYER (cooked
; 0x2BE1000 = recno $57C2, loaded to $4000-$5FFF @ MPR2 for EVERY anime cutscene). The $467A VDC-IRQ
; handler signature appears exactly once in track02.iso, so this single shared player copy is a
; universal per-frame hook with no runtime install. See noredist/docs/findings/cutscene-player.md.
;
; DISPLAY: a raster split shows the band at the bottom. The band lives in an off-screen BAT row, placed
; just above the visible window each frame (tracks the scroll); the split re-points BYR at it for the
; bottom ~16 scanlines. Image cells the band covers are saved and restored when it moves. Hooks (over the
; player's dormant RCR split, handler $46ED gated by $2F=0, RCR=0):
;   - $4689 (vblank path) -> vblank_hook: build the band, save/restore the image under it, arm reg6.
;   - $46ED (RCR dispatch) -> my_rcr: at the split line, point BYR at the band region (BG only).
;
; The vblank path starts at $4689 with INC $2241 (the frame counter the main loop polls). pl_inc ($4318)
; bumps play_counter once per voice clip so the subtitle is PLAY-timed. The whole blob = a play-ordered
; table @ $A000 (per line: n_tiles + a PRE-RENDERED proportional 1bpp pixel strip, terminator n_tiles=0)
; STREAMS from card bank 0x7D - do_blob_load CD_READs it once per cutscene; vh_fetch MPR-swaps 0x7D in,
; copies the current line's strip to strip_buf $4D00; vblank_hook expands it into 4bpp VRAM tiles. build.py
; emits cutscene_subs_blob.bin (VWF strips, mixed case; spliced on disc at 0x9DE000 = recno $13BC). The band
; is drawn non-destructively: the image cells under it are saved and restored when it moves.
;
; Slack: save_under/restore_under/probe $4C60 ; strip_buf $4D00 ; vblank_hook $4A60.. ; vh_fetch $4E20 ;
;        my_after_read+do_blob_load $4E7E/$4ED4 ; scratch $4EA0-$4EAC ; rcr_next $4EAD ; my_rcr $4EB0 ; pl_inc $4FF0.
; Scratch: $4EA0 n_tiles, $4EA1 copy-count, $4EA5 play_counter, $4EA7 probe-temp, $4EA8 width64, $4EA9/$4EAA split BYR
;          (band region pixel-row, read by my_rcr at the raster split), $4EAB/$4EAC under_row ($FFFF=none),
;          $4EAD/$4EAE rcr_next.

.MEMORYMAP
  DEFAULTSLOT 0
  SLOT 0 START $4000 SIZE $2000
.ENDME

.ROMBANKMAP
  BANKSTOTAL 1
  BANKSIZE $2000
  BANKS 1
.ENDRO

.BACKGROUND "incbin/bank68.bin"

.BANK 0 SLOT 0

; --- patch the IRQ handler's vblank-path entry ($4689 = INC $2241, EE 41 22) ---
.ORG $4689 - $4000
  jmp vblank_hook

; --- patch the RCR dispatch target. The IRQ does BIT #$04 / BNE $46ED on a raster interrupt; $46ED is
;     the player's native split handler, dormant ($2F=0, RCR=0, never fires). We redirect it to our own
;     handler and own RCR outright. (Overwrites $46ED-$46EF = LDA $2F / BEQ ..; the rest is orphaned.) ---
.ORG $46ED - $4000
  jmp my_rcr

; --- patch the voice player's per-clip advance ($4318 = INC $2B) so the subtitle is PLAY-timed, not
;     load-timed. pl_inc bumps play_counter, replays the 16-bit INC $2B/$2C, returns to the RTS $431E. ---
.ORG $4318 - $4000
  jmp pl_inc

; --- $42E7 hook (the player's post-read step, JSR $49FD): replay it, then load our blob once per cutscene.
;     Runs in the main loop, after the player's first scene-data CD_READ, before any voice/music. ---
.ORG $42E7 - $4000
  jsr my_after_read

; --- non-destructive band helpers (in the space freed by moving the font into the 0x7D blob). save_under
;     copies the 32 image BAT cells under the band into the 0x7D under-buffer ($BF00); restore_under writes
;     them back. Both run with MPR5=$7D mapped and the under pointer in $00/$01. ---
.ORG $4C60 - $4000
save_under:                      ; VRAM[band_word $4EA2/3] (32 cells) -> under-buffer ($00)=$BF00
  st0 #$01                       ; MARR = band_word (read pointer)
  lda.w $4EA2
  sta.w $0002
  lda.w $4EA3
  sta.w $0003
  st0 #$02                       ; VRR (auto-increment read)
  ldy #$00
su_lp:
  lda.w $0002
  sta ($00),y
  iny
  lda.w $0003
  sta ($00),y
  iny
  cpy #$40
  bne su_lp
  rts
restore_under:                   ; under-buffer ($00)=$BF00 -> VRAM[under_row $4EAB/C] (32 cells)
  st0 #$00                       ; MAWR = under_row (write pointer)
  lda.w $4EAB
  sta.w $0002
  lda.w $4EAC
  sta.w $0003
  st0 #$02                       ; VWR (auto-increment write)
  ldy #$00
ru_lp:
  lda ($00),y
  sta.w $0002
  iny
  lda ($00),y
  sta.w $0003
  iny
  cpy #$40
  bne ru_lp
  rts

; probe: read the BAT cell at (word + (32-n_tiles)/2), the first centred text cell, and set carry iff it
; is one of our text tiles ($07C5-$07E2; the image tops out at $07C4, the face feature is $07E3+).
; In: A=word_lo, X=word_hi. Out: C. Uses $4EA7 as scratch; does not touch $00/$01.
probe:
  pha                            ; word_lo
  txa
  pha                            ; word_hi
  lda #$20
  sec
  sbc.w $4EA0                    ; 32 - n_chars
  lsr a                          ; (32 - n)/2 = centre column offset
  sta.w $4EA7
  st0 #$01                       ; select MARR (read pointer)
  pla                            ; word_hi
  tax
  pla                            ; word_lo
  clc
  adc.w $4EA7                    ; + centre offset
  sta.w $0002                    ; MARR lo
  txa
  adc #$00
  sta.w $0003                    ; MARR hi
  st0 #$02                       ; VRR
  lda.w $0002                    ; cell lo
  ldx.w $0003                    ; cell hi
  cpx #$07
  bne probe_no                   ; tile hi != $07 -> not our text
  cmp #$C5
  bcc probe_no                   ; tile lo < $C5 -> image tile ($0760-$07C4)
  cmp #$E3
  bcs probe_no                   ; tile lo >= $E3 -> face feature ($07E3+)
  sec
  rts
probe_no:
  clc
  rts

; strip_buf @ $4D00 ($4D00-$4DEF, up to 30 tiles * 8 B): vh_fetch copies the CURRENT line's pre-rendered 1bpp
; proportional strip here each frame from the streamed blob in bank 0x7D; vblank_hook expands it to VRAM. The
; full play-ordered table streams from 0x7D (no resident cap). (strip_buf sits in the freed cs_font region.)

.ORG $4E20 - $4000               ; subtitle stream helpers (in the freed cs_table region, < scratch @ $4EA0)
; vh_fetch: find the current line (play_counter-1) in the streamed blob and copy its pre-rendered 1bpp strip
; into strip_buf @ $4D00. The blob (card bank 0x7D, mapped at $A000 via a borrowed MPR5) is a play-ordered
; table: per entry n_tiles(1) + strip(n_tiles*8). Walk it with a 16-bit pointer (advance 1 + n_tiles*8 per
; skipped entry), then copy the target strip. Sets $4EA0 = n_tiles (0 if play_counter is past the last line).
vh_fetch:
  lda $00
  pha
  lda $01
  pha
  tma #$20                       ; save MPR5
  pha
  lda #$7D
  tam #$20                       ; MPR5 = bank 0x7D -> blob/table at $A000
  stz $00                        ; ptr = $A000
  lda #$A0
  sta $01
  ldx.w $4EA5                    ; X = play_counter (1-based)
  dex                            ; entries to skip = play_counter - 1
vhf_skip:
  beq vhf_at
  lda ($00)                      ; n_tiles of this entry
  beq vhf_none                   ; terminator before target => no line
  asl a
  asl a
  asl a                          ; n_tiles * 8 (<= 240, no overflow)
  clc
  adc #$01                       ; + the n_tiles byte => 1 + n_tiles*8
  clc
  adc $00
  sta $00                        ; ptr += entry size (16-bit)
  bcc vhf_s1
  inc $01
vhf_s1:
  dex
  bra vhf_skip
vhf_at:
  lda ($00)                      ; n_tiles of the target entry
  beq vhf_none
  sta.w $4EA0                    ; n_tiles -> scratch
  asl a
  asl a
  asl a                          ; count = n_tiles * 8
  sta.w $4EA1
  inc $00                        ; advance ptr past the n_tiles byte to the strip start
  bne vhf_a1
  inc $01
vhf_a1:
  cly
vhf_cp:
  lda ($00),y                    ; strip byte y from 0x7D
  sta.w $4D00,y                  ; -> strip_buf (bank 0x68)
  iny
  cpy.w $4EA1
  bne vhf_cp
  bra vhf_done
vhf_none:
  stz.w $4EA0                    ; no line
vhf_done:
  pla
  tam #$20                       ; restore MPR5
  pla
  sta $01
  pla
  sta $00
  rts

loaded_flag:                     ; baked 0 (reset by the per-cutscene bank reload); set after the blob loads
.db $00

; my_after_read (hooked from $42E7): replay the displaced post-read step ($49FD), then load the blob the
; first time this cutscene (gated by loaded_flag).
my_after_read:
  jsr $49FD                      ; displaced: the player's own post-read step
  lda.w loaded_flag
  bne mar_done
  jsr do_blob_load
  lda #$01
  sta.w loaded_flag
mar_done:
  rts

.ORG $4ED4 - $4000               ; do_blob_load in the free gap after my_rcr (ends $4ED2), before the init
                                 ; data @ $4EFE - keeps the tail after vblank_hook free for its growth.
; do_blob_load: CD_READ the subtitle blob (recno $0013BC = cooked 0x9DE000) into card bank 0x7D. Descriptor
; @ $F8-$FF: count(2 LE) / dest(2 LE, $FA=dest bank) / recno(3 BE: $FC=hi,$FD=mid,$FE=lo) / mode($FF).
do_blob_load:
  lda #$04                       ; count = 4 sectors (8 KB = all of bank 0x7D, verified free in-cutscene)
  sta $F8
  stz $F9
  lda #$7D                       ; dest = card bank 0x7D ($2A000)
  sta $FA
  stz $FB
  stz $FC                        ; recno hi
  lda #$13                       ; recno mid
  sta $FD
  lda #$BC                       ; recno lo  => recno $0013BC
  sta $FE
  lda #$06                       ; mode 6 (load to card bank, same as the scene-data CD_READs)
  sta $FF
mil_read:
  jsr $E009                      ; CD_READ; A=0 on success, nonzero while busy/on error -> retry
  cmp #$00
  bne mil_read
  rts

; --- per-frame band builder (runs in the cutscene's VDC IRQ vblank path, all in bank 0x68) ---
.ORG $4A60 - $4000
vblank_hook:
  ; current line = play_counter ($4EA5) - 1 (play_counter bumped by pl_inc). 0 => no clip has started.
  lda.w $4EA5
  bne vh_have
  jmp vh_disarm                  ; no clip yet => no band, nothing to restore
vh_have:
  jsr vh_fetch                   ; current line's pre-rendered strip -> strip_buf $4D00; $4EA0 = n_tiles
  lda.w $4EA0
  bne vh_match
  jmp vh_noline                  ; terminator: restore the last band's image, then disarm
vh_match:
  ; --- band geometry: width64 ($4EA8), band_word ($4EA2/3), split BYR ($4EA9/A), one row above the visible
  ;     window (tracks the scroll). ---
  st0 #$01                       ; MARR = $0400 (width probe: image hi != 0 => 64-wide, blank => 32-wide)
  st1 #$00
  st2 #$04
  st0 #$02                       ; VRR
  lda.w $0002
  lda.w $0003
  beq vh_w32
  lda #$01
  sta.w $4EA8                    ; width64 = 1
  bra vh_byr
vh_w32:
  stz.w $4EA8                    ; width64 = 0 (32-wide)
vh_byr:
  lda $2039                      ; split BYR = (BYR & ~7) - 19 (text sits ~3px below the split line)
  and #$F8
  sec
  sbc #$13
  sta.w $4EA9
  lda $203A
  sbc #$00
  sta.w $4EAA
  lda $2039                      ; band_word = (BYR & ~7) << 2 (32w) or << 3 (64w), minus 64/128, & $07FF
  and #$F8
  sta.w $4EA2
  lda $203A
  sta.w $4EA3
  asl.w $4EA2
  rol.w $4EA3
  asl.w $4EA2
  rol.w $4EA3                    ; << 2
  lda.w $4EA8
  beq vh_bw32
  asl.w $4EA2
  rol.w $4EA3                    ; << 3 (64-wide)
  sec
  lda.w $4EA2
  sbc #$80                       ; - 128
  sta.w $4EA2
  lda.w $4EA3
  sbc #$00
  sta.w $4EA3
  bra vh_bwmask
vh_bw32:
  sec
  lda.w $4EA2
  sbc #$40                       ; - 64
  sta.w $4EA2
  lda.w $4EA3
  sbc #$00
  sta.w $4EA3
vh_bwmask:
  lda.w $4EA3
  and #$07
  sta.w $4EA3
  ; --- MPR5 = $7D window: glyph-gen (font @ $A000 in 0x7D) + non-destructive band save/restore ($BF00) ---
  lda $00
  pha
  lda $01
  pha
  tma #$20                       ; save MPR5
  pha
  lda #$7D
  tam #$20                       ; MPR5 = bank 0x7D
  ; regenerate the glyph tiles EVERY frame (scene images clobber our tile region): expand the pre-rendered
  ; 1bpp proportional strip (strip_buf $4D00, n_tiles*8 bytes) into 4bpp VRAM tiles $7C5+ (color 15, all 4
  ; planes = the strip row). One tile = 8 rows; $7C5-$7E2 = 30 tiles free. (strip_buf is bank 0x68, so this
  ; needs no 0x7D map - it just rides in the window.)
  st0 #$00                       ; MAWR = $7C50 (tile $7C5)
  st1 #$50
  st2 #$7C
  st0 #$02
  stz $00                        ; strip_buf ptr = $4D00
  lda #$4D
  sta $01
  ldx.w $4EA0                    ; X = n_tiles down-counter
vh_etile:
  cly
vh_ep01:
  lda ($00),y                    ; strip row byte -> planes 0,1
  sta.w $0002
  sta.w $0003
  iny
  cpy #$08
  bne vh_ep01
  cly
vh_ep23:
  lda ($00),y                    ; same byte -> planes 2,3
  sta.w $0002
  sta.w $0003
  iny
  cpy #$08
  bne vh_ep23
  lda $00                        ; strip_buf ptr += 8 (next tile)
  clc
  adc #$08
  sta $00
  bcc vh_etadv
  inc $01
vh_etadv:
  dex
  bne vh_etile
  ; --- non-destructive band. `under` (0x7D $BF00) holds the image of under_row ($4EAB/C; $FFFF=none).
  ;     Decisions use probe (does our band tile sit at a row) rather than tracking scene changes. ---
  stz $00
  lda #$BF
  sta $01                        ; under-buffer ptr = $BF00
  ; (A) band moved off under_row: restore that row if our band is still there
  lda.w $4EA2
  cmp.w $4EAB
  bne vh_u_movd
  lda.w $4EA3
  cmp.w $4EAC
  beq vh_u_savechk               ; same row -> no restore
vh_u_movd:
  lda.w $4EAB
  cmp #$FF
  bne vh_u_oldchk
  lda.w $4EAC
  cmp #$FF
  beq vh_u_savechk               ; under_row invalid -> nothing to restore
vh_u_oldchk:
  lda.w $4EAB
  ldx.w $4EAC
  jsr probe                      ; our band still at under_row?
  bcc vh_u_savechk               ; no -> skip restore
  jsr restore_under
vh_u_savechk:
  ; (B) save band_word's image into `under`, unless our band is already drawn there
  lda.w $4EA2
  ldx.w $4EA3
  jsr probe                      ; our band already at band_word?
  bcs vh_u_setrow                ; yes -> `under` is valid, skip the save
  jsr save_under
vh_u_setrow:
  tii $4EA2, $4EAB, 2            ; under_row = band_word
vh_udone:
  pla
  tam #$20                       ; restore MPR5
  pla
  sta $01
  pla
  sta $00
  ; --- draw the band over band_word: the dark bar ($00FF), then the centered text tiles ($7C5+col). The
  ;     image it covers is now safe in `under`. ---
  st0 #$00
  lda.w $4EA2
  sta.w $0002
  lda.w $4EA3
  sta.w $0003
  st0 #$02
  ldx #$20
vh_clrl:
  st1 #$FF
  st2 #$00
  dex
  bne vh_clrl
  st0 #$00                       ; centered: MAWR = band_word + (32 - n_chars)/2
  lda #$20
  sec
  sbc.w $4EA0
  lsr a
  clc
  adc.w $4EA2
  sta.w $0002
  lda.w $4EA3
  adc #$00
  sta.w $0003
  st0 #$02
  cly
vh_rl:
  tya
  clc
  adc #$C5                       ; tile $7C5 + col
  sta.w $0002
  lda #$07
  sta.w $0003
  iny
  cpy.w $4EA0
  bne vh_rl
  stz.w $4EAF                    ; reset my_rcr's fire-flag; arm the split at rcr_next ($4EAD/E)
  st0 #$06
  lda.w $4EAD
  sta.w $0002
  lda.w $4EAE
  sta.w $0003
  bra vh_done
vh_noline:
  ; play_counter is past the last line: restore the last band's image if our band is still at under_row
  ; (probe), then invalidate.
  lda.w $4EAB
  cmp #$FF
  bne vh_nl_chk
  lda.w $4EAC
  cmp #$FF
  beq vh_disarm                  ; under_row invalid -> nothing
vh_nl_chk:
  lda.w $4EAB
  ldx.w $4EAC
  jsr probe                      ; our band still at under_row?
  bcc vh_disarm                  ; no -> nothing to clean up
  lda $00
  pha
  lda $01
  pha
  tma #$20
  pha
  lda #$7D
  tam #$20
  stz $00
  lda #$BF
  sta $01
  jsr restore_under
  lda #$FF
  sta.w $4EAB
  sta.w $4EAC                    ; invalidate (restore only once)
  pla
  tam #$20
  pla
  sta $01
  pla
  sta $00
vh_disarm:
  st0 #$06                       ; RCR = 0 => no split. clear BOTH bytes (high may be $01 from a 224 arm).
  stz.w $0002
  stz.w $0003
vh_done:
  inc $2241                      ; replay the displaced INC $2241
  jmp $468C                      ; continue the IRQ handler's vblank path

; --- my_rcr: the RCR split handler ($46ED redirect). At the split line set BXR=0, BYR=band region,
;     CR=$88 (BG + vblank on, sprites + RCR off), then exit via the player's IRQ teardown $46E3. ---
.ORG $4EAB - $4000
.db $FF, $FF                     ; under_row init = $FFFF (reset per cutscene bank reload)
.db $D0, $00                     ; rcr_next init = $00D0 (160-line bottom)
.ORG $4EB0 - $4000
my_rcr:
  st0 #$07                       ; BXR = 0
  stz.w $0002
  stz.w $0003
  st0 #$08                       ; BYR = split BYR (band region rows)
  lda.w $4EA9
  sta.w $0002
  lda.w $4EAA
  sta.w $0003
  st0 #$05                       ; CR = $88 (BG + vblank on; sprites + RCR off)
  lda #$88
  sta.w $0002
  stz.w $0003
  jmp $46E3

; --- play-counter hook ($4318 -> here). Bumps play_counter, replays the 16-bit INC $2B/$2C, RTS $431E.
;     FIXED $4FF0 (past cs_table + scratch) - inline it overran the scratch and self-corrupted. ---
.ORG $4FF0 - $4000
pl_inc:
  inc.w $4EA5                    ; play_counter++ (once per voice clip that starts playing)
  inc $2B                        ; the displaced INC $2B / BNE / INC $2C (16-bit pointer advance)
  bne pl_skip
  inc $2C
pl_skip:
  jmp $431E
