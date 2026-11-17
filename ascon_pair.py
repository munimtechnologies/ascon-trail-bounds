# Copyright 2026 Munim, Inc.
# SPDX-License-Identifier: Apache-2.0
# Made with AI agents working in the name of MV2 of Munim, Inc. (mv2@munimtech.com).
"""ascon_pair: a value-level SAT model that looks for a conforming pair of a given
differential characteristic of the Ascon permutation (NIST SP 800-232).

A characteristic says which differences a pair should have; a conforming (right) pair
is two real 320-bit states whose difference really follows it through the rounds of
the permutation, round constants included. Finding one shows the characteristic is
not empty for the real permutation in that window of rounds.

Model, for R rounds starting at round index `first` of the 12-round permutation:
  A_r = state entering the S-box layer of round r (round constant already added),
  B_r = S(A_r) column by column (CNF of the S-box graph),
  A_{r+1} = L(B_r) xor the next round constant (XOR clauses),
  and for every active column j of round r with (alpha, beta) = (x_r col j, y_r col j):
  A_r col j lies in {v : S(v) xor S(v xor alpha) = beta}.
Inactive columns carry no condition. The second state is the first xor x_0.

Every pair a solver returns is re-checked by ascon_model.trail_from_pair, which runs
the real round function on both states (no formula). UNSAT or a timeout is reported as
such and never as a proof about the characteristic in other windows.

usage: python ascon_pair.py --trail T.json [T2.json ...] --out OUT [--windows all|0,8]
                            [--per-window 600] [--jobs 2]
"""

import argparse
import hashlib
import importlib.util
import json
import math
import multiprocessing as mp
import os
import platform
import sys
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location("ascon_model", os.path.join(_HERE, "ascon_model.py"))
AM = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(AM)

__version__ = "0.1.0"
SOLVER_PREFERENCE = ("cadical195", "cadical153", "glucose4", "minisat22")


# ---------------------------------------------------------------- local CNFs
def _cover_clauses(off_set, nbits):
    """Clauses (over local variables 1..nbits; variable k+1 is bit k) satisfied
    exactly by the points NOT in off_set."""
    if not off_set:
        return ()
    cubes = AM.greedy_cover(AM.prime_implicants(off_set, nbits), off_set)
    clauses = []
    for value, mask in cubes:
        clause = []
        for k in range(nbits):
            if mask >> k & 1:
                continue
            clause.append(-(k + 1) if value >> k & 1 else (k + 1))
        clauses.append(tuple(clause))
    return tuple(clauses)


_GRAPH = None


def sbox_graph_cnf():
    """CNF over 10 local variables satisfied exactly by p = (v << 5) | S(v)."""
    global _GRAPH
    if _GRAPH is None:
        graph = {(v << 5) | AM.sbox5(v) for v in range(32)}
        _GRAPH = _cover_clauses([p for p in range(1024) if p not in graph], 10)
    return _GRAPH


def solution_set(alpha, beta):
    """{v : S(v) xor S(v xor alpha) = beta} (the values that follow alpha -> beta)."""
    return frozenset(v for v in range(32) if AM.sbox5(v) ^ AM.sbox5(v ^ alpha) == beta)


_COND = {}


def condition_cnf(alpha, beta):
    """CNF over 5 local variables (variable k+1 = bit k of v) satisfied exactly by
    the members of solution_set(alpha, beta)."""
    key = (alpha, beta)
    if key not in _COND:
        members = solution_set(alpha, beta)
        if not members:
            raise ValueError("DDT[%d][%d] = 0" % key)
        _COND[key] = _cover_clauses([v for v in range(32) if v not in members], 5)
    return _COND[key]


def xor_parity_clauses(vs, parity):
    """Clauses forcing XOR(vs) == parity."""
    out = []
    n = len(vs)
    for bits in range(1 << n):
        if bin(bits).count("1") % 2 != parity:
            out.append([-v if bits >> k & 1 else v for k, v in enumerate(vs)])
    return out


