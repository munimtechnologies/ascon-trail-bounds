# Copyright 2026 Munim, Inc.
# SPDX-License-Identifier: Apache-2.0
# Made with AI agents working in the name of MV2 of Munim, Inc. (mv2@munimtech.com).
"""ascon_backward: exact one-round BACKWARD extension of an Ascon-p differential
characteristic (prepend a round), with no solver.

Fix the S-box-layer OUTPUT difference y of the first round of a characteristic. Its
active columns C are fixed, and so is everything after it. The first round's input x
may be any difference with DDT[x_j][y_j] > 0 in every column j (x_j = 0 outside C). A
prepended round then has output L^-1(x), and its number of active S-boxes is the number
of non-zero columns of L^-1(x) (the S-box is a bijection, and every non-zero output
column has some allowed input). So the cheapest prepended round is

    min over allowed x of  #columns( Sigma_0^-1(x_0) | ... | Sigma_4^-1(x_4) ).

Row i of x lies in the |C|-dimensional space V_C of words supported on C, so for each row
we list every v in V_C (2^|C| words, Gray-code order) with popcount(Sigma_i^-1(v)) <= T,
then combine rows by depth-first search, pruning on the size of the union, and keep the
combinations whose columns are all allowed. This is exact for the threshold T: every
allowed x with at most T active columns in L^-1(x) is found.

Sigma_i(x) = x ^ (x >>> a) ^ (x >>> b) is multiplication by p = 1 + t^a + t^b in
GF(2)[t]/(t^64 + 1). Since p^64 = 1 + t^64a + t^64b = 1, the inverse is
p^63 = p p^2 p^4 p^8 p^16 p^32, and p^(2^k) = 1 + t^(2^k a) + t^(2^k b).

Usage: python ascon_backward.py --data DIR_WITH_TRAIL_JSON --out OUT_DIR [--max-t 30]

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


def popcount(x):
    return bin(x).count("1")


def inv_row(i, x):
    """Sigma_i^-1(x) for row i (0..4)."""
    a, b = AM.ROT[i]
    for k in range(6):
        x = x ^ AM.rotr(x, (a << k) % 64) ^ AM.rotr(x, (b << k) % 64)
    return x


def inv_linear(words):
    return tuple(inv_row(i, w) for i, w in enumerate(words))


def active_columns(words):
    u = words[0] | words[1] | words[2] | words[3] | words[4]
    return [j for j in range(64) if (u >> j) & 1]


def n_active(words):
    return popcount(words[0] | words[1] | words[2] | words[3] | words[4])


def prepend_count(x):
    """Active S-boxes of the round placed before a round with input difference x."""
    return n_active(inv_linear(x))


def allowed_inputs(y):
    """{column: frozenset of inputs a with DDT[a][y_j] > 0} for every active column of y."""
    table = AM.ddt()
    out = {}
    for j in active_columns(y):
        b = AM.column(y, j)
        out[j] = frozenset(a for a in range(1, 32) if table[a][b] > 0)
    return out


def row_candidates(i, cols, allowed, t):
    """Every v in V_C for row i that respects the forced bits of the allowed sets and
    has popcount(Sigma_i^-1(v)) <= t, as a list of (weight, v, Sigma_i^-1(v))."""
    bit = 4 - i
    f1 = f0 = 0
    for j in cols:
        bits = {(a >> bit) & 1 for a in allowed[j]}
        if bits == {1}:
            f1 |= 1 << j
        elif bits == {0}:
            f0 |= 1 << j
    inv = [inv_row(i, 1 << j) for j in cols]
    out = []
    v = p = 0
    for k in range(1 << len(cols)):
        if k:
            idx = (k & -k).bit_length() - 1
            v ^= 1 << cols[idx]
            p ^= inv[idx]
        if (v & f0) == 0 and (v & f1) == f1:
            w = popcount(p)
            if w <= t:
                out.append((w, v, p))
    out.sort()
    return out


def search(y, t, cap=200000):
    """All allowed first-round inputs x for output y whose prepended round has at most t
    active S-boxes. Returns a list of (count, x) sorted by count. Raises RuntimeError if
    more than cap are found."""
    cols = active_columns(y)
    if not cols:
        raise ValueError("no active column")
    allowed = allowed_inputs(y)
    lists = [(len(c), i, c) for i, c in
             ((i, row_candidates(i, cols, allowed, t)) for i in range(5))]
    lists.sort()
    order = [(i, c) for _n, i, c in lists]
    leaves = []
    vs = [0, 0, 0, 0, 0]

    def rec(depth, union):
        if depth == 5:
            for j in cols:
                a = 0
                for r in range(5):
                    a |= ((vs[r] >> j) & 1) << (4 - r)
                if a not in allowed[j]:
                    return
            leaves.append((popcount(union), tuple(vs)))
            if len(leaves) > cap:
                raise RuntimeError("more than %d solutions" % cap)
            return
        row, cands = order[depth]
        for w, v, p in cands:
            if w > t:
                break
            u = union | p
            if popcount(u) <= t:
                vs[row] = v
                rec(depth + 1, u)
        vs[row] = 0

    rec(0, 0)
    leaves.sort()
    return leaves


def minimum(y, max_t=30, cap=200000):
    """(exact minimum, number of minimisers) if the minimum is <= max_t, else (None, 0)."""
    for t in range(1, max_t + 1):
        leaves = search(y, t, cap)
        if leaves:
            m = leaves[0][0]
            return m, sum(1 for c, _x in leaves if c == m)
    return None, 0


# ---------------------------------------------------------------- CLI
def main(argv=None):
    ext = _load("ascon_extend")
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--data", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--max-t", type=int, default=30)
    args = ap.parse_args(argv)
    os.makedirs(args.out, exist_ok=True)
    rows = []
    for root, _dirs, files in os.walk(args.data):
        for name in sorted(files):
            if not name.lower().endswith(".json"):
                continue
            row = {"file": name}
            try:
                with open(os.path.join(root, name), encoding="utf-8") as f:
                    trail = ext.parse_trail_obj(json.load(f))
                row["counts"] = AM.check_trail(trail)
                for r in range(min(2, len(trail))):
                    t0 = time.time()
                    m, n = minimum(tuple(trail[r][1]), args.max_t)
                    row["round%d_output" % (r + 1)] = {
                        "published_prepend_count": prepend_count(tuple(trail[r][0])),
                        "exact_min": m, "n_minimisers": n, "max_t": args.max_t,
                        "seconds": round(time.time() - t0, 1)}
            except Exception as exc:  # report and continue
                row["error"] = "%s: %s" % (type(exc).__name__, exc)
            rows.append(row)
            print(json.dumps(row), flush=True)
    with open(os.path.join(args.out, "summary.json"), "w", encoding="utf-8") as f:
        json.dump({"version": __version__, "rows": rows}, f, indent=1)
    return 0 if rows and not any("error" in r for r in rows) else 1


if __name__ == "__main__":
    sys.exit(main())
