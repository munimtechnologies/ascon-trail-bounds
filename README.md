# ascon-trail-bounds

Open, pre-registered work on a question about the cryptographic strength of **Ascon**, the
NIST lightweight-cryptography standard (SP 800-232, 2025): what is the smallest number of
active S-boxes in a 4-round differential characteristic of its permutation?

By MV2 of Munim, Inc. (mv2@munimtech.com). The code and text were made with AI agents working
in his name. Licence: Apache-2.0 (code), CC BY 4.0 (text).

## Why this question
For 4 rounds of Ascon-p, the proven lower bound is **36** active S-boxes. The best
characteristic known has **42**. Nobody knows which number in between is the true minimum.
Closing that gap would give the exact 4-round minimum for the permutation of a deployed
standard. Even moving the proven bound up by one would be a new result, and so would a
characteristic with 41 or fewer.

| Rounds | Proven lower bound | Best characteristic found |
|---|---|---|
| 3 | 15 (exact) | 15 |
| 4 | 36 [EME22] | 44 [designers], 43 [MR22], 42 [Otoi26] |
| 5 | (none listed; 6-round bound 54 [EME22]) | 78, 72 [MR22], 68 [Otoi26] |

Prior work:
- Dobraunig, Eichlseder, Mendel, Schläffer. Cryptanalysis of Ascon. CT-RSA 2015. https://eprint.iacr.org/2015/030
- [EME22] Erlacher, Mendel, Eichlseder. Bounds for the Security of Ascon against Differential and Linear Cryptanalysis. ToSC 2022(1), 64-87. https://doi.org/10.46586/tosc.v2022.i1.64-87
- [MR22] Makarim, Rohit. Towards Tight Differential Bounds of Ascon: A Hybrid Usage of SMT and MILP. ToSC 2022(3), 303-340. https://doi.org/10.46586/tosc.v2022.i3.303-340
- El Hirch, Mella, Mehrdad, Daemen. Improved Differential and Linear Trail Bounds for ASCON. ToSC 2022(4), 145-178. https://eprint.iacr.org/2022/1377
- Song et al. New Differential-Based Distinguishers for Ascon via Constraint Programming. IET Information Security 2024.
- [Otoi26] N. Otoi, github.com/otoinobuo/ascon-trails (2026, not peer reviewed): 42-active 4-round and 68-active 5-round characteristics.

## Two lines of work
1. **Lower bound (v1).** Ask a SAT solver directly whether a 4-round characteristic with 35 or
   36 active S-boxes exists (`run_bounds.py`, `PREREG_4R_DIFF_V1.md`). The published 36 was
   obtained by splitting the problem into many per-round patterns, at a cost reported second-hand
   as hundreds of CPU days, so our small runs will probably time out. We will publish whatever
   they return.
2. **Record characteristics (rec-v1).** A large-neighbourhood search around the best published
   characteristics, looking for a 4-round one with 41 or fewer active S-boxes or a 5-round one
   with 67 or fewer (`ascon_lns.py`, `PREREG_REC_V1.md`). Anything found is re-checked without
   the formula, so a record does not depend on trusting the solver.

## What is here
- `ascon_model.py`: an exact CNF model of Ascon-p differential characteristics, written in
  pure Python, plus an independent trail checker that does not use the formula.
- `test_ascon_model.py`: checks the S-box against the specification table, checks that the
  S-box CNF matches the DDT on all 1,024 pairs, checks that real pairs through real rounds
  (and their rotations) satisfy the formula, and brute-forces the cardinality encoding.
- `run_bounds.py`, `test_run_bounds.py`: the v1 lower-bound tasks on 2 CPUs, with grading.
- `ascon_lns.py`, `test_ascon_lns.py`: the neighbourhood search, with seed loading,
  neighbourhood formulas, the search loop and grading.
- `PREREG_4R_DIFF_V1.md`, `PREREG_REC_V1.md`: each question, its rows, and what counts as a
  result, all fixed before any run.

Run them: `pip install python-sat`, then `python run_bounds.py --out results --minutes 165`, or
`python ascon_lns.py --data DIR_WITH_SEED_JSON --out results --minutes 160`.

## Status
- 2026-11-17: v1 pre-registered; job `ascon-4r-v1` queued.
- 2026-11-17: rec-v1 pre-registered; job `ascon-rec-v1` queued.

Results will be published here as measured, including timeouts and searches that find nothing.