def is_affine(points):
    """True if the set is an affine subspace of GF(2)^n (closed under u^v^w)."""
    pts = set(points)
    if not pts:
        return False
    lst = sorted(pts)
    for u in lst:
        for v in lst:
            for w in lst:
                if u ^ v ^ w not in pts:
                    return False
    return True


def trail_weight(trail):
    """-log2 of the characteristic's probability under the usual independence
    assumption: sum over active columns of 5 - log2(DDT[alpha][beta])."""
    table = AM.ddt()
    w = 0.0
    for xw, yw in trail:
        for j in range(64):
            a, b = AM.column(xw, j), AM.column(yw, j)
            if a:
                if table[a][b] == 0:
                    raise ValueError("DDT[%d][%d] = 0" % (a, b))
                w += 5 - math.log2(table[a][b])
    return w


# ---------------------------------------------------------------- the pair model
class PairModel:
    def __init__(self, trail, first):
        trail = [(tuple(x), tuple(y)) for x, y in trail]
        AM.check_trail(trail)
        self.rounds = len(trail)
        if not (0 <= first and first + self.rounds <= 12):
            raise ValueError("window %d..%d is outside rounds 0..11" % (first, first + self.rounds - 1))
        self.first = first
        self.trail = trail
        self.nv = 0
        R = self.rounds
        self.A = [[[self._new() for _ in range(64)] for _ in range(5)] for _ in range(R)]
        self.B = [[[self._new() for _ in range(64)] for _ in range(5)] for _ in range(R)]
        self.clauses = []
        self.n_conditions = 0
        self._build()

    def _new(self):
        self.nv += 1
        return self.nv

    def _build(self):
        graph = sbox_graph_cnf()
        R = self.rounds
        for r in range(R):
            for j in range(64):
                for clause in graph:
                    out = []
                    for lit in clause:
                        k = abs(lit) - 1
                        var = self.A[r][4 - (k - 5)][j] if k >= 5 else self.B[r][4 - k][j]
                        out.append(var if lit > 0 else -var)
                    self.clauses.append(out)
        for r in range(R - 1):
            rc = AM.ROUND_CONSTANTS[self.first + r + 1]
            for i, (s1, s2) in enumerate(AM.ROT):
                for j in range(64):
                    c = (rc >> j) & 1 if i == 2 else 0
                    vs = (self.A[r + 1][i][j], self.B[r][i][j],
                          self.B[r][i][(j + s1) % 64], self.B[r][i][(j + s2) % 64])
                    self.clauses.extend(xor_parity_clauses(vs, c))
        for r, (xw, yw) in enumerate(self.trail):
            for j in range(64):
                a, b = AM.column(xw, j), AM.column(yw, j)
                if not a:
                    continue
                self.n_conditions += 1
                for clause in condition_cnf(a, b):
                    self.clauses.append([(1 if lit > 0 else -1) * self.A[r][4 - (abs(lit) - 1)][j]
                                         for lit in clause])

    def states_from(self, state):
        """(A_r, B_r) words for every round when the first state of the pair is `state`."""
        s = tuple(state)
        out = []
        for r in range(self.rounds):
            rc = AM.ROUND_CONSTANTS[self.first + r]
            a = (s[0], s[1], s[2] ^ rc, s[3], s[4])
            b = AM.sbox_layer(a)
            out.append((a, b))
            s = AM.linear(b)
        return out

    def assignment_from_state(self, state):
        val = {}
        for r, (a, b) in enumerate(self.states_from(state)):
            for i in range(5):
                for j in range(64):
                    val[self.A[r][i][j]] = bool(a[i] >> j & 1)
                    val[self.B[r][i][j]] = bool(b[i] >> j & 1)
        return val

    def decode(self, model):
        pos = {lit for lit in model if lit > 0}
        a0 = [sum(1 << j for j in range(64) if self.A[0][i][j] in pos) for i in range(5)]
        a0[2] ^= AM.ROUND_CONSTANTS[self.first]
        return tuple(a0)


