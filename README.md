# ascon-trail-bounds

Open, pre-registered work on a question about the cryptographic strength of **Ascon**, the
NIST lightweight-cryptography standard (SP 800-232, 2025): what is the smallest number of
active S-boxes in a 4-round (and 5-round) differential characteristic of its permutation?

By MV2 of Munim, Inc. (mv2@munimtech.com). The code and text were made with AI agents working
in his name. Licence: Apache-2.0 (code), CC BY 4.0 (text).

## Latest result (2026-11-19)
**A 5-round characteristic with 67 active S-boxes** (profile 14-11-9-7-26), one fewer than the
best published 68. It extends by one round the 41-active 4-round characteristic published on
2026-11-18 by L. Sotomayor, changing only one round-4 S-box output. An exhaustive check of all
8^7 round-4 output choices shows that 26 is the fewest active S-boxes round 5 can have after
that trail. See `RESULTS_EXT5_V1.md` and `ext5_w125_suffix.json`. Limits: rounds 1-3 are
Sotomayor's and are re-checked end to end by job `ascon-ext-v1`. No conforming pair has been
searched for yet, and no human expert has checked this.

## Why this question
For 4 rounds of Ascon-p, the proven lower bound is **36** active S-boxes. The best
characteristic known has **41** (since 2026-11-18). Nobody knows which number in between is the
true minimum. Closing that gap would give the exact 4-round minimum for the permutation of a
deployed standard.

| Rounds | Proven lower bound | Best characteristic found |
|---|---|---|
| 3 | 15 (exact) | 15 |
| 4 | 36 [EME22] | 44 [designers], 43 [MR22], 42 [Otoi26], 41 [Sot26] |
| 5 | (none listed; 6-round bound 54 [EME22]) | 78, 72 [MR22], 68 [Otoi26], **67 (this repo)** |

Prior work:
- Dobraunig, Eichlseder, Mendel, Schläffer. Cryptanalysis of Ascon. CT-RSA 2015. https://eprint.iacr.org/2015/030
- [EME22] Erlacher, Mendel, Eichlseder. Bounds for the Security of Ascon against Differential and Linear Cryptanalysis. ToSC 2022(1), 64-87. https://doi.org/10.46586/tosc.v2022.i1.64-87
- [MR22] Makarim, Rohit. Towards Tight Differential Bounds of Ascon: A Hybrid Usage of SMT and MILP. ToSC 2022(3), 303-340. https://doi.org/10.46586/tosc.v2022.i3.303-340 (code and configuration lists: https://github.com/Crypto-TII/ascon_hybrid_milp_smt, Apache-2.0)
- El Hirch, Mella, Mehrdad, Daemen. Improved Differential and Linear Trail Bounds for ASCON. ToSC 2022(4), 145-178. https://eprint.iacr.org/2022/1377
- Song et al. New Differential-Based Distinguishers for Ascon via Constraint Programming. IET Information Security 2024.
- AlgSAT: a SAT method for search and verification of differential characteristics. https://eprint.iacr.org/2022/1641 (right pairs for Ascon characteristics; one published 4-round characteristic found to have none).
- [Otoi26] N. Otoi, github.com/otoinobuo/ascon-trails (2026, not peer reviewed): 42-active 4-round and 68-active 5-round characteristics, with one real pair for the 4-round one.
- [Sot26] L. Sotomayor, github.com/sotomayorlucas/ascon-41-trail (v1.0.0, 2026-11-18, not peer reviewed; Zenodo 10.5281/zenodo.24344400): two 41-active 4-round characteristics (14-11-9-7) with conforming pairs.

## Lines of work
1. **Lower bound (v1).** Ask a SAT solver directly whether a 4-round characteristic with 35 or
   36 active S-boxes exists (`run_bounds.py`, `PREREG_4R_DIFF_V1.md`). The published 36 was
   obtained by splitting the problem into many per-round patterns, at a cost reported second-hand
   as hundreds of CPU days, so our small runs will probably time out. We will publish whatever
   they return.
