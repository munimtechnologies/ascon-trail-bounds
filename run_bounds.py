# Copyright 2026 Munim, Inc.
# SPDX-License-Identifier: Apache-2.0
# Made with AI agents working in the name of MV2 of Munim, Inc.
"""Run the pre-registered bound checks of PREREG_4R_DIFF_V1.md and grade them.

usage: python run_bounds.py --out OUT_DIR [--minutes 165]

Two lanes run in parallel (one CPU each). Each task (rounds, bound) asks a SAT solver
whether an R-round characteristic with at most `bound` active S-boxes exists.
UNSAT => every R-round characteristic has >= bound + 1 active S-boxes (solver result;
a checked proof certificate is a separate, later step). SAT => the solver's trail is
re-checked by ascon_model.check_trail (no formula involved) and saved.
Tasks still running at the deadline are recorded as TIMEOUT (inconclusive).
"""

import argparse
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

LANES = (
    ((1, 0), (1, 1), (2, 3), (2, 4), (3, 14), (3, 15), (4, 35)),
    ((4, 36),),
)
DIMACS_FOR = {(4, 35), (4, 36)}
SOLVER_PREFERENCE = ("cadical195", "cadical153", "glucose4", "minisat22")


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


def run_task(rounds, bound, solver_name, out_dir):
    from pysat.solvers import Solver
    t0 = time.time()
    model, clauses, nvars = AM.build_cnf(rounds, bound)
    rec = {"rounds": rounds, "bound": bound, "solver": solver_name,
           "n_vars": nvars, "n_clauses": len(clauses),
           "build_seconds": round(time.time() - t0, 2)}
    if (rounds, bound) in DIMACS_FOR:
        path = os.path.join(out_dir, "cnf", "ascon_%dr_le%d.cnf.gz" % (rounds, bound))
        AM.write_dimacs(path, clauses, nvars,
                        "Ascon permutation, %d rounds, differential characteristic with <= %d "
                        "active S-boxes; column 0 of round %d active (rotational symmetry). "
                        "ascon_model %s" % (rounds, bound, AM.symmetry_round(rounds), AM.__version__))
        rec["dimacs"] = os.path.relpath(path, out_dir)
    t1 = time.time()
    with Solver(name=solver_name, bootstrap_with=clauses) as s:
        sat = s.solve()
        rec["solve_seconds"] = round(time.time() - t1, 2)
        try:
            rec["solver_stats"] = s.accum_stats()
        except Exception:
            pass
        if sat:
            trail = model.decode(s.get_model())
            counts = AM.check_trail(trail)          # raises if the trail is invalid
            rec["status"] = "SAT"
            rec["round_counts"] = counts
            rec["total_active"] = sum(counts)
            rec["trail"] = AM.trail_to_hex(trail)
            if sum(counts) > bound:
                rec["status"] = "ERROR"
                rec["error"] = "decoded trail exceeds bound: model/decoder mismatch"
        else:
            rec["status"] = "UNSAT"
    return rec


def lane_worker(tasks, solver_name, out_dir, path):
    for rounds, bound in tasks:
        try:
            rec = run_task(rounds, bound, solver_name, out_dir)
        except Exception as e:     # recorded, never hidden
            rec = {"rounds": rounds, "bound": bound, "status": "ERROR", "error": repr(e)}
        with open(path, "a") as f:
            f.write(json.dumps(rec) + "\n")
            f.flush()
            os.fsync(f.fileno())


def minimum_row(res, rounds, expected):
    lo, hi = res.get((rounds, expected - 1), {}), res.get((rounds, expected), {})
    ok = lo.get("status") == "UNSAT" and hi.get("status") == "SAT" and hi.get("total_active") == expected
    return {"row": "R%d" % rounds,
            "claim": "minimum over %d round(s) is %d active S-boxes (published value)" % (rounds, expected),
            "observed": "<=%d: %s; <=%d: %s%s" % (expected - 1, lo.get("status", "MISSING"), expected,
                                                hi.get("status", "MISSING"),
                                                " (trail with %s)" % hi.get("total_active") if hi.get("status") == "SAT" else ""),
            "verdict": "held" if ok else "FAILED"}


