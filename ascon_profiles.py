# Copyright 2026 Munim, Inc.
# SPDX-License-Identifier: Apache-2.0
# Made with AI agents working in the name of MV2 of Munim, Inc. (mv2@munimtech.com).
"""ascon_profiles: configuration-guided SAT search for 4-round differential
characteristics of the Ascon permutation with at most 41 active S-boxes (rec-v2).

Pre-registered in PREREG_REC_V2.md. A "profile" (a0, a1, a2, a3) is a per-round cap on the
number of active S-boxes. For each profile the SAT question is whether some 4-round
characteristic has at most a_r active S-boxes in round r, for every r. Profiles come from
the list of possible 4-round configurations published with Makarim and Rohit (ToSC 2022(3),
github.com/Crypto-TII/ascon_hybrid_milp_smt, Apache-2.0), filtered with their rules.

Their script.py is never executed: its constant lists are read with ast.literal_eval.

Every characteristic a solver returns is re-checked by ascon_model.check_trail (S-box DDT and
linear layer, no formula), so a record never depends on the encoding or the solver. An UNSAT
answer is a solver result for that one profile.

usage: python ascon_profiles.py --data DATA_DIR --out OUT_DIR [--minutes 165] [--per-profile 120]
"""

import argparse
import ast
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

TARGET = (15, 11, 9, 7)          # Otoi (2026), the best published 4-round profile (42)
MAX_SUM = 41                      # we look for <= 41
SYM_ROUND = 1                     # column 0 of round index 1 is active (rotation symmetry)
SOLVER_PREFERENCE = ("cadical195", "cadical153", "glucose4", "minisat22")
CONTROL_SECONDS = 300.0
NEG_CONTROL_SECONDS = 60.0
SEED_NAME = "ascon_4r_42active.json"

_MODEL = {}                       # rounds -> AM.TrailModel, built in the parent before forking


# ---------------------------------------------------------------- MR22 inputs
def parse_mr22_constants(source):
    """Read ZZF, ZZT_21 and LIN from the text of MR22's script.py without running it.
    Returns {"ZZF": set of 3-tuples, "ZZT_21": set of 3-tuples, "LIN": tuple of 64 ints}."""
    found = {}
    try:
        tree = ast.parse(source)
    except SyntaxError:
        tree = None
    if tree is not None:
        for node in tree.body:
            if not isinstance(node, ast.Assign) or len(node.targets) != 1:
                continue
            t = node.targets[0]
            if isinstance(t, ast.Name) and t.id in ("ZZF", "ZZT_21", "LIN"):
                found[t.id] = ast.literal_eval(node.value)
    else:
        for name in ("ZZF", "ZZT_21", "LIN"):
            text = _bracket_literal(source, name)
            if text is not None:
                found[name] = ast.literal_eval(text)
    missing = [k for k in ("ZZF", "ZZT_21", "LIN") if k not in found]
    if missing:
        raise ValueError("missing constants: %s" % ", ".join(missing))
    out = {}
    for k in ("ZZF", "ZZT_21"):
        rows = found[k]
        if not isinstance(rows, (list, tuple)):
            raise ValueError("%s is not a list" % k)
        s = set()
        for row in rows:
            if (not isinstance(row, (list, tuple)) or len(row) != 3
                    or not all(isinstance(v, int) for v in row)):
                raise ValueError("%s has a row that is not 3 ints: %r" % (k, row))
            s.add(tuple(row))
        out[k] = s
    lin = found["LIN"]
    if not isinstance(lin, (list, tuple)) or len(lin) != 64 or not all(isinstance(v, int) for v in lin):
        raise ValueError("LIN is not a list of 64 ints")
    out["LIN"] = tuple(lin)
    return out


def _bracket_literal(source, name):
    """Fallback when the script is not valid Python 3: the text of the first top-level
    `name = [...]` literal, found by matching brackets (never executed)."""
    for line_start in [0] + [i + 1 for i, ch in enumerate(source) if ch == "\n"]:
        line = source[line_start:line_start + len(name) + 64]
        if not line.startswith(name):
            continue
        rest = line[len(name):].lstrip(" \t")
        if not rest.startswith("="):
            continue
        open_at = source.find("[", line_start)
        if open_at < 0:
            return None
        depth = 0
        for k in range(open_at, len(source)):
            ch = source[k]
            if ch == "[":
                depth += 1
            elif ch == "]":
                depth -= 1
                if depth == 0:
                    return source[open_at:k + 1]
        return None
    return None


