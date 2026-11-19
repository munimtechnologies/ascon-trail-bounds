# Copyright 2026 Munim, Inc.
# SPDX-License-Identifier: Apache-2.0
# Made with AI agents working in the name of MV2 of Munim, Inc. (mv2@munimtech.com).
"""ascon_extend: exact one-round extension of an Ascon-p differential characteristic.

The last round of a characteristic has S-box-layer input difference x. Every active
column j (x_j != 0) may output any b with DDT[x_j][b] > 0, and the next round's input
is L(y), which is linear in y. So the fewest active S-boxes the next round can have,
over every output choice of the last round, is found exactly by enumerating the
product of the DDT rows of the active columns (8^7 = 2,097,152 choices for seven
active columns with input 00001). No solver is used.

extend_trail() keeps every earlier round unchanged, replaces the last round's output
by the first minimiser found, and appends one round whose output in each active
column a is S(0) ^ S(a) (always allowed: DDT[a][S(0) ^ S(a)] >= 2). The result is
re-checked with ascon_model.check_trail, which does not use any formula.

Usage: python ascon_extend.py --data DIR_WITH_TRAIL_JSON --out OUT_DIR

Pure standard-library Python. Apache-2.0.
"""

import argparse
import hashlib
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

MAX_CHOICES = 50_000_000


def column_words(j, b):
    """The five words of a state that is zero except column j, which holds b
    (x0 = bit 4 of b ... x4 = bit 0)."""
    return tuple(((b >> (4 - i)) & 1) << j for i in range(5))


def active_columns(words):
    u = words[0] | words[1] | words[2] | words[3] | words[4]
    return [j for j in range(64) if (u >> j) & 1]


def n_active(words):
    return bin(words[0] | words[1] | words[2] | words[3] | words[4]).count("1")


def options(xw):
    """For each active column of xw: (column, [(b, L(column_words(j, b))), ...])."""
    table = AM.ddt()
    out = []
    for j in active_columns(xw):
        a = AM.column(xw, j)
        opts = [(b, AM.linear(column_words(j, b))) for b in range(32) if table[a][b] > 0]
        out.append((j, opts))
    return out


def best_extension(xw, max_choices=MAX_CHOICES):
    """Exact minimum over all DDT-compatible outputs y of xw of the number of active
    S-boxes of L(y). Returns {"min", "n_minimisers", "first_minimiser" (tuple of b per
    active column), "columns", "choices"}."""
    opts = options(xw)
    if not opts:
        raise ValueError("no active column")
    total = 1
    for _j, o in opts:
        total *= len(o)
    if total > max_choices:
        raise ValueError("too many output choices: %d" % total)
    cols = [j for j, _o in opts]
    lists = [o for _j, o in opts]
    n = len(lists)
    state = {"min": 65, "count": 0, "first": None}
    choice = [0] * n
    last = lists[-1]

    def rec(i, w0, w1, w2, w3, w4):
        if i == n - 1:
            for b, (c0, c1, c2, c3, c4) in last:
                k = bin((w0 ^ c0) | (w1 ^ c1) | (w2 ^ c2) | (w3 ^ c3) | (w4 ^ c4)).count("1")
                if k < state["min"]:
                    choice[i] = b
                    state["min"], state["count"], state["first"] = k, 1, tuple(choice)
                elif k == state["min"]:
                    state["count"] += 1
            return
        for b, (c0, c1, c2, c3, c4) in lists[i]:
            choice[i] = b
            rec(i + 1, w0 ^ c0, w1 ^ c1, w2 ^ c2, w3 ^ c3, w4 ^ c4)

    rec(0, 0, 0, 0, 0, 0)
    return {"min": state["min"], "n_minimisers": state["count"],
            "first_minimiser": state["first"], "columns": cols, "choices": total}


def output_from_choice(columns, bs):
    words = [0, 0, 0, 0, 0]
    for j, b in zip(columns, bs):
        for i, w in enumerate(column_words(j, b)):
            words[i] |= w
    return tuple(words)


def next_round_output(xw):
    """A valid output for every active column: b = S(0) ^ S(a)."""
    s0 = AM.sbox5(0)
    cols = active_columns(xw)
    return output_from_choice(cols, [s0 ^ AM.sbox5(AM.column(xw, j)) for j in cols])


def extend_trail(trail):
    """Returns (new_trail, counts, best) with one more round, minimal for this
    trail's last-round input. Raises ValueError if the input trail is invalid."""
    AM.check_trail(trail)
    xw = tuple(trail[-1][0])
    best = best_extension(xw)
    y_new = output_from_choice(best["columns"], best["first_minimiser"])
    x_next = AM.linear(y_new)
    new = [tuple(map(tuple, r)) for r in trail[:-1]] + [(xw, y_new), (x_next, next_round_output(x_next))]
    counts = AM.check_trail(new)
    if counts[-1] != best["min"]:
        raise AssertionError("extension count mismatch")
    return new, counts, best


# ---------------------------------------------------------------- CLI
def parse_trail_obj(obj):
    """{"trail": [{"in": [5 hex words], "out": [...]}, ...]} (or the first list of such
    dicts found at the top level) -> [(xw, yw), ...]."""
    rounds = None
    if isinstance(obj, dict):
        if isinstance(obj.get("trail"), list):
            rounds = obj["trail"]
        else:
            for v in obj.values():
                if isinstance(v, list) and v and isinstance(v[0], dict) and "in" in v[0] and "out" in v[0]:
                    rounds = v
                    break
    elif isinstance(obj, list):
        rounds = obj
    if not rounds:
        raise ValueError("no trail found")
    out = []
    for rd in rounds:
        xw = tuple(int(str(h), 16) for h in rd["in"])
        yw = tuple(int(str(h), 16) for h in rd["out"])
        if len(xw) != 5 or len(yw) != 5:
            raise ValueError("expected 5 words per state")
        out.append((xw, yw))
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--data", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    os.makedirs(args.out, exist_ok=True)
    rows = []
    for root, _dirs, files in os.walk(args.data):
        for name in sorted(files):
            if not name.lower().endswith(".json") or "pair" in name.lower():
                continue
            p = os.path.join(root, name)
            if os.path.getsize(p) > 500000:
                continue
            with open(p, "rb") as f:
                raw = f.read()
            row = {"file": name, "sha256": hashlib.sha256(raw).hexdigest()}
            try:
                trail = parse_trail_obj(json.loads(raw.decode("utf-8")))
                row["counts"] = AM.check_trail(trail)
                t0 = time.time()
                new, counts, best = extend_trail(trail)
                row.update({"valid": True, "extended_counts": counts,
                            "extended_total": sum(counts),
                            "next_round_min": best["min"],
                            "n_minimisers": best["n_minimisers"],
                            "choices": best["choices"],
                            "seconds": round(time.time() - t0, 1)})
                base = os.path.splitext(name)[0]
                with open(os.path.join(args.out, base + "_ext.json"), "w", encoding="utf-8") as f:
                    json.dump({"source_file": name, "source_sha256": row["sha256"],
                               "rounds": len(new), "per_round": counts,
                               "active": sum(counts), "trail": AM.trail_to_hex(new)}, f, indent=1)
            except Exception as exc:
                row.update({"valid": False, "error": "%s: %s" % (type(exc).__name__, exc)})
            rows.append(row)
            print(json.dumps(row), flush=True)
    with open(os.path.join(args.out, "summary.json"), "w", encoding="utf-8") as f:
        json.dump({"version": __version__, "rows": rows}, f, indent=1)
    return 0 if rows and all(r.get("valid") for r in rows) else 1


if __name__ == "__main__":
    sys.exit(main())
