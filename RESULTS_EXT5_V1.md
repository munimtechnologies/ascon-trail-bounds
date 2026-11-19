# RESULTS ext5-v1: a 5-round Ascon-p characteristic with 67 active S-boxes

2026-11-19. MV2 of Munim, Inc. Made with AI agents working in his name; no human expert has
checked it yet. Text CC BY 4.0, code Apache-2.0.

## Result
Extending the 4-round characteristic with 41 active S-boxes published on 2026-11-18 by
L. Sotomayor ([ascon-41-trail](https://github.com/sotomayorlucas/ascon-41-trail) v1.0.0,
`trails/ascon_p4_41active_w125.json`, profile 14-11-9-7) by one round gives a **5-round
differential characteristic of the Ascon permutation with 67 active S-boxes (profile
14-11-9-7-26)**. The best 5-round characteristic published before has 68 (15-11-9-7-26,
[Otoi 2026](https://github.com/otoinobuo/ascon-trails)); before that 72 (Makarim and Rohit,
ToSC 2022(3)) and 78.

This was not pre-registered. It is a direct, exhaustive computation, and every number here is
re-derived by `test_ascon_extend.py` before this file can be committed.

| Rounds | Best characteristic before | Now |
|---|---|---|
| 4 | 42 [Otoi26], 41 [Sotomayor26] | 41 (unchanged) |
| 5 | 68 [Otoi26] | **67** (this file) |

## How
- The round-4 input of the 41-trail is non-zero only in row x4: `0x0220000008202208`, i.e.
  seven active S-boxes in columns 3, 9, 13, 21, 27, 53, 57, each with input difference 00001.
- The Ascon S-box maps 00001 to 8 possible output differences (9, 11, 13, 15, 24, 26, 28, 30),
  each with probability 2^-3. The published trail uses 01001 (9) in all seven columns.
- Round 5's input is L(y4), linear in the round-4 output. `ascon_extend.best_extension`
  enumerates all 8^7 = 2,097,152 output choices and counts the active S-boxes of L(y4).
- **The minimum is 26.** With the published outputs it is 27 (so the trail as published
  extends to 68, a tie). Changing only column 21's output to 11000 (24) gives 26.
- New round-4 output: x0 = `0000000000200000`, x1 = `0220000008202208`,
  x4 = `0220000008002208` (x2 = x3 = 0). Round-5 input: x0 = `0200000000200004`,
  x1 = `1330404459257248`, x4 = `122040110c11324c`, active columns 2, 3, 6, 9, 12, 13, 14, 16,
  18, 20, 21, 24, 26, 27, 28, 30, 32, 34, 36, 38, 46, 52, 53, 56, 57, 60. Any non-zero round-5
  input has an allowed output (we use S(0) xor S(a)). Data: `ext5_w125_suffix.json`.

Why 26 is the floor for this round-4 input (the exhaustive test confirms it): every allowed
output sets x1, so row x1 of L(y4) is fixed and covers 21 columns. Each column also sets exactly
one of x0, x4 and any subset of x2, x3. Rows x2 and x3 can only add columns. Whichever of x0 or
x4 it sets, column 3 adds a column outside those 21 (26, or 39 and 48), and so do column 13 (36,
or 49 and 58) and column 27 (20, or 8 and 63). Column 9 adds two (2 and 32, or 45 and 54). No
other column produces these, and the four groups are disjoint, so at least 21 + 5 = 26.

## Limits
- Rounds 1-3 are Sotomayor's, unchanged. Their author checks them with a dependency-free
  verifier and gives conforming pairs. We checked only round 4 and round 5 here; job
  `ascon-ext-v1` re-checks the whole 5-round characteristic with our own `check_trail`.
- No conforming pair has been searched for the 5-round characteristic. Changing column 21's
  output may break the published 4-round pair. This is a count of active S-boxes, not a
  probability record and not an attack on Ascon. Full 12-round Ascon is unaffected.
- Only one of the two published 41-trails (weight 125) was extended here. The weight-140 one
  and Otoi's 42-trail are extended in the same job.
- Our neighbourhood search (rec-v1) and our configuration-guided search (rec-v2) were
  pre-registered with "41 or fewer" (4 rounds) and "67 or fewer" (5 rounds) as record bars,
  before this result and before the 41-trail appeared. See `NOTE_PRIOR_ART_2026-11-19.md`.
