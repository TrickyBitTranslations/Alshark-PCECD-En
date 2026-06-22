# Cutscene blocks that struggle to fit the byte budget

Tracked during the machine-translation pass. Each $C000 dialogue block has a hard in-RAM text
budget (see noredist/docs/findings/space-budget.md). English (1 byte/char) usually runs longer than
the Japanese it replaces, so many scenes had to be COMPRESSED to fit. The `cut` column = roughly how
many characters the first natural-length pass had to trim. High-cut blocks are where the **human
pass will want more room** - the prime candidates for the relocation / move-code-out-of-text-slot
fix, so fuller prose can be restored.

All 46 blocks now translated and fitting. `headroom` is current free bytes.

| block | budget | used | headroom | %used | MT had to cut (~chars) |
|-------|-------:|-----:|---------:|------:|-----------------------:|
| 0x7c1000 | 4682 | 4620 | 62 | 99% | 1489 **HEAVY** |
| 0x7df000 | 4382 | 4304 | 78 | 98% | 1319 **HEAVY** |
| 0x7e1000 | 4673 | 4583 | 90 | 98% | 1208 **HEAVY** |
| 0x7db000 | 3729 | 3638 | 91 | 98% | 1132 **HEAVY** |
| 0x7dd000 | 4445 | 4351 | 94 | 98% | 1132 **HEAVY** |
| 0x7b3000 | 4876 | 4795 | 81 | 98% | 984 **HEAVY** |
| 0x79d000 | 3204 | 3173 | 31 | 99% | 908 **HEAVY** |
| 0x7a5000 | 4096 | 3977 | 119 | 97% | 816 **HEAVY** |
| 0x78b000 | 4096 | 4005 | 91 | 98% | 793 **HEAVY** |
| 0x7bb000 | 4948 | 4744 | 204 | 96% | 762 **HEAVY** |
| 0x7e3000 | 4250 | 4103 | 147 | 97% | 749 **HEAVY** |
| 0x7b7000 | 3595 | 3490 | 105 | 97% | 727 **HEAVY** |
| 0x7ad000 | 4281 | 4214 | 67 | 98% | 697 **HEAVY** |
| 0x7e9000 | 3211 | 3104 | 107 | 97% | 655 **HEAVY** |
| 0x7b1000 | 4096 | 4022 | 74 | 98% | 624 **HEAVY** |
| 0x7c9000 | 3234 | 3123 | 111 | 97% | 577 tight |
| 0x791000 | 4097 | 3965 | 132 | 97% | 555 tight |
| 0x79f000 | 2918 | 2805 | 113 | 96% | 466 tight |
| 0x7b9000 | 2687 | 2591 | 96 | 96% | 441 tight |
| 0x785000 | 6144 | 6044 | 100 | 98% | 400 tight |
| 0x7c3000 | 4098 | 3846 | 252 | 94% | 387 tight |
| 0x797000 | 2691 | 2600 | 91 | 97% | 339 tight |
| 0x7af000 | 2904 | 2783 | 121 | 96% | 319 tight |
| 0x7a9000 | 2597 | 2519 | 78 | 97% | 287 |
| 0x7d3000 | 1417 | 1318 | 99 | 93% | 283 |
| 0x793000 | 2880 | 2852 | 28 | 99% | 267 tight |
| 0x795000 | 3484 | 3293 | 191 | 95% | 253 |
| 0x7a1000 | 4107 | 3348 | 759 | 82% | 121 |
| 0x7c7000 | 2163 | 2046 | 117 | 95% | 14 |
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
| 0x7cd000 | 6161 | 4637 | 1524 | 75% | - |
| 0x7cf000 | 6144 | 5090 | 1054 | 83% | - |
| 0x7d1000 | 2049 | 1084 | 965 | 53% | - |
| 0x7e5000 | 6144 | 5936 | 208 | 97% | - |
| 0x7e7000 | 6144 | 4479 | 1665 | 73% | - |

## Worst offenders (restore fuller text here once relocation lands)
- **0x7c1000** Lamyu Kose origin-of-the-Martians exposition - cut ~1489. Heavily compressed lore.
- **0x7df000** Welda's backstory - ~1319.  **0x7e1000** party thoughts - ~1208.
- **0x7db000 / 0x7dd000** party strategy/banter blocks - ~1132 each.
- **0x7b3000** Prince Zaate - ~984.  **0x79d000** Kidun briefing - ~908.
- **0x7a5000** Shaina reunion/bar - ~816.  **0x78b000** spaceport - ~793.  **0x7bb000** Wultria - ~762.
- **0x7e3000** trials banter - ~749.  **0x7b7000** Bartz/snow tank - ~727.  **0x7ad000** Yaku trial - ~697.
- **0x7e9000** Atraia/weapon-dev - ~655.  **0x7b1000** - ~624.  **0x7c9000** Zolian town - ~577.

## Tightest raw budgets (little room even before English grows)
- 0x7d3000 (1417), 0x7d1000 (2049), 0x7a9000 (2597), 0x7b9000 (2687), 0x797000 (2691),
  0x7c7000 (2163), 0x793000 (2880), 0x7af000 (2904), 0x79f000 (2918), 0x7e9000 (3211).

