# Pre-registration: 4-round differential active-S-box bound for the Ascon permutation (v1)

Registered 2026-11-17 by MV2 of Munim, Inc. (mv2@munimtech.com), before any solver run.
Made with AI agents working in his name. Licence: CC BY 4.0 for this text; code Apache-2.0.

## Question
Ascon (NIST SP 800-232, 2025) is the U.S. standard for lightweight authenticated encryption
and hashing. How many S-boxes must be active in any 4-round differential characteristic
(trail) of its 320-bit permutation Ascon-p? Call this minimum M4.

State of the art as far as we could find on 2026-11-17 (see README for links):
- 3 rounds: exactly 15 (designers, Cryptanalysis of Ascon, CT-RSA 2015).
- 4 rounds, lower bound: M4 >= 36 (Erlacher, Mendel, Eichlseder, ToSC 2022(1), SAT); marked not tight.
- 4 rounds, best trails: 44 (designers), 43 (Makarim and Rohit, ToSC 2022(3)),
  42 (N. Otoi, 2026, github.com/otoinobuo/ascon-trails, not peer reviewed).
- So 36 <= M4 <= 42. Makarim and Rohit (FSE 2023 slides): "Finding exact differential and
  linear bounds for 4 rounds Ascon is still challenging."

## Method (fixed now)
- Model: `ascon_model.py` 0.1.0. Exact CNF of the S-box DDT (Quine-McCluskey prime implicants
  plus a greedy cover, checked against all 1,024 input/output pairs), XOR clauses for the linear
  layer (rotations 19/28, 61/39, 1/6, 10/17, 7/41), active flags a <-> OR(column), and a Sinz
  sequential counter for "at most B active S-boxes". Rotational symmetry: column 0 of round 2
  (round index 1) is forced active. This loses no generality, because every column is an
  identical S-box and the linear layer only rotates rows.
- Soundness tests: every characteristic followed by real pairs through real Ascon rounds, and
  by their rotations, must satisfy the formula.
- Solver: the first available of CaDiCaL 1.9.5, CaDiCaL 1.5.3, Glucose 4, MiniSat 2.2 (PySAT).
- Job `ascon-4r-v1`: 2 CPUs, 2 GB, 165-minute wall budget. Lane A runs (1,0),(1,1),(2,3),(2,4),
  (3,14),(3,15),(4,35). Lane B runs (4,36). Each (R,B) asks whether an R-round characteristic
  with <= B active S-boxes exists. Any task unfinished at the deadline is TIMEOUT. The DIMACS
  files of (4,35) and (4,36) are saved so anyone can re-run them.

## Rows and what counts
| Row | Claim tested | Holds if |
|---|---|---|
| R1 | 1-round minimum is 1 | (1,0) UNSAT and (1,1) SAT with 1 |
| R2 | 2-round minimum is 4 | (2,3) UNSAT and (2,4) SAT with 4 |
| R3 | 3-round minimum is 15 | (3,14) UNSAT and (3,15) SAT with 15 |
| R4 | M4 >= 36 (published) | (4,35) UNSAT |
| R5 | NEW: M4 >= 37 | (4,36) UNSAT |

- R1-R3 are calibration. If any fails, the model is not trusted and R4/R5 are not graded.
- R4 SAT would contradict a published proof: stop and investigate the model before saying anything.
- R5 UNSAT is reported as a solver result. We will call it "proved" only after a v2 job
  re-solves the published DIMACS with a proof-producing solver and the DRAT/LRAT certificate
  passes a checker. Any trail a solver returns (SAT) is re-checked by `check_trail`, which uses
  the DDT and linear layer directly, not the formula.
- R5 SAT with exactly 36 active S-boxes would be a new record trail (better than 42).
- TIMEOUT means inconclusive and is published as such. The next version then splits the
  instance by the active-S-box count per round, using the proved 2- and 3-round minima as cuts.

## What would be remarkable
Closing the gap, i.e. the exact value of M4, would settle a question that three 2022 ToSC
papers left open for the permutation inside NIST's lightweight-cryptography standard. Moving
the proved bound from 36 to 37 or more is a smaller but real step.

## Limits stated in advance
Active-S-box counts bound the probability of single characteristics, not differentials
(clustering), and say nothing about the linear case, which comes later. The result concerns
the bare permutation, not an attack on Ascon. Our runs are small (2 CPUs, about 3 hours),
so TIMEOUT is a likely outcome and an honest one.
