# RESULTS ext5-v2: the 5-round 67 checked end to end, and a second 67

2026-11-24. MV2 of Munim, Inc. Made with AI agents working in his name; no human expert has
checked it yet. Text CC BY 4.0, code Apache-2.0.

## Result
1. **The full 5-round characteristic with 67 active S-boxes (14-11-9-7-26) passes our own
   check, round by round.** `ext5_full_w125.json` holds all five rounds: rounds 1-3 and the
   round-4 input copied unchanged from L. Sotomayor's 41-active 4-round characteristic
   ([ascon-41-trail](https://github.com/sotomayorlucas/ascon-41-trail) v1.0.0, weight 125), and
   the round-4 output changed in column 21 only (`RESULTS_EXT5_V1.md`). `ascon_model.check_trail`,
   which uses no formula, checks every column of every round against the S-box difference table
   and every link x_{r+1} = L(y_r). It returns [14, 11, 9, 7, 26].
2. **A second, different 5-round characteristic with 67.** Sotomayor's other 41-active
   characteristic (weight 140) has a different round 1, but from the round-2 output on it is
   the weight-125 one rotated by 26 bits. Appending the same two-round suffix, rotated the same
   way, gives 14-11-9-7-26 = 67 again.
3. **All three record 4-round characteristics share one tail.** From the round-2 output to
   the round-4 input, Otoi's 42-active characteristic
   ([ascon-trails](https://github.com/otoinobuo/ascon-trails)) is the weight-125 one rotated by
   47 bits. The three differ only in round 1, the round-2 input and (Otoi) the round-4 output.
   So Otoi's 68 = 15-11-9-7-26 and our 67 = 14-11-9-7-26 extend the same 11-9-7 tail with the
   same 26-active last round (26 is the exhaustive minimum for this round-4 input, and rotation
   does not change it). The one S-box gained comes from round 1 (Sotomayor's 14 against Otoi's
   15).

Every statement above is asserted by `test_ascon_extend_full.py`. The publishing pipeline
runs it before this file can be committed.

| Rounds | Best before | Now |
|---|---|---|
| 4 | 42 [Otoi26], 41 [Sot26] | 41 (unchanged) |
| 5 | 68 [Otoi26] | **67**, two characteristics (this file) |

Record history: `ext5_records.json`.

## Rotations
`AM.rotate_state(w, s)` rotates every row right by s bits (bit j to bit j - s).
- w140 = rotate(w125, 26) for the round-2 output, round 3 and round 4 (in and out).
- Otoi = rotate(w125, 47) for the round-2 output, round 3 and the round-4 input.
- Round-4 input of w125: x4 = `0220000008202208` (columns 3, 9, 13, 21, 27, 53, 57); of w140:
  x4 = `0808820088000002`; of Otoi: x4 = `0000104044100440`.

## What this does not show
- No conforming pair has been searched for either 5-round characteristic. Changing one round-4
  output may make the published 4-round pair stop following it. This is a count of active
  S-boxes, not a probability record (both have weight far above any attack) and not an attack
  on Ascon. Full 12-round Ascon is unaffected.
- That 67 is optimal for 5 rounds. Next: `PREREG_BACK_V1.md` asks whether a round put in front
  of the 41-trails can be cheaper than 26.
