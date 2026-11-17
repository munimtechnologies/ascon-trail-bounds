# Copyright 2026 Munim, Inc.
# SPDX-License-Identifier: Apache-2.0
# Made with AI agents working in the name of MV2 of Munim, Inc. (mv2@munimtech.com).
"""ascon_lns: large-neighbourhood search (LNS) for differential characteristics of the
Ascon permutation with few active S-boxes, seeded from the best published ones.

Pre-registered in PREREG_REC_V1.md. A neighbourhood keeps some rounds close to the
current best characteristic: in each restricted round, at most `extra` columns may be
active outside the columns active in the current best. The other rounds are free. The
SAT question is whether some characteristic in that neighbourhood has at most
best - 1 active S-boxes in total. If one is found, it becomes the new best and the
schedule starts again from the top.

Every characteristic a solver returns is re-checked by ascon_model.check_trail, which
uses the S-box DDT and the linear layer directly, not the formula. So a record found
here does not depend on the encoding being right. UNSAT only closes that one
neighbourhood, and it is a solver result.

usage: python ascon_lns.py --data DATA_DIR --out OUT_DIR [--minutes 160] [--per-solve 300]
"""

import argparse
import hashlib
import importlib.util
import json
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

# Seeds: N. Otoi, github.com/otoinobuo/ascon-trails (MIT), trails/*.json.
SEED_NAMES = {"ascon_4r_42active.json": 4, "ascon_5r_68active.json": 5}
EXPECTED = {4: (15, 11, 9, 7), 5: (15, 11, 9, 7, 26)}

# (restricted rounds, extra columns allowed per restricted round), most restrictive first.
SCHEDULE = {
    4: (
        ((1, 2, 3), 0), ((1, 2, 3), 1), ((2, 3), 0), ((1, 2), 0), ((1, 3), 0),
        ((1, 2, 3), 2), ((2, 3), 1), ((1, 2), 1), ((1, 3), 1),
        ((3,), 0), ((2,), 0), ((1,), 0),
        ((1, 2, 3), 3), ((2, 3), 2), ((1, 2), 2), ((1, 3), 2),
        ((3,), 1), ((2,), 1), ((1,), 1),
        ((2, 3), 3), ((1, 2), 3), ((1, 3), 3),
    ),
    5: (
        ((1, 2, 3), 0), ((1, 2, 3), 1), ((2, 3), 0), ((1, 2), 0), ((1, 3), 0),
        ((1, 2, 3), 2), ((2, 3), 1), ((1, 2), 1), ((1, 3), 1),
        ((2,), 0), ((3,), 0), ((1,), 0),
        ((1, 2, 3), 3), ((2, 3), 2), ((1, 2), 2),
        ((2, 3, 4), 2), ((1, 2, 3, 4), 4),
    ),
}
SOLVER_PREFERENCE = ("cadical195", "cadical153", "glucose4", "minisat22")

_MODELS = {}     # rounds -> AM.TrailModel, built in the parent before forking


# ---------------------------------------------------------------- seeds
def parse_trail_obj(obj):
    """{"trail": [{"in": [5 hex words x0..x4], "out": [...]}, ...]} -> [(xw, yw), ...]."""
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


def find_seeds(data_dir, max_bytes=200000):
    """Find seed characteristics (JSON) anywhere under data_dir. Files with the
    published names are tried first; the first valid trail per round count wins."""
    cands = []
    for root, _dirs, files in os.walk(data_dir):
        for name in files:
            if not name.lower().endswith(".json"):
                continue
            p = os.path.join(root, name)
            try:
                if os.path.getsize(p) > max_bytes:
                    continue
            except OSError:
                continue
            cands.append((0 if name in SEED_NAMES else 1, p))
    found = {}
    for _pri, p in sorted(cands):
        try:
            with open(p, "rb") as f:
                raw = f.read()
            obj = json.loads(raw.decode("utf-8"))
            trail = parse_trail_obj(obj)
        except Exception:
            continue
        r = len(trail)
        if r in EXPECTED and r not in found:
            found[r] = {"path": p, "sha256": hashlib.sha256(raw).hexdigest(),
                        "claimed_active": obj.get("active") if isinstance(obj, dict) else None,
                        "trail": trail}
    return found


def seed_active(trail):
    """Per round, the set of columns whose S-box is active."""
    return [frozenset(j for j in range(64) if AM.column(xw, j)) for xw, _yw in trail]


