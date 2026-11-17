# Copyright 2026 Munim, Inc.
# SPDX-License-Identifier: Apache-2.0
# Made with AI agents working in the name of MV2 of Munim, Inc.
"""Tests for ascon_lns: seed parsing, the neighbourhood formula (it must accept the
trail it is built around and reject columns outside it), the search loop (only
independently re-checked improvements count), and grading."""

import hashlib
import importlib.util
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
LNS = _load("ascon_lns")

try:
    import pysat.solvers  # noqa: F401
    HAVE_PYSAT = True
except Exception:
    HAVE_PYSAT = False


def real_trail(rounds, seed, kind):
    """The differences a real pair follows through real rounds."""
    rnd = random.Random(seed)
    state = tuple(rnd.getrandbits(64) for _ in range(5))
    if kind == "col":            # one active column
        j = rnd.randrange(64)
        col = rnd.randrange(1, 32)
        delta = tuple(((col >> (4 - i)) & 1) << j for i in range(5))
    else:                        # dense
        delta = tuple(rnd.getrandbits(64) for _ in range(5))
    return AM.trail_from_pair(state, delta, rounds, rnd.randrange(12))


def norm(trail):
    return [(tuple(x), tuple(y)) for x, y in trail]


class TestSeeds(unittest.TestCase):
    def test_parse_roundtrip(self):
        t = real_trail(4, 1, "col")
        obj = json.loads(json.dumps({"R": 4, "trail": AM.trail_to_hex(t)}))
        self.assertEqual(LNS.parse_trail_obj(obj), norm(t))

    def test_parse_accepts_0x_prefix(self):
        t = real_trail(2, 2, "col")
        hx = [{"in": ["0x" + w for w in rd["in"]], "out": ["0X" + w for w in rd["out"]]}
              for rd in AM.trail_to_hex(t)]
        self.assertEqual(LNS.parse_trail_obj({"trail": hx}), norm(t))

    def test_parse_rejects_wrong_width(self):
        with self.assertRaises(ValueError):
            LNS.parse_trail_obj({"trail": [{"in": ["0"] * 4, "out": ["0"] * 5}]})

    def test_find_seeds(self):
        d = tempfile.mkdtemp()
        try:
            t4 = real_trail(4, 3, "col")
            t5 = real_trail(5, 4, "col")
            raw4 = json.dumps({"R": 4, "active": 99, "trail": AM.trail_to_hex(t4)}).encode()
            with open(os.path.join(d, "ascon_4r_42active.json"), "wb") as f:
                f.write(raw4)
            os.makedirs(os.path.join(d, "sub"))
            with open(os.path.join(d, "sub", "other.json"), "w") as f:
                json.dump({"trail": AM.trail_to_hex(t5)}, f)
            with open(os.path.join(d, "junk.json"), "w") as f:
                f.write("[1, 2, 3]")
            with open(os.path.join(d, "notjson.json"), "w") as f:
                f.write("{not json")
            found = LNS.find_seeds(d)
            self.assertEqual(sorted(found), [4, 5])
            self.assertEqual(found[4]["trail"], norm(t4))
            self.assertEqual(found[4]["sha256"], hashlib.sha256(raw4).hexdigest())
            self.assertEqual(found[4]["claimed_active"], 99)
            self.assertEqual(found[5]["trail"], norm(t5))
        finally:
            shutil.rmtree(d)

    def test_seed_active(self):
        t = real_trail(4, 5, "col")
        act = LNS.seed_active(t)
        self.assertEqual([len(a) for a in act], AM.check_trail(t))
        self.assertEqual(len(act[0]), 1)


