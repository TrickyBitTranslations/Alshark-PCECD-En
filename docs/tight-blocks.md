# Cutscene blocks that struggle to fit the byte budget

Auto-tracked during the machine-translation pass. Each $C000 dialogue block has a hard in-RAM
text budget (block text-region bytes; see noredist/docs/findings/space-budget.md). English (1
byte/char) often runs longer than the Japanese it replaces, so the MT pass had to COMPRESS these
scenes to fit. The `cut` column = roughly how many characters the first natural-length pass had to
trim to fit. High-cut blocks are where the **human pass will want more room** - i.e. the prime
candidates for the relocation / move-scene-code-out-of-text-slot fix (so prose can be restored).

Regenerate with the snippet in this repo's history / the script that produced it. HEAD at write: see git log.

| block | budget | used | headroom | %used | MT had to cut (~chars) |
|-------|-------:|-----:|---------:|------:|-----------------------:|
| 0x7c1000 | 4682 | 4620 | 62 | 99% | 1489 **HEAVY** |
| 0x7b3000 | 4876 | 4795 | 81 | 98% | 984 **HEAVY** |
| 0x79d000 | 3204 | 3173 | 31 | 99% | 908 **HEAVY** |
| 0x7a5000 | 4096 | 3977 | 119 | 97% | 816 **HEAVY** |
| 0x78b000 | 4096 | 4005 | 91 | 98% | 793 **HEAVY** |
| 0x7bb000 | 4948 | 4744 | 204 | 96% | 762 **HEAVY** |
| 0x7b7000 | 3595 | 3490 | 105 | 97% | 727 **HEAVY** |
| 0x7ad000 | 4281 | 4214 | 67 | 98% | 697 **HEAVY** |
| 0x7b1000 | 4096 | 4022 | 74 | 98% | 624 **HEAVY** |
| 0x791000 | 4097 | 3965 | 132 | 97% | 555 tight |
| 0x79f000 | 2918 | 2805 | 113 | 96% | 466 tight |
| 0x7b9000 | 2687 | 2591 | 96 | 96% | 441 tight |
| 0x785000 | 6144 | 6042 | 102 | 98% | 400 tight |
| 0x7c3000 | 4098 | 3846 | 252 | 94% | 387 tight |
| 0x797000 | 2691 | 2608 | 83 | 97% | 339 tight |
| 0x7af000 | 2904 | 2783 | 121 | 96% | 319 tight |
| 0x7a9000 | 2597 | 2519 | 78 | 97% | 287 tight |
| 0x793000 | 2880 | 2852 | 28 | 99% | 267 tight |
| 0x795000 | 3484 | 3293 | 191 | 95% | 253 |
| 0x7a1000 | 4107 | 3348 | 759 | 82% | 121 |
| 0x787000 | 6144 | 5285 | 859 | 86% | - |
| 0x789000 | 6144 | 5255 | 889 | 86% | - |
| 0x78d000 | 2048 | 1039 | 1009 | 51% | - |
| 0x799000 | 6144 | 5040 | 1104 | 82% | - |
| 0x79b000 | 6145 | 5424 | 721 | 88% | - |
| 0x7a3000 | 6144 | 5346 | 798 | 87% | - |
| 0x7a7000 | 6145 | 5486 | 659 | 89% | - |
| 0x7ab000 | 4096 | 3041 | 1055 | 74% | - |
| 0x7b5000 | 6144 | 5024 | 1120 | 82% | - |
| 0x7bd000 | 4096 | 3916 | 180 | 96% | - |
| 0x7bf000 | 6152 | 5054 | 1098 | 82% | - |
| 0x7c5000 | 6144 | 5338 | 806 | 87% | - |

## Worst offenders (restore these first once relocation lands)
- **0x7c1000** (Lamyu Kose's origin-of-the-Martians exposition): budget 4682, had to cut ~1489 chars.
  The lore got heavily compressed; deserves full prose.
- **0x7b3000** (Prince Zaate scenes): ~984. **0x79d000** (Kidun briefing): ~908.
- **0x7a5000** (Shaina/reunion + Wuhlia bar): ~816. **0x78b000** (spaceport/Atraia naming): ~793.
- **0x7bb000** (Wultria NPCs): ~762. **0x7b7000** (Bartz/snow tank): ~727. **0x7ad000** (Yaku trial): ~697.

## Tightest budgets (small slots, little room even before English grows)
- 0x7b9000 (2687), 0x7a9000 (2597), 0x797000 (2691), 0x793000 (2880), 0x7af000 (2904), 0x79f000 (2918).
  Several of these are narration-heavy and were squeezed hard.

