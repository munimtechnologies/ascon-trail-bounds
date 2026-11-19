# Copyright 2026 Munim, Inc.
# SPDX-License-Identifier: Apache-2.0
# Made with AI agents working in the name of MV2 of Munim, Inc.
"""Tests for ascon_profiles (rec-v2): reading MR22's constants without running their script,
their configuration filters (checked against a line-by-line transcription of their control
flow), the dominance reduction, the per-round profile formula (it must accept real trails at
their own counts and reject them one below), record verification and grading."""

import hashlib
import importlib.util
import itertools
import json
import os
import random
import shutil
import tempfile
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))


def _load(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(_HERE, name + ".py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


AM = _load("ascon_model")
AP = _load("ascon_profiles")

try:
    import pysat.solvers  # noqa: F401
    HAVE_PYSAT = True
except Exception:
    HAVE_PYSAT = False

# A fixture in the syntax of MR22's script.py. The top-level raise proves it is never run.
FIXTURE_SCRIPT = '''
raise SystemExit("this script must never be executed")
in_file = 'possible_configurations.txt'
# 3-round invfeasible configurations
ZZF = [[1, 4, 10], [1, 5, 9], [24, 3, 3]]
ZZT_21 = [[2, 4, 10], [2, 4, 11],
          [3, 6, 9], [5, 5, 5],
          [10, 2, 9]]
LIN = [3, 4, 5, 6, 7, 8, 9, 10,
       2, 2, 2, 2, 2, 2, 2, 2,
       2, 2, 2, 2, 2, 2, 2, 2,
       2, 2, 2, 2, 2, 2, 2, 2,
       2, 2, 2, 2, 2, 2, 2, 2,
       2, 2, 2, 2, 2, 2, 2, 2,
       2, 2, 2, 2, 2, 2, 2, 2,
       2, 2, 2, 2, 2, 2, 2, 2]
ZZ1 = []
for r in range(10):
    ZZ1.append(r)
print(len(ZZ1))
'''


def real_trail(rounds, seed, kind="col"):
    rnd = random.Random(seed)
    state = tuple(rnd.getrandbits(64) for _ in range(5))
    if kind == "col":
        j = rnd.randrange(64)
        col = rnd.randrange(1, 32)
        delta = tuple(((col >> (4 - i)) & 1) << j for i in range(5))
    else:
        delta = tuple(rnd.getrandbits(64) for _ in range(5))
    return AM.trail_from_pair(state, delta, rounds, rnd.randrange(12))


def mr22_reference(T, ZZF, ZZT_21, LIN):
    """Line-by-line transcription of MR22 script.py steps 1-3 and 5 (lists, not sets)."""
    L = list(T)
    if not ([L[0], L[1], L[2]] not in ZZF and [L[1], L[2], L[3]] not in ZZF):
        return False
    ok2 = False
    if T[0] + T[1] + T[2] <= 21 and T[1] + T[2] + T[3] <= 21:
        if [T[0], T[1], T[2]] in ZZT_21 and [T[1], T[2], T[3]] in ZZT_21:
            ok2 = True
    elif T[0] + T[1] + T[2] <= 21 and T[1] + T[2] + T[3] >= 22:
        if [T[0], T[1], T[2]] in ZZT_21:
            ok2 = True
    elif T[0] + T[1] + T[2] >= 22 and T[1] + T[2] + T[3] <= 21:
        if [T[1], T[2], T[3]] in ZZT_21:
            ok2 = True
    elif T[0] + T[1] + T[2] >= 22 and T[1] + T[2] + T[3] >= 22:
        ok2 = True
    if not ok2:
        return False
    if not (T[1] >= LIN[T[0] - 1] and T[2] >= LIN[T[1] - 1] and T[3] >= LIN[T[2] - 1]):
        return False
    if T[0] == 3 and T[1] >= 33:
        return False
    elif (T[1] == 2 and T[2] >= 23) or (T[1] == 3 and T[2] >= 33):
        return False
    elif (T[2] == 2 and T[3] >= 23) or (T[2] == 3 and T[3] >= 33):
        return False
    return True


def mr22_step4_drops(T):
    if T[0] == 2:
        return True
    elif T[1] == 2 and T[3] <= 9:
        return True
    elif (T[0] == 3 and T[2] <= 11) or (T[1] == 3 and T[3] <= 11):
        return True
    return False


class TestModelCopy(unittest.TestCase):
    """The job runs on a copy of ascon_model.py; check the parts this search relies on."""

    def test_sbox_matches_spec(self):
        self.assertEqual(tuple(AM.sbox5(v) for v in range(32)), AM.SBOX_SPEC)

    def test_sbox_cnf_matches_ddt(self):
        table = AM.ddt()
        for a in range(32):
            for b in range(32):
                self.assertEqual(AM.eval_local_sbox_cnf(a, b), table[a][b] > 0, (a, b))

    def test_real_trails_satisfy_model(self):
        m = AM.TrailModel(3)
        for seed in range(3):
            t = real_trail(3, 100 + seed, "dense")
            self.assertTrue(AM.clauses_satisfied(m.clauses, m.assignment_from_trail(t)))


class TestParsing(unittest.TestCase):
    def test_constants_read_without_running(self):
        c = AP.parse_mr22_constants(FIXTURE_SCRIPT)
        self.assertEqual(c["ZZF"], {(1, 4, 10), (1, 5, 9), (24, 3, 3)})
        self.assertIn((10, 2, 9), c["ZZT_21"])
        self.assertEqual(len(c["ZZT_21"]), 5)
        self.assertEqual(len(c["LIN"]), 64)
        self.assertEqual(c["LIN"][:3], (3, 4, 5))

    def test_missing_or_bad_constants(self):
        with self.assertRaises(ValueError):
            AP.parse_mr22_constants("ZZF = [[1, 2, 3]]\nZZT_21 = []\n")
        with self.assertRaises(ValueError):
            AP.parse_mr22_constants("ZZF = [[1, 2, 3]]\nZZT_21 = []\nLIN = [1, 2]\n")
        lin64 = "LIN = [" + ", ".join(["1"] * 64) + "]\n"
        self.assertEqual(len(AP.parse_mr22_constants("ZZF = [[1, 2, 3]]\nZZT_21 = []\n" + lin64)["LIN"]), 64)
        with self.assertRaises(ValueError):
            AP.parse_mr22_constants("ZZF = [[1, 2]]\nZZT_21 = []\n" + lin64)

    def test_python2_script_fallback(self):
        src = FIXTURE_SCRIPT.replace("print(len(ZZ1))", "print len(ZZ1)")
        with self.assertRaises(SyntaxError):
            compile(src, "s", "exec")
        self.assertEqual(AP.parse_mr22_constants(src), AP.parse_mr22_constants(FIXTURE_SCRIPT))

    def test_non_literal_rejected(self):
        with self.assertRaises(ValueError):
            AP.parse_mr22_constants("ZZF = []\nZZT_21 = []\nLIN = [1] * 64\n")

    def test_configurations(self):
        text = "2 4 36 2\n2 34 4 2\n\n8 6 x 8\n1 2 3\n0 5 5 5\n15 11 9 7\n9 9 10 12"
        configs, rep = AP.parse_configurations(text)
        self.assertEqual(configs, [(2, 4, 36, 2), (2, 34, 4, 2), (15, 11, 9, 7), (9, 9, 10, 12)])
        self.assertEqual(rep["skipped"], 3)
        self.assertEqual(rep["last_line"], "9 9 10 12")
        self.assertEqual(rep["parsed"], 4)


class TestFilters(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.c = AP.parse_mr22_constants(FIXTURE_SCRIPT)
        cls.lists = {"ZZF": [list(t) for t in cls.c["ZZF"]], "ZZT_21": [list(t) for t in cls.c["ZZT_21"]],
                     "LIN": list(cls.c["LIN"])}

    def _ours(self, t):
        return (AP.f1_not_infeasible(t, self.c["ZZF"]) and AP.f2_small_windows_valid(t, self.c["ZZT_21"])
                and AP.f3_branch(t, self.c["LIN"]) and AP.f5_max_rules(t))

    def test_matches_transcription_random(self):
        rnd = random.Random(7)
        pts = [tuple(rnd.randint(1, 40) for _ in range(4)) for _ in range(4000)]
        pts += [(1, 4, 10, 5), (7, 1, 5, 9), (2, 4, 10, 30), (30, 2, 4, 11), (5, 5, 5, 5), (2, 4, 10, 2),
                (3, 33, 9, 9), (9, 2, 23, 9), (9, 9, 3, 33), (2, 4, 11, 9), (3, 6, 9, 3)]
        for t in pts:
            self.assertEqual(self._ours(t), mr22_reference(t, self.lists["ZZF"], self.lists["ZZT_21"],
                                                           self.lists["LIN"]), t)
            self.assertEqual(AP.f4_heuristic_excluded(t), mr22_step4_drops(t), t)

    def test_apply_filters_counts(self):
        configs = [(5, 5, 5, 5), (5, 5, 5, 5), (1, 4, 10, 5), (30, 30, 30, 30), (3, 33, 9, 9)]
        kept, st = AP.apply_filters(configs, self.c)
        self.assertEqual(st["distinct"], 4)
        self.assertEqual(st["after_f1"], 3)
        self.assertIn((30, 30, 30, 30), kept)
        self.assertNotIn((1, 4, 10, 5), kept)
        self.assertNotIn((3, 33, 9, 9), kept)


class TestMaximal(unittest.TestCase):
    def _brute(self, ps):
        ps = set(ps)
        return sorted(p for p in ps if not any(q != p and all(a >= b for a, b in zip(q, p)) for q in ps))

    def test_against_brute_force(self):
        rnd = random.Random(3)
        for trial in range(30):
            ps = [tuple(rnd.randint(1, 9) for _ in range(4)) for _ in range(rnd.randint(1, 60))]
            self.assertEqual(AP.maximal_profiles(ps), self._brute(ps), trial)

    def test_chain_and_antichain(self):
        self.assertEqual(AP.maximal_profiles([(1, 1, 1, 1), (2, 1, 1, 1), (2, 2, 2, 2)]), [(2, 2, 2, 2)])
        anti = [(3, 1, 1, 1), (1, 3, 1, 1), (1, 1, 3, 1), (1, 1, 1, 3)]
        self.assertEqual(AP.maximal_profiles(anti), sorted(anti))
        self.assertEqual(AP.maximal_profiles([]), [])

    def test_order(self):
        ps = [(10, 10, 10, 10), (15, 11, 9, 6), (14, 11, 9, 7), (15, 10, 9, 6)]
        out = AP.order_profiles(ps)
        self.assertEqual(out[:2], [(14, 11, 9, 7), (15, 11, 9, 6)])
        self.assertEqual(out[2], (15, 10, 9, 6))
        self.assertEqual(out[-1], (10, 10, 10, 10))


class TestProfileFormula(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m4 = AM.TrailModel(4)

    def test_rotation(self):
        t = real_trail(4, 41, "dense")
        r = AP.rotate_to_symmetry(t)
        self.assertNotEqual(AM.column(r[1][0], 0), 0)
        self.assertEqual(AM.check_trail(r), AM.check_trail(t))

    def test_accepts_own_counts_rejects_one_below(self):
        for seed, kind in ((51, "col"), (52, "col"), (53, "dense")):
            t = AP.rotate_to_symmetry(real_trail(4, seed, kind))
            counts = tuple(AM.check_trail(t))
            ex, nv = AP.profile_cnf(self.m4, counts)
            val, nv2 = AP.profile_assignment(self.m4, counts, t)
            self.assertEqual(nv, nv2)
            self.assertTrue(AM.clauses_satisfied(self.m4.clauses, val))
            self.assertTrue(AM.clauses_satisfied(ex, val), (seed, counts))
            looser = tuple(min(64, c + 2) for c in counts)
            ex, _ = AP.profile_cnf(self.m4, looser)
            val, _ = AP.profile_assignment(self.m4, looser, t)
            self.assertTrue(AM.clauses_satisfied(ex, val))
            for r in range(4):
                tight = tuple(c - 1 if q == r else c for q, c in enumerate(counts))
                ex, _ = AP.profile_cnf(self.m4, tight)
                val, _ = AP.profile_assignment(self.m4, tight, t)
                self.assertFalse(AM.clauses_satisfied(ex, val), (seed, r))

    def test_total_bound(self):
        t = AP.rotate_to_symmetry(real_trail(4, 61, "col"))
        counts = tuple(AM.check_trail(t))
        loose = tuple(min(64, c + 3) for c in counts)
        total = sum(counts)
        ex, nv = AP.profile_cnf(self.m4, loose, total)
        val, nv2 = AP.profile_assignment(self.m4, loose, t, total)
        self.assertEqual(nv, nv2)
        self.assertTrue(AM.clauses_satisfied(ex, val))
        ex, _ = AP.profile_cnf(self.m4, loose, total - 1)
        val, _ = AP.profile_assignment(self.m4, loose, t, total - 1)
        self.assertFalse(AM.clauses_satisfied(ex, val))

    def test_symmetry_clause(self):
        t = real_trail(4, 71, "col")
        counts = tuple(AM.check_trail(t))
        j = next(j for j in range(64) if AM.column(t[1][0], j) == 0)
        moved = AM.rotate_trail(AP.rotate_to_symmetry(t), (64 - j) % 64)
        ex, _ = AP.profile_cnf(self.m4, counts)
        val, _ = AP.profile_assignment(self.m4, counts, moved)
        self.assertEqual(ex[0], [self.m4.act[1][0]])
        self.assertEqual(val[self.m4.act[1][0]], AM.column(moved[1][0], 0) != 0)

    def test_wrong_length(self):
        with self.assertRaises(ValueError):
            AP.profile_cnf(self.m4, (1, 2, 3))


class TestVerifyAndInputs(unittest.TestCase):
    def test_verify_record(self):
        t = real_trail(4, 81, "col")
        total = sum(AM.check_trail(t))
        ok, counts = AP.verify_record({"trail": AM.trail_to_hex(t)}, total)
        self.assertTrue(ok)
        self.assertEqual(counts, AM.check_trail(t))
        ok, _ = AP.verify_record({"trail": AM.trail_to_hex(t)}, total - 1)
        self.assertFalse(ok)
        bad = AM.trail_to_hex(t)
        bad[2]["in"][3] = "%016x" % (int(bad[2]["in"][3], 16) ^ (1 << 5))
        ok, msg = AP.verify_record({"trail": bad}, 99)
        self.assertFalse(ok)
        ok, _ = AP.verify_record({"trail": AM.trail_to_hex(real_trail(3, 82, "col"))}, 99)
        self.assertFalse(ok)

    def test_find_inputs(self):
        d = tempfile.mkdtemp()
        try:
            os.makedirs(os.path.join(d, "a"))
            for rel in ("a/script.py", "possible_configurations.txt", "ascon_4r_42active.json", "other.json"):
                with open(os.path.join(d, rel), "w") as f:
                    f.write("x")
            got = AP.find_inputs(d)
            self.assertEqual(sorted(got), ["configs", "script", "seed"])
            self.assertTrue(got["script"].endswith("script.py"))
            self.assertEqual(AP.sha256_file(got["seed"]), hashlib.sha256(b"x").hexdigest())
        finally:
            shutil.rmtree(d)


class TestGrade(unittest.TestCase):
    def test_record(self):
        rows = {r["row"]: r for r in AP.grade(
            {"ok": True, "observed": {}}, {"ok": True, "observed": {}, "target_in_list": {}},
            {"status": "UNSAT"},
            [{"kind": "control", "status": "SAT"}, {"kind": "search", "status": "SAT", "profile": [15, 11, 9, 6]},
             {"kind": "search", "status": "UNSAT", "profile": [14, 11, 9, 7]},
             {"kind": "search", "status": "NOT_RUN", "profile": [1, 1, 1, 1]}],
            [{"active": 41, "round_counts": [15, 11, 9, 6]}])}
        self.assertEqual(rows["D0"]["verdict"], "held")
        self.assertEqual(rows["C1"]["verdict"], "held")
        self.assertEqual(rows["C2"]["verdict"], "held")
        self.assertTrue(rows["Q"]["verdict"].startswith("NEW RECORD"))
        self.assertIn("15-11-9-6", rows["Q"]["verdict"])
        self.assertEqual(rows["U"]["observed"], [[14, 11, 9, 7]])

    def test_nothing(self):
        rows = {r["row"]: r for r in AP.grade(
            {"ok": False, "observed": "ERROR"}, {"ok": False}, {"status": "TIMEOUT"},
            [{"kind": "control", "status": "TIMEOUT"}, {"kind": "search", "status": "TIMEOUT", "profile": [1, 1, 1, 1]}],
            [])}
        self.assertEqual(rows["D0"]["verdict"], "FAILED")
        self.assertEqual(rows["C2"]["verdict"], "FAILED")
        self.assertTrue(rows["C1"]["verdict"].startswith("inconclusive"))
        self.assertTrue(rows["Q"]["verdict"].startswith("no 4-round characteristic"))
        self.assertIn("1 profiles tried", rows["Q"]["verdict"])


@unittest.skipUnless(HAVE_PYSAT, "python-sat not installed")
class TestSolveWithPysat(unittest.TestCase):
    def test_two_round_controls(self):
        AP._MODEL[2] = AM.TrailModel(2)
        name = AP.pick_solver()
        d = tempfile.mkdtemp()
        try:
            t = real_trail(2, 91, "col")
            counts = tuple(AM.check_trail(t))
            rec = AP.solve_profile_once(2, counts, None, name, os.path.join(d, "a.json"))
            self.assertEqual(rec["status"], "SAT", rec)
            got = AP.parse_trail_obj({"trail": rec["trail"]})
            self.assertEqual(AM.check_trail(got), rec["round_counts"])
            self.assertTrue(all(c <= a for c, a in zip(rec["round_counts"], counts)))
            rec = AP.solve_profile_once(2, (1, 2), None, name, os.path.join(d, "b.json"))
            self.assertEqual(rec["status"], "UNSAT", rec)
            if hasattr(os, "fork"):
                rec = AP.solve_with_limit(2, (1, 2), None, name, os.path.join(d, "c.json"), 60)
                self.assertEqual(rec["status"], "UNSAT", rec)
        finally:
            shutil.rmtree(d)
            AP._MODEL.pop(2, None)


if __name__ == "__main__":
    unittest.main()
