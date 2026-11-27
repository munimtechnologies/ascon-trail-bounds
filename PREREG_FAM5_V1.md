# PREREG fam5-v1: a two-ended exact search of the record family

2026-11-27. Written before any of the computations below ran. MV2 of Munim, Inc. Made with
AI agents working in his name. Text CC BY 4.0, code Apache-2.0.

## Why
Every record characteristic we know of lies in one family: Sotomayor's two 41s and Otoi's 42
over 4 rounds, and our two 67s and Otoi's 68 over 5 rounds. Sotomayor
([ascon-41-trail](https://github.com/sotomayorlucas/ascon-41-trail) v1.0.0) restricts the
round-2 S-box output to rows x1 and x4 and the round-3 output to row x4, and reports an exact
4-round minimum of 41 inside that family. back-v1 (`RESULTS_BACK_V1.md`) showed that the one
tail all records share cannot be improved by changing round 1 or by putting a round in front.
The open question is whether a *different* member of the family, with both ends optimised
at the same time, beats 67 over 5 rounds. As far as we know, no search of this kind has been
published for 5 rounds.

## The family is fixed by one 64-bit word (`ascon_family5.py`)
Write v for the round-3 output row x4. The S-box facts DDT[00001][00001] = 0,
DDT[01000][00001] = 0 and DDT[01001][00001] > 0 force every active column of the round-3
input to be 01001. So the round-2 output is (0, o1, 0, 0, o4) with
o1 = Sigma1^-1(v) and o4 = Sigma4^-1(v), and the round-4 input is z = Sigma4(v) in row x4.
Rounds 2, 3 and 4 have |o1 | o4|, |v| and |z| active S-boxes. Round 1 and round 5 are left
completely free:
- R1(v): the exact minimum over every round-2 input that the S-box allows (`ascon_backward.search`);
- R5(z): the exact minimum over every round-4 output (`ascon_extend.best_extension`, for
  |z| <= 7), or the lower bound |Sigma1(z)| otherwise. The bound holds because every S-box output
  for input 00001 has bit x1 set (checked in the test), so the round-5 input row x1 is Sigma1(z).

T4 = R1 + |o1 | o4| + |v| + |z| and T5 = T4 + R5.

## Search
o1, o4, v and z are GF(2)-linear images of one another. Pick one of them as the anchor, and
enumerate every anchor word of weight k up to rotation (bit 0 set: C(63, k-1) words). The
other words are updated by table XORs. A cheap exact filter (R1 >= 1, R5 >= |Sigma1 z|) keeps
the words that could reach T4 <= 40 or T5 <= 66. Each survivor's rotation class then gets the
exact R1 search. A survivor is "ok" when R1 is proven large enough, a "candidate" when a round 1
is found that reaches a bar, and "undecided" when round 2 has more than 22 active columns
(too many for the exact R1 search).

## Claims, each checked exhaustively by its own commit-time test
| Id | Anchor words | Claim | Test |
|---|---|---|---|
| F0 | sanity | S-box facts; the w125 record is the family member with \|o4\| = 3; scan() equals a table-free brute force on every anchor for k <= 3 (and a k = 4 slice); the candidate path finds the published round 1 when the 4-round bar is raised to 41 | `test_ascon_family5.py` |
| F1 | o1, o4, v, z of weight 1-6 | no member has T4 <= 40 or T5 <= 66 (all ok) | `test_ascon_family5_k6.py` |
| F2 | z of weight 7 (67,945,521 words) | same | `test_ascon_family5_k7_z.py` |
| F3 | v of weight 7 | same | `test_ascon_family5_k7_v.py` |
| F4 | o4 of weight 7 | same | `test_ascon_family5_k7_o4.py` |
| F5 | o1 of weight 7 | same | `test_ascon_family5_k7_o1.py` |

Predictions: F0 passes. F1-F5 pass for the 4-round bar, because Sotomayor reports 41 as the
exact family minimum. For the 5-round bar we do not know. We expect a pass, because the record
member is the cheapest one we know and its R5 of 26 is already near |Sigma1 z|.

## How to read the outcomes
Each test is committed only if it passes within the publishing pipeline's time limit. So its
presence in the repository is the result.
- F0 absent: the tool is wrong somewhere, and nothing from F1-F5 is reported.
- F0 present, Fi absent: some member is a candidate, or undecided, or the test ran out of
  time. Next we bisect with narrower tests (one k, one slice of the second-lowest bit, or
  "no candidate" separately from "no undecided"). Any candidate is written out explicitly and
  checked with `check_trail` before it is called a characteristic.
- All present: every family member in which at least one of o1, o4, v, z has 7 or fewer
  active columns needs at least 41 active S-boxes over 4 rounds and at least 67 over 5. Our
  67 is then optimal over that part of the family.

## Limits
- This is not the whole family. A member in which all of o1, o4, v and z have 8 or more
  active columns is not covered (rounds 2-4 then have at least 24 active S-boxes).
- It does not reach outside the family (round-2 output rows other than x1 and x4, or a
  round-3 output outside row x4).
- These are counts of active S-boxes, not probabilities. It is not an attack on Ascon.
