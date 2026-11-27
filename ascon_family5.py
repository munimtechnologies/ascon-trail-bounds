# Copyright 2026 Munim, Inc.
# SPDX-License-Identifier: Apache-2.0
# Made with AI agents working in the name of MV2 of Munim, Inc. (mv2@munimtech.com).
"""ascon_family5: exact two-ended search over the one-word family of Ascon-p
differential characteristics that contains every record 4-round characteristic
(Sotomayor's two 41s, Otoi's 42) and our 5-round 67.

The family (Sotomayor 2026, ascon-41-trail README): the round-2 S-box output has
non-zero rows only in x1 and x4, and the round-3 S-box output only in x4. Write v for
the round-3 output row x4. Then everything from the round-2 output to the round-4
input is fixed by v:

  * The round-3 input is L(round-2 output), so its rows are x1 = Sigma1(o1) and
    x4 = Sigma4(o4) and every other row is 0. The S-box must map each active column
    of it to 00001. DDT[00001][00001] = DDT[01000][00001] = 0 and
    DDT[01001][00001] > 0, so every active column is 01001: Sigma1(o1) = Sigma4(o4) = v,
    i.e. o1 = Sigma1^-1(v), o4 = Sigma4^-1(v).
  * Round 2 has |o1 | o4| active S-boxes, round 3 has |v|, and the round-4 input is
    z = Sigma4(v) in row x4 only, so round 4 has |z|.
  * Round 1 (in front) is free: R1(v) = the exact minimum, over every round-2 input the
    S-box allows for output (0, o1, 0, 0, o4), of the active columns of L^-1(input)
    (ascon_backward.search).
  * Round 5 (behind) is free: R5(z) = the exact minimum over every round-4 output the
    S-box allows for input (0, 0, 0, 0, z) (ascon_extend.best_extension).

  4-round total  T4(v) = R1(v) + |o1 | o4| + |v| + |z|
  5-round total  T5(v) = T4(v) + R5(z)

Lower bounds used for pruning, both exact facts checked by the tests:
  * R1 >= 1.
  * R5(z) >= |Sigma1(z)|: every S-box output for input 00001 has bit x1 set, so the
    round-4 output row x1 is exactly z and the round-5 input row x1 is Sigma1(z).

The search. o1, o4, v, z and Sigma1(z) are all GF(2)-linear in v (Sigma_i is
invertible: Sigma^64 = 1, so Sigma^-1 = Sigma^63). We pick one of the four words
o1, o4, v, z as the ANCHOR and enumerate every anchor of weight k, up to rotation
(all five counts are invariant under rotating every row by the same amount, so the
anchor's lowest set bit is put at bit 0). The other words are updated by one XOR of
a precomputed table per bit. A word passes the cheap filter when

  LB4 = 1 + |o1 | o4| + |v| + |z| <= bound4     or     LB4 + |Sigma1 z| <= bound5,

and only the survivors get the exact R1 and R5. So scan() + exact() decide, for every
family member whose anchor has weight k, whether T4 <= bound4 or T5 <= bound5.

Usage: python ascon_family5.py --anchor z --k 7 [--p1-lo 1 --p1-hi 63] --out OUT_DIR

Pure standard-library Python. Apache-2.0.
"""

import argparse
import importlib.util
import json
import os
import sys
import time

__version__ = "0.1.0"

_HERE = os.path.dirname(os.path.abspath(__file__))