2. **Record characteristics near the best known (rec-v1).** A large-neighbourhood search around
   the best published characteristics (`ascon_lns.py`, `PREREG_REC_V1.md`). Anything found is
   re-checked without the formula, so a record does not depend on trusting the solver. Since
   2026-11-18 a 4-round record needs 40 or fewer and a 5-round record 66 or fewer
   (`NOTE_PRIOR_ART_2026-11-19.md`).
3. **Real pairs (pair-v1).** A characteristic only describes differences, and some published
   ones have no real pair at all. `ascon_pair.py` builds a value-level SAT model with the round
   constants of each window of rounds and searches for two real states that follow a given
   characteristic. Every pair it returns is re-run through the real permutation
   (`PREREG_PAIR_V1.md`).
4. **Configuration-guided records (rec-v2).** Split the search by the number of active S-boxes
   per round, using MR22's published list of possible 4-round configurations and their filter
   rules (read as data; their script is never run). Each maximal per-round cap becomes one small
   SAT question (`ascon_profiles.py`, `PREREG_REC_V2.md`).
5. **Exact one-round extensions (ext5).** For a fixed last-round input, enumerate every
   allowed last-round output and count the active S-boxes of the next round exactly
   (`ascon_extend.py`, `RESULTS_EXT5_V1.md`). No solver is involved.

## What is here
- `ascon_model.py`: an exact CNF model of Ascon-p differential characteristics, written in
  pure Python, plus an independent trail checker that does not use the formula.
- `test_ascon_model.py`: checks the S-box against the specification table, checks that the
  S-box CNF matches the DDT on all 1,024 pairs, checks that real pairs through real rounds
  (and their rotations) satisfy the formula, and brute-forces the cardinality encoding.
- `run_bounds.py`, `test_run_bounds.py`: the v1 lower-bound tasks on 2 CPUs, with grading.
- `ascon_lns.py`, `test_ascon_lns.py`: the neighbourhood search.
- `ascon_pair.py`, `test_ascon_pair.py`: the value-level pair search.
- `ascon_profiles.py`, `test_ascon_profiles.py`: the configuration-guided search.
- `ascon_extend.py`, `test_ascon_extend.py`: exact one-round extension. The tests check it
  against an independent brute force, and re-derive every number in `RESULTS_EXT5_V1.md`,
  including the exhaustive minimum of 26 over all 8^7 choices.
- `PREREG_*.md`: each question, its rows, and what counts as a result, all fixed before any run.
- `NOTE_JOBS_2026-11-17.md`, `NOTE_PRIOR_ART_2026-11-19.md`: notes written before any result.

Run them: `pip install python-sat`, then `python run_bounds.py --out results --minutes 165`,
`python ascon_lns.py --data DIR_WITH_SEED_JSON --out results --minutes 160`,
`python ascon_pair.py --data DIR_WITH_TRAIL_JSON --out results --per-window 300`,
`python ascon_profiles.py --data DIR_WITH_MR22_AND_SEED --out results --minutes 165`, or
(standard library only) `python ascon_extend.py --data DIR_WITH_TRAIL_JSON --out results`.

## Status
- 2026-11-17: v1, rec-v1 and pair-v1 pre-registered; jobs filed.
- 2026-11-19: rec-v2 pre-registered; job `ascon-prof-v1` filed. None of the earlier jobs has
  started yet, so there are no results from them.
- 2026-11-19 (later): the 41-trail of [Sot26] appeared, so the record bars moved
  (`NOTE_PRIOR_ART_2026-11-19.md`). We extended it to 5 rounds: 67 active S-boxes
  (`RESULTS_EXT5_V1.md`). Job `ascon-ext-v1` re-checks the full 5-round characteristic.

Results will be published here as measured, including timeouts and searches that find nothing.