def check_pair(state, trail, first):
    """Formula-free check: run both states through the real rounds."""
    trail = [(tuple(x), tuple(y)) for x, y in trail]
    got = AM.trail_from_pair(tuple(state), trail[0][0], len(trail), first)
    return [(tuple(x), tuple(y)) for x, y in got] == trail


# ---------------------------------------------------------------- solving
def parse_trail_obj(obj):
    out = []
    for rd in obj["trail"]:
        xw = tuple(int(h, 16) for h in rd["in"])
        yw = tuple(int(h, 16) for h in rd["out"])
        if len(xw) != 5 or len(yw) != 5:
            raise ValueError("expected 5 words per state")
        out.append((xw, yw))
    if not out:
        raise ValueError("empty trail")
    return out


def pick_solver():
    from pysat.solvers import Solver
    for name in SOLVER_PREFERENCE:
        try:
            s = Solver(name=name)
            s.delete()
            return name
        except Exception:
            continue
    raise RuntimeError("no SAT solver available in pysat")


def _write_json(path, obj):
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(obj, f, indent=1)
    os.replace(tmp, path)


def solve_window(trail, first, solver_name, path):
    """Solve one window in this process; write the record to path."""
    rec = {"first_round": first, "rounds": len(trail)}
    try:
        from pysat.solvers import Solver
        t0 = time.time()
        m = PairModel(trail, first)
        rec.update(n_vars=m.nv, n_clauses=len(m.clauses), n_conditions=m.n_conditions,
                   build_seconds=round(time.time() - t0, 2))
        t1 = time.time()
        with Solver(name=solver_name, bootstrap_with=m.clauses) as s:
            sat = s.solve()
            rec["solve_seconds"] = round(time.time() - t1, 2)
            if sat:
                state = m.decode(s.get_model())
                ok = check_pair(state, trail, first)
                delta = trail[0][0]
                rec.update(status="SAT" if ok else "ERROR",
                           state=["%016x" % w for w in state],
                           other=["%016x" % (w ^ d) for w, d in zip(state, delta)],
                           recheck="real rounds reproduce the characteristic" if ok else
                           "the solver's pair does NOT follow the characteristic (model bug)")
            else:
                rec["status"] = "UNSAT"
    except Exception as e:
        rec.update(status="ERROR", error=repr(e))
    _write_json(path, rec)
    return rec


def run_tasks(tasks, solver_name, work_dir, per_window, jobs):
    """tasks: list of (label, trail, first). Each runs in a forked child, killed after
    per_window seconds (TIMEOUT = inconclusive). Returns {label: record}."""
    ctx = mp.get_context("fork")
    pending = list(tasks)
    running = {}
    results = {}
    while pending or running:
        while pending and len(running) < max(1, jobs):
            label, trail, first = pending.pop(0)
            path = os.path.join(work_dir, "%s.json" % label)
            p = ctx.Process(target=solve_window, args=(trail, first, solver_name, path))
            p.start()
            running[label] = (p, path, time.time(), first, len(trail))
        time.sleep(0.5)
        for label in list(running):
            p, path, t0, first, R = running[label]
            timed_out = time.time() - t0 > per_window
            if p.is_alive() and not timed_out:
                continue
            if p.is_alive():
                p.terminate()
                p.join(10)
                if p.is_alive():
                    p.kill()
                    p.join(5)
            else:
                p.join()
            rec = None
            if os.path.exists(path):
                try:
                    with open(path) as f:
                        rec = json.load(f)
                except Exception:
                    rec = None
            if rec is None:
                rec = ({"status": "TIMEOUT", "limit_seconds": per_window} if timed_out else
                       {"status": "ERROR", "error": "child exited %s without a result" % p.exitcode})
                rec.update(first_round=first, rounds=R)
            rec["wall_seconds"] = round(time.time() - t0, 1)
            results[label] = rec
            del running[label]
    return results