# ---------------------------------------------------------------- the neighbourhood formula
def neighbourhood_cnf(model, seed, restrict, extra, bound):
    """Clauses added to model.clauses: (1) in every restricted round at most `extra`
    columns are active outside seed's active columns; (2) round 0 is not all zero
    (then no round is, as the S-box and the linear layer are bijective); (3) at most
    `bound` active S-boxes in total. Returns (clauses, number_of_variables)."""
    if len(seed) != model.rounds:
        raise ValueError("seed has %d rounds, model %d" % (len(seed), model.rounds))
    act = seed_active(seed)
    clauses = []
    nxt = model.nv + 1
    for r in restrict:
        outside = [model.act[r][j] for j in range(64) if j not in act[r]]
        if extra <= 0:
            clauses.extend([-v] for v in outside)
        else:
            cl, nxt = AM.seq_counter_atmost(outside, extra, nxt)
            clauses.extend(cl)
    clauses.append(list(model.act[0]))
    cl, nxt = AM.seq_counter_atmost(model.active_vars(), bound, nxt)
    clauses.extend(cl)
    return clauses, nxt - 1


def extend_counter_assignment(val, lits, k, next_var):
    """Give the auxiliary variables of seq_counter_atmost(lits, k, next_var) their
    intended values (s[i][j] = at least j of lits[0..i] are true). Returns next var."""
    n = len(lits)
    if k >= n or k <= 0:
        return next_var
    running = 0
    for i in range(n - 1):
        running += bool(val[lits[i]])
        for j in range(1, k + 1):
            val[next_var] = running >= j
            next_var += 1
    return next_var


def neighbourhood_assignment(model, seed, restrict, extra, bound, trail):
    """Full assignment (model + neighbourhood_cnf variables) for a given trail."""
    val = model.assignment_from_trail(trail)
    act = seed_active(seed)
    nxt = model.nv + 1
    for r in restrict:
        outside = [model.act[r][j] for j in range(64) if j not in act[r]]
        if extra > 0:
            nxt = extend_counter_assignment(val, outside, extra, nxt)
    nxt = extend_counter_assignment(val, model.active_vars(), bound, nxt)
    return val, nxt - 1


# ---------------------------------------------------------------- the search loop
def lns_loop(seed, schedule, solve_fn, time_left, log, on_record=None, min_seconds=20.0):
    """Walk the schedule; on a verified improvement restart it around the new best.
    solve_fn(best, restrict, extra, bound, seconds_left) -> record dict with "status"
    and, when SAT, "trail" (hex form). Returns (best, best_counts, steps)."""
    best = seed
    best_counts = AM.check_trail(seed)
    best_total = sum(best_counts)
    i = 0
    steps = 0
    while i < len(schedule):
        left = time_left()
        if left < min_seconds:
            break
        restrict, extra = schedule[i]
        bound = best_total - 1
        rec = dict(solve_fn(best, restrict, extra, bound, left))
        rec.update({"restrict": list(restrict), "extra": extra, "bound": bound,
                    "best_before": best_total, "step": steps})
        steps += 1
        improved = False
        if rec.get("status") == "SAT":
            try:
                trail = parse_trail_obj({"trail": rec["trail"]})
                counts = AM.check_trail(trail)
            except Exception as e:
                rec["status"] = "ERROR"
                rec["error"] = "returned trail failed the independent re-check: %r" % (e,)
            else:
                if sum(counts) <= bound:
                    best, best_counts, best_total = trail, counts, sum(counts)
                    improved = True
                    rec["improved_to"] = best_total
                    rec["round_counts"] = counts
                    if on_record is not None:
                        on_record(best, best_counts, rec)
                else:
                    rec["status"] = "ERROR"
                    rec["error"] = "returned trail has %d active S-boxes, above the bound" % sum(counts)
        log(rec)
        i = 0 if improved else i + 1
    return best, best_counts, steps


# ---------------------------------------------------------------- solving (child processes)
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


def solve_once(rounds, seed, restrict, extra, bound, solver_name, path):
    """Solve one neighbourhood in this process and write the record to path."""
    rec = {"rounds": rounds}
    try:
        from pysat.solvers import Solver
        model = _MODELS[rounds]
        t0 = time.time()
        extra_cl, nv = neighbourhood_cnf(model, seed, restrict, extra, bound)
        rec["n_vars"] = nv
        rec["n_clauses"] = len(model.clauses) + len(extra_cl)
        rec["build_seconds"] = round(time.time() - t0, 2)
        t1 = time.time()
        with Solver(name=solver_name, bootstrap_with=model.clauses) as s:
            s.append_formula(extra_cl)
            sat = s.solve()
            rec["solve_seconds"] = round(time.time() - t1, 2)
            if sat:
                trail = model.decode(s.get_model())
                counts = AM.check_trail(trail)
                rec.update(status="SAT", round_counts=counts, total_active=sum(counts),
                           trail=AM.trail_to_hex(trail))
            else:
                rec["status"] = "UNSAT"
    except Exception as e:
        rec.update(status="ERROR", error=repr(e))
    _write_json(path, rec)
    return rec


