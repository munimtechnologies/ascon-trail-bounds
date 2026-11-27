# RESULTS back-v1: no cheaper round in front of the record characteristics

2026-11-27. MV2 of Munim, Inc. Made with AI agents working in his name. No human expert has
checked it yet. Text CC BY 4.0, code Apache-2.0.

All four pre-registered claims of `PREREG_BACK_V1.md` passed. Each is checked exhaustively
by its own test, and the publishing pipeline committed each test only after it passed:

| Id | Claim (exhaustive, `ascon_backward.py`, no solver) | Test | Commit |
|---|---|---|---|
| B1 | the search reproduces the published round-2 input of the w125 trail at T = 14, and agrees with an independent brute force | `test_ascon_backward.py` | 53af92e5 |
| B2 | in front of the shared 11-9-7 tail (round-2 output fixed), round 1 needs **at least 14** active S-boxes, over every round-2 input the S-box allows | `test_ascon_backward_core.py` | 66fe88da |
| B3a | a round put in front of Sotomayor's 41-active (weight 125) characteristic needs **at least 26** | `test_ascon_backward_prepend_w125.py` | ca71d967 |
| B3b | the same for the weight-140 characteristic: **at least 26** | `test_ascon_backward_prepend_w140.py` | 2c549880 |

## What follows
1. **The shared tail is used optimally.** Every 5-round characteristic whose rounds 2-4 are the
   tail (round-2 output to round-4 input, up to rotation) has at least
   14 + 11 + 9 + 7 + 26 = 67 active S-boxes. Round 1 needs at least 14 (B2), and round 5 needs
   at least 26 (the exhaustive minimum over all 8^7 round-4 outputs, `RESULTS_EXT5_V1.md`).
   Our 67 (`RESULTS_EXT5_V2.md`) meets this bound, so it is optimal for that tail. The same
   holds for 4 rounds: 41 is optimal for the tail in rounds 2-4.
2. **Prepending does not help.** A 5-round characteristic made by putting a round in front of
   either 41-active characteristic has at least 26 + 41 = 67.
3. So a 5-round record of 66 or fewer needs a different middle. `PREREG_FAM5_V1.md` searches
   the record family for one, with both ends optimised at the same time.

## Limits
These are exact statements about fixed tails and fixed characteristics, not about all
5-round characteristics. They count active S-boxes, not probabilities, and are not an
attack on Ascon.
