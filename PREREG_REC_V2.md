# Pre-registration: configuration-guided search for a 4-round Ascon characteristic with at most 41 active S-boxes (rec-v2)

Registered 2026-11-19 by MV2 of Munim, Inc. (mv2@munimtech.com), before any run of this
search and before any result of rec-v1 (`PREREG_REC_V1.md`) or pair-v1 (`PREREG_PAIR_V1.md`).
Made with AI agents working in his name. Licence: CC BY 4.0 for this text; code Apache-2.0.

## Why a third search
rec-v1 searches close to Otoi's 42-active characteristic (same active columns, small changes).
A characteristic with 41 or fewer could look quite different. Otoi reports that asking a solver
directly for "41 or fewer in total" gave no answer in about 7.5 hours. Makarim and Rohit
(ToSC 2022(3), "MR22") split the 4-round problem by **configuration**: the number of active
S-boxes in each of the 4 rounds. Their repository (github.com/Crypto-TII/ascon_hybrid_milp_smt,
Apache-2.0, commit 0d3711de, `milp/4round_cases/`) publishes the full list of configurations
that "may give a 4-round trail with at most 44 active S-boxes" (`possible_configurations.txt`)
and a script with rules that remove impossible ones. We use that list to split the search for
41 or fewer into many smaller SAT questions, each of which a solver may answer quickly.

## Question
Does a 4-round differential characteristic of Ascon-p (NIST SP 800-232) with at most 41 active
S-boxes exist? We search for one. We do not try to prove that none exists.

## Method (fixed now)
- Inputs, downloaded by the job with SHA-256 recorded: MR22's `script.py` and
  `possible_configurations.txt` at commit 0d3711de, and Otoi's `trails/ascon_4r_42active.json`
  (github.com/otoinobuo/ascon-trails, MIT).
- MR22's `script.py` is **never executed**. Its constant lists `ZZF` (infeasible 3-round
  configurations), `ZZT_21` (valid 3-round configurations with sum <= 21) and `LIN` (minimum
  active S-boxes after k active ones) are read with `ast.literal_eval`.
- Every line of the configuration file with 4 integers in 1..64 is read, including the last
  line, which MR22's loop skips; the summary reports what that line is.
- Filters, re-implemented from MR22's script and unit-tested against a line-by-line
  transcription of it: (1) neither 3-round window is in `ZZF`; (2) every 3-round window with sum
  <= 21 is in `ZZT_21`; (3) `T[r+1] >= LIN[T[r] - 1]`; (5) MR22's rules that 2 active S-boxes
  cannot be followed by 23 or more, nor 3 by 33 or more. MR22's step 4 (four exclusions
  justified only by comments) is **not** applied; those configurations are kept and counted.
- Keep the configurations with sum <= 41. A profile (a0, a1, a2, a3) is solved as a **cap**:
  at most a_r active S-boxes in round r. A cap covers every configuration below it, so only
  the maximal profiles (not dominated in every round by another kept profile) are solved.
- Order, fixed: L1 distance to 15-11-9-7 (the best published profile), then larger sum first,
  then lexicographic. The first item of the queue is a control: the cap 15-11-9-7 itself.
- Model: `ascon_model.py` 0.1.0 (the exact CNF used by v1 and rec-v1), with Sinz counters per
  round and the clause "column 0 of round 2 is active" (rotational symmetry; every non-zero
  characteristic has a rotation that satisfies it). Search code: `ascon_profiles.py` 0.1.0.
- After a record with total t, the remaining profiles are solved with the extra cap "at most
  t - 1 in total".
- Every SAT answer is re-checked by `check_trail` (S-box DDT and linear layer, no formula).
- Job `ascon-prof-v1`: 2 lanes on 2 CPUs, 2 GB, 165 minutes, 120 s per profile (300 s for the
  control). CaDiCaL 1.9.5 through PySAT, or the first available fallback. Unit tests run first.

## Rows and what counts
| Row | Claim tested | Holds if |
|---|---|---|
| D0 | MR22's inputs are found and parse (ZZF, ZZT_21, LIN of 64 ints, a non-empty configuration list) | all parse |
| C0 | Otoi's characteristic re-checks as 15-11-9-7 and satisfies the cap formula 15-11-9-7 but not 14-11-9-7 | all three |
| C0b | 15-11-9-7 is in MR22's list and passes filters 1, 2, 3 and 5 | reported as found (if it is missing or filtered out, that is reported plainly: MR22's list or rules would then exclude a real characteristic) |
| C2 | the solver returns UNSAT for 2 rounds capped at 1-2 (the 2-round minimum is 4) | UNSAT within 60 s |
| C1 | the solver finds a characteristic inside the cap 15-11-9-7 within 300 s | SAT; a TIMEOUT means the 120 s TIMEOUTs below say little |
| Q | NEW: a 4-round characteristic with at most 41 active S-boxes | a re-checked characteristic is found |
| U | caps the solver proves empty | listed as solver results (uncertified), one per profile |

- Also reported, with no verdict: the number of configurations read, after each filter, with
  sum <= 41, maximal, and how many of those MR22's step 4 would have dropped; profiles tried,
  SAT, UNSAT, TIMEOUT and not reached.
- If Q holds: the characteristic is published with its hex differences as "a characteristic,
  no pair checked yet", and a pair search (as in pair-v1) follows before we call it a trail that
  real values follow.
- If Q does not hold: "not found in the profiles tried". UNSAT caps are solver results about
  those caps only. We make no lower-bound claim: proving 42 is the minimum would need every
  maximal cap closed and the MR22 list and rules to be complete, which this job does not test.

## What would be remarkable
A 4-round characteristic with 41 or fewer active S-boxes for the permutation of NIST's
lightweight-cryptography standard: the third improvement on the designers' 44 (43 in 2022,
42 in 2026), narrowing the open interval [36, 42].

## Limits stated in advance
The time budget covers only a small part of the queue (roughly 160 profiles), so a negative
result is weak. Fewer active S-boxes do not mean a higher probability. This is not an attack on
Ascon, and it uses only the public, unkeyed permutation.