def make_solver_fn(rounds, solver_name, work_dir, per_solve):
    """solve_fn for lns_loop: each neighbourhood is solved in a forked child that is
    killed after per_solve seconds (TIMEOUT = inconclusive)."""
    ctx = mp.get_context("fork")
    counter = [0]

    def solve(seed, restrict, extra, bound, left):
        counter[0] += 1
        path = os.path.join(work_dir, "solve_%dr_%04d.json" % (rounds, counter[0]))
        limit = max(1.0, min(per_solve, left - 10.0))
        p = ctx.Process(target=solve_once, args=(rounds, seed, tuple(restrict), extra, bound, solver_name, path))
        t0 = time.time()
        p.start()
        p.join(limit)
        timed_out = p.is_alive()
        if timed_out:
            p.terminate()
            p.join(10)
            if p.is_alive():
                p.kill()
                p.join(5)
        rec = None
        if os.path.exists(path):
            try:
                with open(path) as f:
                    rec = json.load(f)
            except Exception:
                rec = None
        if rec is None:
            rec = ({"status": "TIMEOUT", "limit_seconds": round(limit, 1)} if timed_out else
                   {"status": "ERROR", "error": "child exited %s without a result" % p.exitcode})
        rec["wall_seconds"] = round(time.time() - t0, 1)
        return rec
    return solve


def _append_jsonl(path, rec):
    with open(path, "a") as f:
        f.write(json.dumps(rec) + "\n")
        f.flush()
        os.fsync(f.fileno())


def lane_main(rounds, seed, out_dir, solver_name, deadline, per_solve):
    log_path = os.path.join(out_dir, "lns_%dr.jsonl" % rounds)
    state_path = os.path.join(out_dir, "lane_%dr.json" % rounds)
    work = os.path.join(out_dir, "work_%dr" % rounds)
    os.makedirs(work, exist_ok=True)
    state = {"rounds": rounds, "seed_total": None, "sanity_formula": None, "sanity_status": None,
             "best_total": None, "best_counts": None, "steps": 0, "stopped": None}

    def save():
        _write_json(state_path, state)

    try:
        model = _MODELS[rounds]
        counts = AM.check_trail(seed)
        total = sum(counts)
        state.update(seed_total=total, best_total=total, best_counts=counts)
        everything = tuple(range(rounds))
        ex, nv = neighbourhood_cnf(model, seed, everything, 0, total)
        val, nv2 = neighbourhood_assignment(model, seed, everything, 0, total, seed)
        state["sanity_formula"] = bool(nv == nv2 and AM.clauses_satisfied(model.clauses, val)
                                       and AM.clauses_satisfied(ex, val))
        save()
        if not state["sanity_formula"]:
            state["stopped"] = "the seed does not satisfy its own neighbourhood formula"
            save()
            return
        solve = make_solver_fn(rounds, solver_name, work, per_solve)

        def left():
            return deadline - time.time()

        rec = solve(seed, everything, 0, total, left())
        rec.update(kind="sanity", restrict=list(everything), extra=0, bound=total)
        _append_jsonl(log_path, rec)
        state["sanity_status"] = rec.get("status")
        save()
        if rec.get("status") != "SAT":
            state["stopped"] = "sanity solve did not return SAT"
            save()
            return

        def on_record(trail, cnts, r):
            name = "ascon_%dr_%dactive.json" % (rounds, sum(cnts))
            _write_json(os.path.join(out_dir, "records", name), {
                "R": rounds, "active": sum(cnts), "round_counts": cnts,
                "trail": AM.trail_to_hex(trail),
                "found_by": {"restrict": r.get("restrict"), "extra": r.get("extra"),
                             "bound": r.get("bound"), "step": r.get("step")},
                "checked_by": "ascon_model.check_trail %s (DDT and linear layer, no formula)" % AM.__version__,
                "note": "Made with AI agents working in the name of MV2 of Munim, Inc. CC BY 4.0."})
            state.update(best_total=sum(cnts), best_counts=cnts)
            save()

        def log(r):
            r = dict(r)
            r["kind"] = "lns"
            _append_jsonl(log_path, r)
            state["steps"] += 1
            save()

        lns_loop(seed, SCHEDULE[rounds], solve, left, log, on_record)
        state["stopped"] = "schedule finished or time budget used"
        save()
    except Exception as e:
        state["stopped"] = "ERROR %r" % (e,)
        save()


# ---------------------------------------------------------------- grading
def _pattern(counts):
    return "-".join(str(c) for c in counts)


