# Pre-registration: searching near the best known Ascon characteristics for new records (rec-v1)

Registered 2026-11-17 by MV2 of Munim, Inc. (mv2@munimtech.com), before any run of this
search. Made with AI agents working in his name. Licence: CC BY 4.0 for this text; code Apache-2.0.

## Why a second line next to v1
v1 (`PREREG_4R_DIFF_V1.md`) asks a SAT solver directly whether a 4-round characteristic with
36 or fewer active S-boxes exists. We have since learned that the published bound of 36
(Erlacher, Mendel and Eichlseder, ToSC 2022(1)) was obtained by splitting the problem into many
per-round patterns. A secondary summary puts the total at roughly 600 CPU days; we could not
read that figure in the paper itself, so treat it as unconfirmed. Our v1 job has 2 CPUs for about
3 hours, so its 4-round rows will very likely end in TIMEOUT. We leave v1 unchanged, and it will
be graded as registered.

The other side of the gap can be checked cheaply. A characteristic that a solver *finds* can be
verified by anyone in milliseconds, without trusting the solver or the encoding. The best known
4-round characteristic has 42 active S-boxes and the best known 5-round one has 68 (both by
N. Otoi, 2026, github.com/otoinobuo/ascon-trails, not peer reviewed; earlier records were 43 and
44 for 4 rounds and 72 and 78 for 5 rounds). Otoi's paper reports that runs asking directly for
41 or fewer gave no answer in about 7.5 hours, that repeat runs of his descending search mostly
stalled at 45. It describes no neighbourhood or local search. That is the approach we test here.

## Question
Does a 4-round characteristic of Ascon-p with at most 41 active S-boxes, or a 5-round one with at
most 67, exist close to the best published ones?

## Method (fixed now)
- Seeds: `trails/ascon_4r_42active.json` and `trails/ascon_5r_68active.json` from
  github.com/otoinobuo/ascon-trails (MIT licence; branch main, commit 8ad5d145 on 2026-11-06),
  downloaded by the job. The job records each file's SHA-256.
- Model: `ascon_model.py` 0.1.0, the same exact CNF as v1 but without the rotational symmetry
  clause, since a seed fixes the rotation. Search: `ascon_lns.py` 0.1.0.
- A neighbourhood is a pair (restricted rounds, d). In each restricted round, at most d columns
  may be active outside the columns active in the current best characteristic. All other rounds
  are free. The solver is asked for a characteristic in that neighbourhood with at most
  (current best - 1) active S-boxes in total. The schedule is fixed in `ascon_lns.SCHEDULE`:
  22 neighbourhoods for 4 rounds and 17 for 5 rounds, from the most restrictive (rounds 2-4
  restricted, d = 0) to looser ones (d up to 4). Round numbers here count from 1; in the code
  they count from 0.
- Every solver answer of SAT is re-checked by `check_trail`, which uses the S-box DDT and the
  linear layer directly and no formula. An improvement then becomes the new best, and the
  schedule restarts from the top with the bound lowered by one.
- Job `ascon-rec-v1`: one lane per round count (2 CPUs), 2 GB, 160 minutes of search, 300 s
  per neighbourhood. CaDiCaL 1.9.5 through PySAT, or the first available fallback. Unit tests
  run first.

## Rows and what counts
| Row | Claim tested | Holds if |
|---|---|---|
| S0-4r | Otoi's 4-round characteristic is valid with 15-11-9-7 (42) | our independent checker returns exactly these counts |
| S0-5r | Otoi's 5-round characteristic is valid with 15-11-9-7-26 (68) | same |
| S1-4r, S1-5r | the seed satisfies its own neighbourhood formula, and the solver finds a solution with all rounds restricted (d = 0, bound = seed total) | both true |
| Q-4r | NEW: a 4-round characteristic with <= 41 active S-boxes | a re-checked characteristic is found |
| Q-5r | NEW: a 5-round characteristic with <= 67 active S-boxes | a re-checked characteristic is found |

- S0 is an independent check of a result that has not been peer reviewed. If S0 fails for a
  round count, that lane does not run, and we report the failure as measured. Before saying
  anything about Otoi's trail, we will check whether our bit or row conventions caused it.
- If Q holds, it is a new record characteristic. It is published with its hex differences, and a
  later job looks for a conforming pair of states, because some published trails turned out to
  be impossible for real values. Until a pair is found we will call it a characteristic, not a
  trail that real values follow.
- If Q does not hold, the result is "not found in these neighbourhoods". That says nothing
  about whether such a characteristic exists. Neighbourhoods that end UNSAT are listed as
  solver results; neighbourhoods that hit the time limit are listed as inconclusive.

## What would be remarkable
A 4-round characteristic with 41 or fewer active S-boxes would be the third improvement on the
designers' 44 (after 43 in 2022 and 42 in 2026) for the permutation inside NIST's
lightweight-cryptography standard, and it would narrow the
open interval [36, 42]. A 5-round improvement would lower the best known count for 5 rounds,
for which no lower bound has been published.

## Limits stated in advance
Fewer active S-boxes do not mean a higher probability (Otoi's 42 has weight 138, above the best
known 4-round weight of 107). This is not an attack on Ascon. All of the search is local, so a
negative result is weak by design.
