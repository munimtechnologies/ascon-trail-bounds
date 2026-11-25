# PREREG back-v1: can a round put in FRONT of the record characteristics be cheap?

2026-11-24, written before any of the computations below ran. MV2 of Munim, Inc. Made with
AI agents working in his name. Text CC BY 4.0, code Apache-2.0.

## Why
Extending L. Sotomayor's 41-active 4-round characteristic forwards gives a 5-round one with
67 active S-boxes, and 26 is the exhaustive minimum for that last round
(`RESULTS_EXT5_V1.md`). The other way to reach 5 rounds is to put a new round in front. A
5-round record (66 or fewer) that way needs a prepended round with 25 or fewer active
S-boxes. The same tool also asks how cheap round 1 can be in front of the shared 11-9-7
tail of all three record 4-round characteristics (`RESULTS_EXT5_V2.md`).

## Method (`ascon_backward.py`)
Fix the S-box output y of a round. Its input x may be any difference the S-box allows,
column by column. The round in front then has output L^-1(x), and its active S-boxes are
the non-zero columns of L^-1(x). Each row of x lies in the 2^|C|-element space of words on
the active columns C, so every row value with a sparse enough preimage is listed exactly
(Gray code), and rows are combined by depth-first search with pruning on the union. For a
threshold T this finds every allowed x whose round in front has at most T active S-boxes.
No solver. The inverse linear layer is Sigma^63 (because Sigma^64 = identity over GF(2)).
`test_ascon_backward.py` checks it against an independent brute force on random instances.

## Claims, each checked exhaustively by its own commit-time test
| Id | Fixed part | Claim | Test |
|---|---|---|---|
| B1 | sanity | search reproduces the published round-2 input of the w125 trail at T = 14 | `test_ascon_backward.py` |
| B2 | round-2 output of w125 (= the shared tail) | round 1 needs >= 14 active S-boxes over every allowed round-2 input | `test_ascon_backward_core.py` |
| B3a | round-1 output of w125 | a prepended round needs >= 26 | `test_ascon_backward_prepend_w125.py` |
| B3b | round-1 output of w140 | a prepended round needs >= 26 | `test_ascon_backward_prepend_w140.py` |

Predictions: B2 holds (as we read Sotomayor's README, his family restricts only the round-2
and round-3 output rows, so his exact minimum of 41 within it would imply B2; B2 is then an
independent check of one consequence, by a different method). B3a and B3b hold (the inverse linear layer is dense). We expect these tests to
pass.

## How to read the outcomes
Each test is committed only if it passes within the publishing pipeline's time limit, so
its presence in the repository is the result.
- B1 present, B2 absent: the search found a round 1 with 13 or fewer active S-boxes in front
  of the tail, i.e. a candidate 4-round characteristic with 40 or fewer (or the test timed
  out). We would then find it explicitly and check it with `check_trail` before any claim.
- B1 present, B3a or B3b absent: a candidate 5-round characteristic with 66 or fewer (or a
  timeout). Same follow-up.
- B1 absent: the tool is wrong somewhere; nothing from B2/B3 is reported.
Exact minima (not just the bars) come from `python ascon_backward.py --data ... --out ...`
when compute allows; they will be added here as measured.

## Limits
This covers one fixed tail (B2) and two fixed 4-round characteristics (B3). A 5-round
characteristic that changes more than one end at once is not covered.