class TestNeighbourhood(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m4 = AM.TrailModel(4)
        cls.seed = real_trail(4, 11, "col")
        cls.dense = real_trail(4, 12, "dense")

    def test_seed_satisfies_its_neighbourhoods(self):
        total = sum(AM.check_trail(self.seed))
        for restrict, extra in (((0, 1, 2, 3), 0), ((1, 2, 3), 0), ((2, 3), 1), ((1,), 2)):
            ex, nv = LNS.neighbourhood_cnf(self.m4, self.seed, restrict, extra, total)
            val, nv2 = LNS.neighbourhood_assignment(self.m4, self.seed, restrict, extra, total, self.seed)
            self.assertEqual(nv, nv2)
            self.assertTrue(AM.clauses_satisfied(self.m4.clauses, val))
            self.assertTrue(AM.clauses_satisfied(ex, val), (restrict, extra))
            self.assertIn(list(self.m4.act[0]), ex)

    def test_bound_below_total_violated_by_intended_values(self):
        total = sum(AM.check_trail(self.seed))
        ex, _ = LNS.neighbourhood_cnf(self.m4, self.seed, (1, 2, 3), 0, total - 1)
        val, _ = LNS.neighbourhood_assignment(self.m4, self.seed, (1, 2, 3), 0, total - 1, self.seed)
        self.assertFalse(AM.clauses_satisfied(ex, val))

    def test_outside_columns_counted(self):
        act_seed = LNS.seed_active(self.seed)
        act_dense = LNS.seed_active(self.dense)
        m = len(act_dense[1] - act_seed[1])
        self.assertGreater(m, 1)
        total = sum(AM.check_trail(self.dense))
        # extra = 0: unit clauses forbid every outside column
        ex, _ = LNS.neighbourhood_cnf(self.m4, self.seed, (1,), 0, total)
        val, _ = LNS.neighbourhood_assignment(self.m4, self.seed, (1,), 0, total, self.dense)
        self.assertFalse(AM.clauses_satisfied(ex, val))
        # extra = m: allowed
        ex, nv = LNS.neighbourhood_cnf(self.m4, self.seed, (1,), m, total)
        val, nv2 = LNS.neighbourhood_assignment(self.m4, self.seed, (1,), m, total, self.dense)
        self.assertEqual(nv, nv2)
        self.assertTrue(AM.clauses_satisfied(ex, val))
        # extra = m - 1: the intended counter values violate it
        ex, _ = LNS.neighbourhood_cnf(self.m4, self.seed, (1,), m - 1, total)
        val, _ = LNS.neighbourhood_assignment(self.m4, self.seed, (1,), m - 1, total, self.dense)
        self.assertFalse(AM.clauses_satisfied(ex, val))

    def test_wrong_round_count_rejected(self):
        with self.assertRaises(ValueError):
            LNS.neighbourhood_cnf(self.m4, real_trail(3, 1, "col"), (1,), 0, 10)


class TestCounterExtension(unittest.TestCase):
    def test_matches_seq_counter(self):
        for n in range(2, 8):
            lits = list(range(1, n + 1))
            for k in range(1, n):
                clauses, nxt = AM.seq_counter_atmost(lits, k, n + 1)
                for bits in range(1 << n):
                    val = {i + 1: bool(bits >> i & 1) for i in range(n)}
                    end = LNS.extend_counter_assignment(val, lits, k, n + 1)
                    self.assertEqual(end, nxt)
                    self.assertEqual(AM.clauses_satisfied(clauses, val), bin(bits).count("1") <= k, (n, k, bits))

    def test_trivial_bounds_add_nothing(self):
        val = {1: True, 2: False}
        self.assertEqual(LNS.extend_counter_assignment(val, [1, 2], 2, 3), 3)
        self.assertEqual(LNS.extend_counter_assignment(val, [1, 2], 0, 3), 3)


class TestSchedule(unittest.TestCase):
    def test_well_formed(self):
        for r, sched in LNS.SCHEDULE.items():
            self.assertIn(r, LNS.EXPECTED)
            self.assertEqual(len(set(sched)), len(sched))
            self.assertGreaterEqual(len(sched), 10)
            for restrict, extra in sched:
                self.assertTrue(restrict)
                self.assertEqual(list(restrict), sorted(set(restrict)))
                self.assertTrue(all(0 <= q < r for q in restrict))
                self.assertGreaterEqual(extra, 0)
            self.assertEqual(sched[0], ((1, 2, 3), 0))


class TestLoop(unittest.TestCase):
    def setUp(self):
        self.dense = real_trail(4, 21, "dense")
        self.sparse = real_trail(4, 22, "col")
        self.assertLess(sum(AM.check_trail(self.sparse)), sum(AM.check_trail(self.dense)))
        self.sched = (((1, 2, 3), 0), ((2, 3), 0), ((1,), 1))

    def test_improvement_restarts_schedule(self):
        calls = []
        records = []

        def solve(best, restrict, extra, bound, left):
            calls.append((restrict, extra, bound))
            if len(calls) == 2:
                return {"status": "SAT", "trail": AM.trail_to_hex(self.sparse)}
            return {"status": "UNSAT"}
        logs = []
        best, counts, steps = LNS.lns_loop(self.dense, self.sched, solve, lambda: 1e9, logs.append,
                                           lambda t, c, r: records.append(sum(c)))
        self.assertEqual(norm(best), norm(self.sparse))
        self.assertEqual(counts, AM.check_trail(self.sparse))
        self.assertEqual(steps, 2 + len(self.sched))
        self.assertEqual(records, [sum(counts)])
        self.assertEqual(calls[2][0], self.sched[0][0])            # restarted from the top
        self.assertEqual(calls[2][2], sum(counts) - 1)             # with the new bound
        self.assertEqual(logs[1]["improved_to"], sum(counts))

    def test_invalid_trail_is_not_a_record(self):
        bad = AM.trail_to_hex(self.sparse)
        bad[1]["in"][0] = "%016x" % (int(bad[1]["in"][0], 16) ^ 1)

        def solve(best, restrict, extra, bound, left):
            return {"status": "SAT", "trail": bad}
        logs = []
        best, counts, steps = LNS.lns_loop(self.dense, self.sched, solve, lambda: 1e9, logs.append)
        self.assertEqual(norm(best), norm(self.dense))
        self.assertEqual(steps, len(self.sched))
        self.assertTrue(all(r["status"] == "ERROR" for r in logs))

    def test_sat_above_bound_is_not_a_record(self):
        def solve(best, restrict, extra, bound, left):
            return {"status": "SAT", "trail": AM.trail_to_hex(self.dense)}
        logs = []
        best, _, _ = LNS.lns_loop(self.dense, self.sched, solve, lambda: 1e9, logs.append)
        self.assertEqual(norm(best), norm(self.dense))
        self.assertTrue(all(r["status"] == "ERROR" for r in logs))

    def test_stops_when_time_is_up(self):
        def solve(*a):
            raise AssertionError("should not be called")
        best, _, steps = LNS.lns_loop(self.dense, self.sched, solve, lambda: 5.0, lambda r: None)
        self.assertEqual(steps, 0)


class TestGrade(unittest.TestCase):
    def test_rows(self):
        seed_checks = {4: {"counts": [15, 11, 9, 7]}, 5: {"error": "seed file not found under --data"}}
        lanes = {4: {"sanity_formula": True, "sanity_status": "SAT", "best_total": 41, "best_counts": [15, 10, 9, 7]}}
        rows = {r["row"]: r for r in LNS.grade(seed_checks, lanes)}
        self.assertEqual(rows["S0-4r"]["verdict"], "held")
        self.assertEqual(rows["S1-4r"]["verdict"], "held")
        self.assertTrue(rows["Q-4r"]["verdict"].startswith("NEW RECORD"))
        self.assertIn("15-10-9-7", rows["Q-4r"]["verdict"])
        self.assertEqual(rows["S0-5r"]["verdict"], "FAILED")
        self.assertEqual(rows["S1-5r"]["verdict"], "FAILED")
        self.assertTrue(rows["Q-5r"]["verdict"].startswith("no characteristic"))

    def test_no_improvement(self):
        rows = {r["row"]: r for r in LNS.grade({4: {"counts": [15, 11, 9, 7]}},
                                               {4: {"sanity_formula": True, "sanity_status": "SAT",
                                                    "best_total": 42, "best_counts": [15, 11, 9, 7]}})}
        self.assertTrue(rows["Q-4r"]["verdict"].startswith("no characteristic"))


@unittest.skipUnless(HAVE_PYSAT, "python-sat not installed")
class TestSolveWithPysat(unittest.TestCase):
    def test_solve_once_finds_seed_neighbourhood(self):
        LNS._MODELS[2] = AM.TrailModel(2)
        seed = real_trail(2, 31, "col")
        total = sum(AM.check_trail(seed))
        name = LNS.pick_solver()
        d = tempfile.mkdtemp()
        try:
            rec = LNS.solve_once(2, seed, (0, 1), 0, total, name, os.path.join(d, "a.json"))
            self.assertEqual(rec["status"], "SAT", rec)
            self.assertLessEqual(rec["total_active"], total)
            t = LNS.parse_trail_obj({"trail": rec["trail"]})
            self.assertEqual(AM.check_trail(t), rec["round_counts"])
            act = LNS.seed_active(seed)
            for r, a in enumerate(LNS.seed_active(t)):
                self.assertTrue(a <= act[r])
            # the 2-round minimum is 4, so a bound of 3 is UNSAT in any neighbourhood
            rec = LNS.solve_once(2, seed, (1,), 0, 3, name, os.path.join(d, "b.json"))
            self.assertEqual(rec["status"], "UNSAT", rec)
            if hasattr(os, "fork"):
                fn = LNS.make_solver_fn(2, name, d, 60)
                rec = fn(seed, (0, 1), 0, total, 1000)
                self.assertEqual(rec["status"], "SAT", rec)
        finally:
            shutil.rmtree(d)
            LNS._MODELS.pop(2, None)


if __name__ == "__main__":
    unittest.main()
