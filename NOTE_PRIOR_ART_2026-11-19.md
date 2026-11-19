# Note: new prior art and new record bars (2026-11-19, before any rec-v1, rec-v2 or pair-v1 result)

None of our jobs (`ascon-4r-v1`, `ascon-rec-v1`/`-v2`, `ascon-pair-v1`, `ascon-prof-v1`) has
returned a result yet. This note was written before any of them did.

1. On 2026-11-18 L. Sotomayor published two 4-round characteristics of Ascon-p with **41**
   active S-boxes (profile 14-11-9-7, weights 125 and 140), with conforming pairs and a verifier:
   https://github.com/sotomayorlucas/ascon-41-trail (v1.0.0, MIT, Zenodo
   10.5281/zenodo.24344400). Their README says 41 is the minimum within their restricted search
   family, and mentions LRAT-checked UNSAT certificates for sparse families at 40 or fewer, in a
   separate note to come. The open range for 4 rounds is now [36, 41].
2. On 2026-11-19 we extended that 41-trail by one round to a 5-round characteristic with **67**
   active S-boxes (`RESULTS_EXT5_V1.md`).

Grading changes (rows as pre-registered; only the meaning of "record" moves):
- rec-v1 / rec-v2, row Q: a 4-round characteristic with 41 active S-boxes now **ties** the best
  known. A 4-round **record now needs 40 or fewer**. A 5-round **record now needs 66 or fewer**.
  Both the old and the new bars are reported.
- rec-v2: we add an extra report-only row, C0c. Is 14-11-9-7 in Makarim and Rohit's list of
  possible 4-round configurations, and does it pass their filters? It is read from the job's
  `out/` files, just like C0b.
- pair-v1: unchanged. A pair search for the 67-characteristic will be pre-registered separately.