def parse_configurations(text):
    """Lines of 4 whitespace-separated ints -> (list of 4-tuples, report).
    Unlike MR22's script (range(len(LL) - 1)), the last line is read too; the report says
    what that line was."""
    lines = text.splitlines()
    configs = []
    bad = 0
    for line in lines:
        parts = line.split()
        if not parts:
            continue
        try:
            vals = tuple(int(p) for p in parts)
        except ValueError:
            bad += 1
            continue
        if len(vals) != 4 or not all(1 <= v <= 64 for v in vals):
            bad += 1
            continue
        configs.append(vals)
    nonblank = [l for l in lines if l.strip()]
    report = {"lines": len(lines), "parsed": len(configs), "skipped": bad,
              "distinct": len(set(configs)),
              "last_line": nonblank[-1].strip() if nonblank else "",
              "mr22_loop_skips_last_line": True}
    return configs, report


# ---------------------------------------------------------------- MR22 filters
def f1_not_infeasible(t, zzf):
    """Filter 1: neither 3-round window is a known-infeasible 3-round configuration."""
    return (t[0], t[1], t[2]) not in zzf and (t[1], t[2], t[3]) not in zzf


def f2_small_windows_valid(t, zzt21):
    """Filter 2: every 3-round window with sum <= 21 is a valid 3-round configuration."""
    for w in ((t[0], t[1], t[2]), (t[1], t[2], t[3])):
        if sum(w) <= 21 and w not in zzt21:
            return False
    return True


def f3_branch(t, lin):
    """Filter 3: T[r+1] >= LIN[T[r] - 1] for r = 0, 1, 2."""
    for r in range(3):
        if not 1 <= t[r] <= 64 or t[r + 1] < lin[t[r] - 1]:
            return False
    return True


def f4_heuristic_excluded(t):
    """MR22's step 4, justified only by comments in their script. We do NOT drop these;
    we only flag them. True means MR22 would have dropped the profile."""
    if t[0] == 2:
        return True
    if t[1] == 2 and t[3] <= 9:
        return True
    if (t[0] == 3 and t[2] <= 11) or (t[1] == 3 and t[3] <= 11):
        return True
    return False


def f5_max_rules(t):
    """Filter 5 (MR22's step 5): 2 active S-boxes cannot be followed by >= 23, 3 by >= 33."""
    if t[0] == 3 and t[1] >= 33:
        return False
    if (t[1] == 2 and t[2] >= 23) or (t[1] == 3 and t[2] >= 33):
        return False
    if (t[2] == 2 and t[3] >= 23) or (t[2] == 3 and t[3] >= 33):
        return False
    return True


def apply_filters(configs, consts):
    """Returns (kept list of distinct 4-tuples in input order, counts per stage)."""
    seen = set()
    stage = {"distinct": 0, "after_f1": 0, "after_f2": 0, "after_f3": 0, "after_f5": 0,
             "f4_flagged": 0}
    kept = []
    for t in configs:
        if t in seen:
            continue
        seen.add(t)
        stage["distinct"] += 1
        if not f1_not_infeasible(t, consts["ZZF"]):
            continue
        stage["after_f1"] += 1
        if not f2_small_windows_valid(t, consts["ZZT_21"]):
            continue
        stage["after_f2"] += 1
        if not f3_branch(t, consts["LIN"]):
            continue
        stage["after_f3"] += 1
        if not f5_max_rules(t):
            continue
        stage["after_f5"] += 1
        stage["f4_flagged"] += f4_heuristic_excluded(t)
        kept.append(t)
    return kept, stage


