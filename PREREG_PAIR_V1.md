# Pre-registration pair-v1: do the record characteristics have real pairs?

Fixed on 2026-11-17, before any run of `ascon_pair.py`. By MV2 of Munim, Inc.
(mv2@munimtech.com); made with AI agents working in his name. Text CC BY 4.0, code Apache-2.0.

## Why
A differential characteristic is a statement about differences only. Whether two real
states can follow it through the real permutation, round constants included, is a
separate question. Some published characteristics have no right pair at all: the AlgSAT
paper (ePrint 2022/1641, https://eprint.iacr.org/2022/1641) reports that one 4-round Ascon
characteristic used in earlier attack work admits no right pair. A new record for the minimum number of active S-boxes (rec-v1,
`PREREG_REC_V1.md`) still counts as a characteristic of the permutation if it has no
pair. It is still worth more, and is easier to trust, if a real pair exists and anyone can
re-run it with the reference code.

This is a validity gate for the record search, not a discovery by itself. Right pairs
for 5-round Ascon characteristics have been found before (the AlgSAT paper's Table 20 gives a
conforming pair for the first 5 rounds of a characteristic from [DEMS21]). Otoi (github.com/otoinobuo/ascon-trails) publishes one pair
for the 42-active 4-round characteristic (rounds 8..11) and none for the 68-active 5-round one.

## Method (fixed)
`ascon_pair.py` 0.1.0 with `ascon_model.py` 0.1.0. For R rounds starting at round
index w of the 12-round permutation, the model has value bits A_r (S-box input with
round constant) and B_r = S(A_r) (exact CNF of the S-box graph), A_{r+1} = L(B_r) xor
the next round constant, and, for every active column, a CNF that is exact for the set
{v : S(v) xor S(v xor alpha) = beta}. Inactive columns carry no condition. Every pair
the solver returns is re-run through the real rounds (`ascon_model.trail_from_pair`, no
formula). If that re-run does not reproduce the characteristic, the row is ERROR, never
SAT. Solver: the first of cadical195, cadical153, glucose4, minisat22 that python-sat provides.

Windows: every w with w + R <= 12 (9 windows for 4 rounds, 8 for 5).
Budget: 4 rounds, 300 s per window; 5 rounds, 1,800 s per window; 2 windows at a time.

## Rows
| Row | Claim | What counts |
|---|---|---|
| C0 | The unit tests pass with python-sat installed (they find and re-check pairs for real 2- and 3-round trails) | all tests OK |
| W | Our weight re-check agrees with Otoi's stated weights: 138 (4 rounds), 226 (5 rounds) | equal |
| P4 | Otoi's 42-active 4-round characteristic has a pair in window 8 (rounds 8..11), found and re-checked | SAT + re-check |
| P4-all | In how many of the 9 windows a pair is found in 300 s | a count, no prediction |
| P5 | Otoi's 68-active 5-round characteristic has a pair in at least one of the 8 windows | SAT + re-check in any window |

Outcomes for P5, all published as measured:
- a pair in some window: the 68-active characteristic is realisable in that window.
- UNSAT in a window: the characteristic has no pair in that window (a solver result; it
  will be re-run with a second solver before we state it).
- TIMEOUT: open. Under the usual independence estimate, 2^(320-226) = 2^94 pairs are
  expected per window, so a timeout says nothing about existence.

If rec-v1 finds a record, the record's characteristic is added as row P-rec with the
same method, 4-round budget per window, and its result is published before we call the
record anything more than a characteristic.

## Not claimed
Nothing here bears on the security of Ascon; these are unkeyed statements about
characteristics of the permutation with very low probability.