def find_trail_files(data_dir, rounds=0, max_bytes=200000):
    """Sorted paths of *.json files under data_dir that parse as valid characteristics
    (with `rounds` rounds when rounds > 0)."""
    out = []
    for root, _dirs, files in os.walk(data_dir):
        for name in files:
            if not name.lower().endswith(".json"):
                continue
            p = os.path.join(root, name)
            try:
                if os.path.getsize(p) > max_bytes:
                    continue
                with open(p, "rb") as f:
                    trail = parse_trail_obj(json.loads(f.read().decode("utf-8")))
                AM.check_trail(trail)
            except Exception:
                continue
            if rounds <= 0 or len(trail) == rounds:
                out.append(p)
    return sorted(out)


def parse_windows(spec, rounds):
    allw = list(range(0, 12 - rounds + 1))
    if spec == "all":
        return allw
    ws = sorted({int(x) for x in spec.split(",") if x.strip()})
    return [w for w in ws if w in allw]


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--trail", nargs="+", default=[])
    ap.add_argument("--data", help="also use every *.json under DATA with this many rounds")
    ap.add_argument("--rounds", type=int, default=0, help="with --data: only trails with this many rounds")
    ap.add_argument("--out", required=True)
    ap.add_argument("--windows", default="all")
    ap.add_argument("--per-window", type=float, default=600.0)
    ap.add_argument("--jobs", type=int, default=2)
    args = ap.parse_args(argv)
    if args.data:
        args.trail = list(args.trail) + find_trail_files(args.data, args.rounds)
    if not args.trail:
        ap.error("no trail files (use --trail or --data)")
    os.makedirs(os.path.join(args.out, "pairs"), exist_ok=True)
    work = os.path.join(args.out, "work")
    os.makedirs(work, exist_ok=True)
    started = time.time()
    inputs = {}
    tasks = []
    for path in args.trail:
        name = os.path.splitext(os.path.basename(path))[0]
        info = {"file": os.path.basename(path)}
        try:
            with open(path, "rb") as f:
                raw = f.read()
            info["sha256"] = hashlib.sha256(raw).hexdigest()
            trail = parse_trail_obj(json.loads(raw.decode("utf-8")))
            counts = AM.check_trail(trail)
            info.update(rounds=len(trail), round_counts=counts, total_active=sum(counts),
                        weight=trail_weight(trail))
            for w in parse_windows(args.windows, len(trail)):
                tasks.append(("%s_w%02d" % (name, w), trail, w))
        except Exception as e:
            info["error"] = repr(e)
        inputs[name] = info
    solver_name = pick_solver()
    try:
        from importlib.metadata import version
        pysat_version = version("python-sat")
    except Exception:
        pysat_version = "unknown"
    results = run_tasks(tasks, solver_name, work, args.per_window, args.jobs)
    for label, rec in results.items():
        if rec.get("status") == "SAT":
            _write_json(os.path.join(args.out, "pairs", label + ".json"), dict(
                rec, note="Made with AI agents working in the name of MV2 of Munim, Inc. CC BY 4.0."))
    rows = []
    for name, info in inputs.items():
        mine = {k: v for k, v in results.items() if k.startswith(name + "_w")}
        sat = sorted(v["first_round"] for v in mine.values() if v.get("status") == "SAT")
        rows.append({"trail": name, "total_active": info.get("total_active"),
                     "weight": info.get("weight"),
                     "windows_tried": len(mine), "windows_with_pair": sat,
                     "statuses": {k: v.get("status") for k, v in sorted(mine.items())},
                     "verdict": ("pair found and re-checked in windows %s" % sat) if sat else
                     ("no pair found in the tried windows (open; not a proof that none exists)"
                      if mine else info.get("error", "not run"))})
    summary = {"ascon_pair_version": __version__, "ascon_model_version": AM.__version__,
               "solver": solver_name, "pysat_version": pysat_version,
               "python": sys.version.split()[0], "machine": platform.machine(),
               "per_window_seconds": args.per_window, "jobs": args.jobs,
               "wall_minutes_used": round((time.time() - started) / 60, 1),
               "inputs": inputs, "results": results, "rows": rows}
    _write_json(os.path.join(args.out, "pair_summary.json"), summary)
    print(json.dumps(rows, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