def maximal_profiles(profiles):
    """The profiles not dominated componentwise by another profile in the list.
    An "at most" profile covers every profile below it, so only these need solving.
    Uses a 4-D suffix-OR table (values must be 1..63)."""
    ps = sorted(set(tuple(p) for p in profiles))
    if not ps:
        return []
    d = max(max(p) for p in ps) + 2
    st = (d ** 3, d ** 2, d, 1)
    size = d ** 4
    table = bytearray(size)
    for p in ps:
        table[p[0] * st[0] + p[1] * st[1] + p[2] * st[2] + p[3]] = 1
    # suffix OR along each axis: table[i] = 1 if some profile >= i componentwise
    for k in range(4):
        s = st[k]
        for idx in range(size - 1, -1, -1):
            if (idx // s) % d != d - 1 and table[idx + s]:
                table[idx] = 1
    out = []
    for p in ps:
        base = p[0] * st[0] + p[1] * st[1] + p[2] * st[2] + p[3]
        if not any(table[base + st[k]] for k in range(4)):
            out.append(p)
    return out


def order_profiles(profiles, target=TARGET):
    """Fixed order: L1 distance to the best published profile, then larger sum first,
    then lexicographic."""
    return sorted(profiles, key=lambda p: (sum(abs(a - b) for a, b in zip(p, target)), -sum(p), p))


# ---------------------------------------------------------------- the profile formula
def profile_cnf(model, profile, bound=None, sym_round=SYM_ROUND):
    """Clauses added to model.clauses: column 0 of round sym_round is active; at most
    profile[r] active S-boxes in round r; and, if bound < sum(profile), at most `bound`
    in total. Returns (clauses, number_of_variables)."""
    if len(profile) != model.rounds:
        raise ValueError("profile has %d rounds, model %d" % (len(profile), model.rounds))
    clauses = [[model.act[sym_round][0]]]
    nxt = model.nv + 1
    for r, a in enumerate(profile):
        cl, nxt = AM.seq_counter_atmost(list(model.act[r]), a, nxt)
        clauses.extend(cl)
    if bound is not None and bound < sum(profile):
        cl, nxt = AM.seq_counter_atmost(model.active_vars(), bound, nxt)
        clauses.extend(cl)
    return clauses, nxt - 1


def extend_counter_assignment(val, lits, k, next_var):
    """Intended values of the auxiliary variables of AM.seq_counter_atmost(lits, k, next_var)."""
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


def profile_assignment(model, profile, trail, bound=None):
    """Full assignment (model + profile_cnf variables) for a given trail."""
    val = model.assignment_from_trail(trail)
    nxt = model.nv + 1
    for r, a in enumerate(profile):
        nxt = extend_counter_assignment(val, list(model.act[r]), a, nxt)
    if bound is not None and bound < sum(profile):
        nxt = extend_counter_assignment(val, model.active_vars(), bound, nxt)
    return val, nxt - 1


def rotate_to_symmetry(trail, sym_round=SYM_ROUND):
    """Rotate a trail so that column 0 of round sym_round is active."""
    for j in range(64):
        if AM.column(trail[sym_round][0], j):
            return AM.rotate_trail(trail, j)
    raise ValueError("round %d is all zero" % sym_round)


# ---------------------------------------------------------------- seeds
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


def find_inputs(data_dir):
    """Locate script.py, possible_configurations.txt and the 4-round seed under data_dir."""
    want = {"script": "script.py", "configs": "possible_configurations.txt", "seed": SEED_NAME}
    found = {}
    for root, _dirs, files in os.walk(data_dir):
        for name in sorted(files):
            for key, suffix in want.items():
                if key not in found and name.endswith(suffix):
                    found[key] = os.path.join(root, name)
    return found


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


# ---------------------------------------------------------------- solving
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


def solve_profile_once(rounds, profile, bound, solver_name, path):
    rec = {"rounds": rounds, "profile": list(profile), "bound": bound}
    try:
        from pysat.solvers import Solver
        model = _MODEL[rounds]
        t0 = time.time()
        extra, nv = profile_cnf(model, profile, bound)
        rec["n_vars"] = nv
        rec["n_clauses"] = len(model.clauses) + len(extra)
        rec["build_seconds"] = round(time.time() - t0, 2)
        t1 = time.time()
        with Solver(name=solver_name, bootstrap_with=model.clauses) as s:
            s.append_formula(extra)
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


def solve_with_limit(rounds, profile, bound, solver_name, path, limit):
    """Solve in a forked child, killed after `limit` seconds (TIMEOUT = inconclusive)."""
    ctx = mp.get_context("fork")
    p = ctx.Process(target=solve_profile_once, args=(rounds, tuple(profile), bound, solver_name, path))
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
        rec.update(rounds=rounds, profile=list(profile), bound=bound)
    rec["wall_seconds"] = round(time.time() - t0, 1)
    return rec


def verify_record(rec, max_total):
    """A SAT answer counts only if the returned trail passes check_trail on its own
    and its total is <= max_total. Returns (ok, counts or error)."""
    try:
        trail = parse_trail_obj({"trail": rec["trail"]})
        counts = AM.check_trail(trail)
    except Exception as e:
        return False, "returned trail failed the independent re-check: %r" % (e,)
    if len(counts) != 4:
        return False, "not a 4-round trail"
    if sum(counts) > max_total:
        return False, "returned trail has %d active S-boxes, above %d" % (sum(counts), max_total)
    return True, counts


def _append_jsonl(path, rec):
    with open(path, "a") as f:
        f.write(json.dumps(rec) + "\n")
        f.flush()
        os.fsync(f.fileno())


def lane_main(lane, queue, next_idx, lock, best, out_dir, solver_name, deadline, per_profile):
    """Take profiles from the shared queue in order until time runs out. best is a shared
    int: the current bound for new records (starts at MAX_SUM)."""
    log_path = os.path.join(out_dir, "profiles_lane%d.jsonl" % lane)
    work = os.path.join(out_dir, "work_lane%d" % lane)
    os.makedirs(work, exist_ok=True)
    while True:
        with lock:
            i = next_idx.value
            if i >= len(queue):
                return
            next_idx.value = i + 1
        kind, profile = queue[i]
        limit = CONTROL_SECONDS if kind == "control" else per_profile
        left = deadline - time.time()
        if left < min(limit, 60.0):
            return          # time budget used; the rest of the queue is counted as not reached
        bound = None if kind == "control" else best.value
        rec = solve_with_limit(4, profile, bound, solver_name,
                               os.path.join(work, "p%05d.json" % i), min(limit, left - 10.0))
        rec.update(index=i, kind=kind, lane=lane)
        if rec.get("status") == "SAT" and kind == "search":
            ok, info = verify_record(rec, MAX_SUM)
            if not ok:
                rec["status"] = "ERROR"
                rec["error"] = info
            else:
                total = sum(info)
                rec["record_total"] = total
                name = "ascon_4r_%dactive_%s.json" % (total, "-".join(str(c) for c in info))
                _write_json(os.path.join(out_dir, "records", name), {
                    "R": 4, "active": total, "round_counts": info, "trail": rec["trail"],
                    "found_by": {"profile": list(profile), "bound": bound, "index": i},
                    "checked_by": "ascon_model.check_trail %s (DDT and linear layer, no formula)" % AM.__version__,
                    "pair_checked": False,
                    "note": "Made with AI agents working in the name of MV2 of Munim, Inc. CC BY 4.0."})
                with lock:
                    if total - 1 < best.value:
                        best.value = total - 1
        _append_jsonl(log_path, {k: v for k, v in rec.items() if k != "trail"} | (
            {"trail": rec["trail"]} if rec.get("status") == "SAT" else {}))


# ---------------------------------------------------------------- grading
def _pattern(counts):
    return "-".join(str(c) for c in counts)


def grade(d0, c0, c2, solves, records):
    rows = []
    rows.append({"row": "D0", "claim": "MR22 inputs found and parsed (ZZF, ZZT_21, LIN with 64 entries, configurations)",
                 "observed": d0.get("observed"), "verdict": "held" if d0.get("ok") else "FAILED"})
    rows.append({"row": "C0", "claim": "Otoi's 4-round characteristic re-checks as 15-11-9-7 and satisfies the profile "
                 "formula for 15-11-9-7 but not for 14-11-9-7",
                 "observed": c0.get("observed"), "verdict": "held" if c0.get("ok") else "FAILED"})
    rows.append({"row": "C0b", "claim": "15-11-9-7 is in MR22's configuration list and passes filters 1, 2, 3 and 5",
                 "observed": c0.get("target_in_list"), "verdict": "reported"})
    rows.append({"row": "C2", "claim": "the solver returns UNSAT for 2 rounds capped at 1-2 (the 2-round minimum is 4)",
                 "observed": c2.get("status"), "verdict": "held" if c2.get("status") == "UNSAT" else "FAILED"})
    ctrl = [s for s in solves if s.get("kind") == "control"]
    cst = ctrl[0].get("status") if ctrl else "MISSING"
    rows.append({"row": "C1", "claim": "the solver finds a characteristic within the cap 15-11-9-7 in %d s" % CONTROL_SECONDS,
                 "observed": cst, "verdict": "held" if cst == "SAT" else
                 ("inconclusive (TIMEOUT: profile TIMEOUTs below say little)" if cst == "TIMEOUT" else "FAILED")})
    search = [s for s in solves if s.get("kind") == "search"]
    n = {k: sum(1 for s in search if s.get("status") == k) for k in ("SAT", "UNSAT", "TIMEOUT", "ERROR", "NOT_RUN")}
    if records:
        best = min(records, key=lambda r: r["active"])
        v = ("NEW RECORD: a 4-round characteristic with %d active S-boxes (%s), re-checked without the formula; "
             "no pair checked yet" % (best["active"], _pattern(best["round_counts"])))
    else:
        v = ("no 4-round characteristic with <= %d active S-boxes found in %d profiles tried (open; this says "
             "nothing about whether one exists)" % (MAX_SUM, len(search) - n["NOT_RUN"]))
    rows.append({"row": "Q", "claim": "a 4-round characteristic with at most %d active S-boxes" % MAX_SUM,
                 "observed": n, "verdict": v})
    unsat = [s["profile"] for s in search if s.get("status") == "UNSAT"]
    rows.append({"row": "U", "claim": "profiles whose cap the solver proved empty (solver result, uncertified)",
                 "observed": unsat, "verdict": "reported"})
    return rows


def _read_jsonl(path):
    out = []
    if os.path.exists(path):
        with open(path) as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        out.append(json.loads(line))
                    except ValueError:
                        out.append({"status": "ERROR", "error": "unreadable log line", "kind": "log"})
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--minutes", type=float, default=165.0)
    ap.add_argument("--per-profile", type=float, default=120.0)
    ap.add_argument("--lanes", type=int, default=2)
    args = ap.parse_args(argv)
    started = time.time()
    os.makedirs(os.path.join(args.out, "records"), exist_ok=True)
    summary = {"ascon_profiles_version": __version__, "ascon_model_version": AM.__version__,
               "python": sys.version.split()[0], "machine": platform.machine(),
               "minutes_budget": args.minutes, "per_profile_seconds": args.per_profile,
               "lanes": args.lanes}

    # D0: inputs
    inputs = find_inputs(args.data)
    summary["inputs"] = {k: {"file": os.path.basename(p), "sha256": sha256_file(p)} for k, p in inputs.items()}
    d0 = {"ok": False}
    consts = None
    configs = []
    try:
        with open(inputs["script"], encoding="utf-8", errors="replace") as f:
            consts = parse_mr22_constants(f.read())
        with open(inputs["configs"], encoding="utf-8", errors="replace") as f:
            configs, cfg_report = parse_configurations(f.read())
        summary["config_file"] = cfg_report
        d0 = {"ok": bool(configs), "observed": {"ZZF": len(consts["ZZF"]), "ZZT_21": len(consts["ZZT_21"]),
                                                "LIN": len(consts["LIN"]), "configurations": len(configs)}}
    except Exception as e:
        d0 = {"ok": False, "observed": "ERROR %r" % (e,)}

    # filters, maximal profiles, order
    queue = []
    c0 = {"ok": False}
    if d0["ok"]:
        kept, stages = apply_filters(configs, consts)
        small = [t for t in kept if sum(t) <= MAX_SUM]
        maxi = maximal_profiles(small)
        ordered = order_profiles(maxi)
        stages.update(sum_le_41=len(small), maximal=len(maxi),
                      maximal_f4_flagged=sum(1 for t in maxi if f4_heuristic_excluded(t)),
                      sum_histogram={str(s): sum(1 for t in small if sum(t) == s) for s in range(1, MAX_SUM + 1)
                                     if any(sum(t) == s for t in small)})
        summary["filters"] = stages
        summary["queue_first_40"] = [list(p) for p in ordered[:40]]
        _write_json(os.path.join(args.out, "profiles_ordered.json"), [list(p) for p in ordered])
        tgt = tuple(TARGET)
        c0["target_in_list"] = {"in_file": tgt in set(configs),
                                "passes_f1_f2_f3_f5": tgt in set(kept),
                                "f4_flagged": f4_heuristic_excluded(tgt)}
        queue = [("control", tgt)] + [("search", p) for p in ordered]

    # C0: seed formula check
    model4 = AM.TrailModel(4)
    _MODEL[4] = model4
    try:
        with open(inputs["seed"], "rb") as f:
            raw = f.read()
        seed = parse_trail_obj(json.loads(raw.decode("utf-8")))
        counts = AM.check_trail(seed)
        rot = rotate_to_symmetry(seed)
        val, nv2 = profile_assignment(model4, TARGET, rot)
        ex, nv = profile_cnf(model4, TARGET)
        ok_in = nv == nv2 and AM.clauses_satisfied(model4.clauses, val) and AM.clauses_satisfied(ex, val)
        tight = (14,) + tuple(TARGET[1:])
        val2, _ = profile_assignment(model4, tight, rot)
        ex2, _ = profile_cnf(model4, tight)
        ok_out = not AM.clauses_satisfied(ex2, val2)
        c0.update(ok=tuple(counts) == TARGET and ok_in and ok_out,
                  observed={"counts": _pattern(counts), "satisfies_15_11_9_7": ok_in, "violates_14_11_9_7": ok_out})
    except Exception as e:
        c0.update(ok=False, observed="ERROR %r" % (e,))

    solver_name = pick_solver()
    try:
        from importlib.metadata import version
        pysat_version = version("python-sat")
    except Exception:
        pysat_version = "unknown"
    summary.update(solver=solver_name, pysat_version=pysat_version)

    # C2: negative control on 2 rounds
    _MODEL[2] = AM.TrailModel(2)
    c2 = solve_with_limit(2, (1, 2), None, solver_name, os.path.join(args.out, "c2.json"), NEG_CONTROL_SECONDS)

    # lanes
    deadline = started + args.minutes * 60
    if queue:
        ctx = mp.get_context("fork")
        lock = ctx.Lock()
        next_idx = ctx.Value("i", 0)
        best = ctx.Value("i", MAX_SUM)
        procs = [ctx.Process(target=lane_main, args=(k, queue, next_idx, lock, best, args.out, solver_name,
                                                     deadline, args.per_profile))
                 for k in range(max(1, args.lanes))]
        for p in procs:
            p.start()
        for p in procs:
            p.join(max(0.0, deadline + CONTROL_SECONDS + 60 - time.time()))
        for p in procs:
            if p.is_alive():
                p.terminate()
                p.join(10)

    solves = []
    for k in range(max(1, args.lanes)):
        solves.extend(_read_jsonl(os.path.join(args.out, "profiles_lane%d.jsonl" % k)))
    solves.sort(key=lambda s: s.get("index", 0))
    summary["queue_length"] = len(queue)
    summary["attempted"] = sum(1 for s in solves if s.get("status") != "NOT_RUN")
    summary["not_reached"] = max(0, len(queue) - len(solves))
    records = []
    rdir = os.path.join(args.out, "records")
    summary["records"] = []
    for name in sorted(os.listdir(rdir)):
        if not name.endswith(".json"):
            continue
        try:
            with open(os.path.join(rdir, name)) as f:
                r = json.load(f)
            ok, counts = verify_record(r, MAX_SUM)
        except Exception as e:
            summary["records"].append({"file": name, "error": repr(e)})
            continue
        if ok:
            records.append(r)
            summary["records"].append({"file": name, "active": sum(counts), "round_counts": counts})
        else:
            summary["records"].append({"file": name, "error": counts})
    summary["c0"] = c0
    summary["c2"] = {k: v for k, v in c2.items() if k != "trail"}
    summary["solves"] = [{k: v for k, v in s.items() if k != "trail"} for s in solves]
    summary["wall_minutes_used"] = round((time.time() - started) / 60, 1)
    summary["grade"] = grade(d0, c0, c2, solves, records)
    _write_json(os.path.join(args.out, "summary.json"), summary)
    print(json.dumps(summary["grade"], indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