def _load(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(_HERE, name + ".py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


AM = _load("ascon_model")
AB = _load("ascon_backward")
AE = _load("ascon_extend")

if hasattr(int, "bit_count"):
    popcount = int.bit_count
else:  # Python < 3.10
    def popcount(x):
        return bin(x).count("1")

ANCHORS = ("z", "v", "o4", "o1")
CAP_COLUMNS = 22        # largest round-2 active-column count for the exact R1 search
R5_EXACT_MAX = 7        # largest |z| for the exact R5 enumeration (8^7 choices)


def sigma(i, x):
    a, b = AM.ROT[i]
    return x ^ AM.rotr(x, a) ^ AM.rotr(x, b)


def sigma_inv(i, x):
    return AB.inv_row(i, x)


def words_from_v(v):
    """(z, v, o4, o1, s1) for round-3 output row x4 = v."""
    z = sigma(4, v)
    return z, v, sigma_inv(4, v), sigma_inv(1, v), sigma(1, z)


def v_from_anchor(anchor, a):
    if anchor == "z":
        return sigma_inv(4, a)
    if anchor == "v":
        return a
    if anchor == "o4":
        return sigma(4, a)
    if anchor == "o1":
        return sigma(1, a)
    raise ValueError("anchor must be one of %s" % (ANCHORS,))


def family_rounds(v):
    """The fixed middle of the characteristic: (y2, x3, y3, x4)."""
    z, v, o4, o1, _s1 = words_from_v(v)
    y2 = (0, o1, 0, 0, o4)
    x3 = AM.linear(y2)
    y3 = (0, 0, 0, 0, v)
    x4 = AM.linear(y3)
    return y2, x3, y3, x4


def quick_lb(v):
    """(LB4, LB5) of the filter, computed from scratch."""
    z, v, o4, o1, s1 = words_from_v(v)
    lb4 = 1 + popcount(o1 | o4) + popcount(v) + popcount(z)
    return lb4, lb4 + popcount(s1)


def tables(anchor):
    """For p = 0..63: the images (z, v, o4, o1, s1) of the anchor word 1 << p."""
    return [words_from_v(v_from_anchor(anchor, 1 << p)) for p in range(64)]


def scan(anchor, k, p1_lo=1, p1_hi=63, bound4=40, bound5=66):
    """Every anchor word of weight k with bit 0 set and (k >= 2) its second-lowest set
    bit in [p1_lo, p1_hi]. Returns (sorted list of v of the survivors, number of
    anchor words enumerated)."""
    if k < 1 or k > 64:
        raise ValueError("k")
    T = tables(anchor)
    TZ = [t[0] for t in T]
    TV = [t[1] for t in T]
    TO4 = [t[2] for t in T]
    TO1 = [t[3] for t in T]
    TS1 = [t[4] for t in T]
    pc = popcount
    # LB4 >= 1 + |o4| + |v| + |z| and |z|, |Sigma1 z| >= 1 (z != 0): a word with
    # |v| + |o4| > lim fails both parts of the filter.
    lim = max(bound4 - 2, bound5 - 3)
    hits = []
    count = [0]

    def judge(z, v, o4, o1, s1):
        lb4 = 1 + pc(o1 | o4) + pc(v) + pc(z)
        return lb4 <= bound4 or lb4 + pc(s1) <= bound5

    def rec(start, left, z, v, o4, o1, s1):
        if left == 1:
            for p in range(start, 64):
                vv = v ^ TV[p]
                oo4 = o4 ^ TO4[p]
                if pc(vv) + pc(oo4) > lim:
                    continue
                oo1 = o1 ^ TO1[p]
                zz = z ^ TZ[p]
                lb4 = 1 + pc(oo1 | oo4) + pc(vv) + pc(zz)
                if lb4 <= bound4 or lb4 + pc(s1 ^ TS1[p]) <= bound5:
                    hits.append(vv)
            count[0] += 64 - start
            return
        for p in range(start, 65 - left):
            rec(p + 1, left - 1, z ^ TZ[p], v ^ TV[p], o4 ^ TO4[p], o1 ^ TO1[p], s1 ^ TS1[p])

    z0, v0, o40, o10, s10 = T[0]
    if k == 1:
        count[0] = 1
        if judge(z0, v0, o40, o10, s10):
            hits.append(v0)
        return sorted(set(hits)), count[0]
    for p1 in range(max(1, p1_lo), min(p1_hi, 65 - k) + 1):
        z1, v1, o41, o11, s11 = (z0 ^ TZ[p1], v0 ^ TV[p1], o40 ^ TO4[p1],
                                 o10 ^ TO1[p1], s10 ^ TS1[p1])
        if k == 2:
            count[0] += 1
            if judge(z1, v1, o41, o11, s11):
                hits.append(v1)
        else:
            rec(p1 + 1, k - 2, z1, v1, o41, o11, s11)
    return sorted(set(hits)), count[0]


def canonical(v):
    """The smallest rotation of v (all counts are rotation-invariant)."""
    return min(AM.rotr(v, s) for s in range(64))


def exact(v, bound4=40, bound5=66, cap_columns=CAP_COLUMNS):
    """Decide whether the family member v has T4 <= bound4 or T5 <= bound5.

    status: "ok" (T4 > bound4 and T5 > bound5, proven), "candidate" (a round 1 was found
    that makes T4 <= bound4 or T5 <= bound5) or "undecided" (round 2 has more than
    cap_columns active columns, too many for the exact round-1 search)."""
    z, v, o4, o1, s1 = words_from_v(v)
    c, nv, nz = popcount(o1 | o4), popcount(v), popcount(z)
    core = c + nv + nz
    if nz <= R5_EXACT_MAX:
        r5 = AE.best_extension((0, 0, 0, 0, z))["min"]
        r5_exact = True
    else:
        r5 = popcount(s1)
        r5_exact = False
    need = max(bound4 + 1 - core, bound5 + 1 - core - r5)   # R1 >= need proves "ok"
    out = {"v": "%016x" % v, "z": "%016x" % z, "round2": c, "round3": nv, "round4": nz,
           "r5": r5, "r5_exact": r5_exact, "r1_needed": need}
    if need <= 1:
        out["status"] = "ok"
        return out
    if c > cap_columns:
        out["status"] = "undecided"
        return out
    try:
        sols = AB.search((0, o1, 0, 0, o4), need - 1)
    except RuntimeError:
        sols = None
    if sols == []:
        out["status"] = "ok"
    else:
        out["status"] = "candidate"
        if sols:
            out["r1_min_found"] = sols[0][0]
            out["round2_input"] = ["%016x" % w for w in sols[0][1]]
    return out


def run(anchor, k, p1_lo=1, p1_hi=63, bound4=40, bound5=66):
    """scan + exact on one representative per rotation class. Returns a summary dict."""
    t0 = time.time()
    hits, n = scan(anchor, k, p1_lo, p1_hi, bound4, bound5)
    reps = sorted({canonical(v) for v in hits})
    rows = [exact(v, bound4, bound5) for v in reps]
    return {"anchor": anchor, "k": k, "p1_lo": p1_lo, "p1_hi": p1_hi,
            "bound4": bound4, "bound5": bound5, "enumerated": n,
            "survivors": len(hits), "classes": len(reps), "rows": rows,
            "candidates": sum(r["status"] == "candidate" for r in rows),
            "undecided": sum(r["status"] == "undecided" for r in rows),
            "seconds": round(time.time() - t0, 1)}


# ---------------------------------------------------------------- CLI
def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--anchor", choices=ANCHORS, default="z")
    ap.add_argument("--k", type=int, nargs="+", default=[1, 2, 3, 4, 5, 6, 7])
    ap.add_argument("--p1-lo", type=int, default=1)
    ap.add_argument("--p1-hi", type=int, default=63)
    ap.add_argument("--bound4", type=int, default=40)
    ap.add_argument("--bound5", type=int, default=66)
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    os.makedirs(args.out, exist_ok=True)
    res = []
    for k in args.k:
        s = run(args.anchor, k, args.p1_lo, args.p1_hi, args.bound4, args.bound5)
        print(json.dumps({x: s[x] for x in s if x != "rows"}), flush=True)
        res.append(s)
    path = os.path.join(args.out, "family5_%s.json" % args.anchor)
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"version": __version__, "runs": res}, f, indent=1)
    return 0 if not any(s["candidates"] or s["undecided"] for s in res) else 1


if __name__ == "__main__":
    sys.exit(main())