def grade(seed_checks, lanes):
    rows = []
    for r, expected in sorted(EXPECTED.items()):
        sc = seed_checks.get(r) or {}
        obs = sc.get("counts")
        rows.append({"row": "S0-%dr" % r,
                     "claim": "the published %d-round characteristic re-checks as %s (total %d)" % (r, _pattern(expected), sum(expected)),
                     "observed": _pattern(obs) if obs else sc.get("error", "MISSING"),
                     "verdict": "held" if obs is not None and tuple(obs) == expected else "FAILED"})
        ln = lanes.get(r) or {}
        st = ln.get("sanity_status")
        rows.append({"row": "S1-%dr" % r,
                     "claim": "the seed satisfies its own neighbourhood formula and the solver finds it again",
                     "observed": "formula %s, solver %s" % (ln.get("sanity_formula"), st or "MISSING"),
                     "verdict": "held" if ln.get("sanity_formula") is True and st == "SAT" else "FAILED"})
        best = ln.get("best_total")
        if best is not None and best < sum(expected):
            v = ("NEW RECORD: a %d-round characteristic with %d active S-boxes (%s), re-checked without the formula"
                 % (r, best, _pattern(ln.get("best_counts") or [])))
        else:
            v = ("no characteristic with fewer than %d active S-boxes found in the searched neighbourhoods "
                 "(open; this says nothing about whether one exists)" % sum(expected))
        rows.append({"row": "Q-%dr" % r,
                     "claim": "LNS finds a %d-round characteristic with at most %d active S-boxes" % (r, sum(expected) - 1),
                     "observed": best, "verdict": v})
    return rows


def _read_jsonl(path):
    out = []
    if os.path.exists(path):
        with open(path) as f:
            for line in f:
                line = line.strip()
                if line:
                    out.append(json.loads(line))
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--minutes", type=float, default=160.0)
    ap.add_argument("--per-solve", type=float, default=300.0)
    args = ap.parse_args(argv)
    started = time.time()
    os.makedirs(os.path.join(args.out, "records"), exist_ok=True)

    seeds = find_seeds(args.data)
    seed_checks = {}
    for r in sorted(EXPECTED):
        if r not in seeds:
            seed_checks[r] = {"error": "seed file not found under --data"}
            continue
        s = seeds[r]
        rec = {"file": os.path.basename(s["path"]), "sha256": s["sha256"], "claimed_active": s["claimed_active"]}
        try:
            cnts = AM.check_trail(s["trail"])
            rec.update(counts=cnts, total=sum(cnts))
        except Exception as e:
            rec["error"] = "independent re-check failed: %r" % (e,)
        seed_checks[r] = rec

    solver_name = pick_solver()
    try:
        from importlib.metadata import version
        pysat_version = version("python-sat")
    except Exception:
        pysat_version = "unknown"

    runnable = [r for r in sorted(EXPECTED)
                if seed_checks[r].get("counts") is not None and tuple(seed_checks[r]["counts"]) == EXPECTED[r]]
    for r in runnable:
        _MODELS[r] = AM.TrailModel(r)

    deadline = started + args.minutes * 60
    ctx = mp.get_context("fork")
    procs = [ctx.Process(target=lane_main, args=(r, seeds[r]["trail"], args.out, solver_name, deadline, args.per_solve))
             for r in runnable]
    for p in procs:
        p.start()
    for p in procs:
        p.join(max(0.0, deadline + 60 - time.time()))
    for p in procs:
        if p.is_alive():
            p.terminate()
            p.join(10)

    lanes = {}
    for r in runnable:
        path = os.path.join(args.out, "lane_%dr.json" % r)
        if os.path.exists(path):
            with open(path) as f:
                lanes[r] = json.load(f)
    solves = {}
    for r in runnable:
        solves[r] = [{k: v for k, v in rec.items() if k != "trail"}
                     for rec in _read_jsonl(os.path.join(args.out, "lns_%dr.jsonl" % r))]

    summary = {
        "ascon_lns_version": __version__,
        "ascon_model_version": AM.__version__,
        "solver": solver_name,
        "pysat_version": pysat_version,
        "python": sys.version.split()[0],
        "machine": platform.machine(),
        "cpus_used": len(runnable),
        "wall_minutes_budget": args.minutes,
        "per_solve_seconds": args.per_solve,
        "wall_minutes_used": round((time.time() - started) / 60, 1),
        "seed_checks": {str(k): v for k, v in seed_checks.items()},
        "lanes": {str(k): v for k, v in lanes.items()},
        "solves": {str(k): v for k, v in solves.items()},
        "records": sorted(os.listdir(os.path.join(args.out, "records"))),
        "grade": grade(seed_checks, lanes),
    }
    _write_json(os.path.join(args.out, "summary.json"), summary)
    print(json.dumps(summary["grade"], indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