def grade(res):
    rows = [minimum_row(res, 1, 1), minimum_row(res, 2, 4), minimum_row(res, 3, 15)]
    model_ok = all(r["verdict"] == "held" for r in rows)

    r4 = res.get((4, 35), {})
    st = r4.get("status", "TIMEOUT")
    if st == "UNSAT":
        v4 = "held (reproduces the published >= 36)"
    elif st == "SAT":
        v4 = "CONTRADICTS the published bound >= 36: stop, investigate the model before any claim"
    else:
        v4 = "inconclusive (%s)" % st
    rows.append({"row": "R4", "claim": "no 4-round characteristic with <= 35 active S-boxes (Erlacher-Mendel-Eichlseder 2022)",
                 "observed": st, "verdict": v4})

    r5 = res.get((4, 36), {})
    st5 = r5.get("status", "TIMEOUT")
    if st5 == "UNSAT":
        v5 = ("NEW (solver result): no 4-round characteristic with <= 36 active S-boxes, so the minimum is >= 37; "
              "a checked proof certificate is required before it is called proved")
    elif st5 == "SAT":
        tot = r5.get("total_active")
        if tot is not None and tot >= 36:
            v5 = "NEW RECORD TRAIL: a 4-round characteristic with %s active S-boxes (independently re-checked)" % tot
        else:
            v5 = "CONTRADICTS the published bound >= 36: stop, investigate"
    else:
        v5 = "inconclusive (%s): open question unchanged" % st5
    rows.append({"row": "R5", "claim": "the new question: does a 4-round characteristic with <= 36 active S-boxes exist?",
                 "observed": st5, "verdict": v5})
    if not model_ok:
        for r in rows[3:]:
            r["verdict"] = "NOT GRADED: calibration rows R1-R3 failed, model not trusted (%s)" % r["verdict"]
    return {"model_calibrated": model_ok, "rows": rows}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--minutes", type=float, default=165.0)
    args = ap.parse_args(argv)
    os.makedirs(os.path.join(args.out, "cnf"), exist_ok=True)
    path = os.path.join(args.out, "results.jsonl")
    open(path, "w").close()

    started = time.time()
    AM.sbox_cnf()                        # build once, inherited by the forked lanes
    solver_name = pick_solver()
    try:
        from importlib.metadata import version
        pysat_version = version("python-sat")
    except Exception:
        pysat_version = "unknown"

    ctx = mp.get_context("fork")
    procs = [ctx.Process(target=lane_worker, args=(lane, solver_name, args.out, path)) for lane in LANES]
    for p in procs:
        p.start()
    deadline = started + args.minutes * 60
    for p in procs:
        p.join(max(0.0, deadline - time.time()))
    for p in procs:
        if p.is_alive():
            p.terminate()
            p.join(10)

    res = {}
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                rec = json.loads(line)
                res[(rec["rounds"], rec["bound"])] = rec
    for lane in LANES:
        for key in lane:
            if key not in res:
                res[key] = {"rounds": key[0], "bound": key[1], "status": "TIMEOUT"}

    summary = {
        "ascon_model_version": AM.__version__,
        "solver": solver_name,
        "pysat_version": pysat_version,
        "python": sys.version.split()[0],
        "machine": platform.machine(),
        "cpus_used": len(LANES),
        "wall_minutes_budget": args.minutes,
        "wall_minutes_used": round((time.time() - started) / 60, 1),
        "sbox_cnf_clauses": len(AM.sbox_cnf()),
        "tasks": [{k: v for k, v in res[key].items() if k != "trail"} for lane in LANES for key in lane],
        "grade": grade(res),
    }
    with open(os.path.join(args.out, "summary.json"), "w") as f:
        json.dump(summary, f, indent=2)
    trails = {"%dr_le%d" % key: rec["trail"] for key, rec in res.items() if rec.get("trail")}
    with open(os.path.join(args.out, "trails.json"), "w") as f:
        json.dump(trails, f, indent=1)
    print(json.dumps(summary["grade"], indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
