# Copyright 2026 Munim, Inc.
# SPDX-License-Identifier: Apache-2.0
# Made with AI agents working in the name of MV2 of Munim, Inc.
"""Tests for ascon_pair: the S-box graph CNF and the per-column condition CNFs are
exact (all points checked), real pairs through real rounds satisfy the value model in
their own window and decode back, other states and other windows violate it, and the
formula-free pair check accepts exactly the trail a pair really follows."""

import importlib.util
import json
import math
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
AP = _load("ascon_pair")

try:
    import pysat.solvers  # noqa: F401
    HAVE_PYSAT = True
except Exception:
    HAVE_PYSAT = False


def eval_local(clauses, p):
    return all(any((lit > 0) == bool(p >> (abs(lit) - 1) & 1) for lit in c) for c in clauses)


def real_pair(rounds, seed, first):
    rnd = random.Random(seed)
    state = tuple(rnd.getrandbits(64) for _ in range(5))
    j = rnd.randrange(64)
    col = rnd.randrange(1, 32)
    delta = tuple(((col >> (4 - i)) & 1) << j for i in range(5))
    return state, AM.trail_from_pair(state, delta, rounds, first)


def full_model(m, val):
    return [v if val[v] else -v for v in range(1, m.nv + 1)]


class TestLocalCnfs(unittest.TestCase):
    def test_sbox_graph_exact(self):
        cnf = AP.sbox_graph_cnf()
        graph = {(v << 5) | AM.sbox5(v) for v in range(32)}
        for p in range(1024):
            self.assertEqual(eval_local(cnf, p), p in graph, p)

    def test_sbox_matches_spec_table(self):
        self.assertEqual(tuple(AM.sbox5(v) for v in range(32)), AM.SBOX_SPEC)

    def test_solution_sets_affine_and_condition_cnf_exact(self):
        table = AM.ddt()
        nonempty = 0
        for a in range(1, 32):
            for b in range(32):
                m = AP.solution_set(a, b)
                self.assertEqual(len(m), table[a][b])
                if not m:
                    with self.assertRaises(ValueError):
                        AP.condition_cnf(a, b)
                    continue
                nonempty += 1
                self.assertTrue(AP.is_affine(m), (a, b))
                self.assertEqual(len(m) & (len(m) - 1), 0)
                cnf = AP.condition_cnf(a, b)
                for v in range(32):
                    self.assertEqual(eval_local(cnf, v), v in m, (a, b, v))
        self.assertGreater(nonempty, 31)

    def test_is_affine_rejects(self):
        self.assertFalse(AP.is_affine({0, 1, 2}))
        self.assertTrue(AP.is_affine({5, 6, 9, 10}))   # 5 + span{3, 12}

    def test_xor_parity(self):
        vs = [1, 2, 3, 4]
        for parity in (0, 1):
            cl = AP.xor_parity_clauses(vs, parity)
            for bits in range(16):
                val = {i + 1: bool(bits >> i & 1) for i in range(4)}
                self.assertEqual(AM.clauses_satisfied(cl, val), bin(bits).count("1") % 2 == parity)


class TestPairModel(unittest.TestCase):
    def test_real_pair_satisfies_and_decodes(self):
        for seed, first in ((1, 8), (2, 0), (3, 5)):
            state, trail = real_pair(4, seed, first)
            m = AP.PairModel(trail, first)
            self.assertEqual(m.n_conditions, sum(AM.check_trail(trail)))
            val = m.assignment_from_state(state)
            self.assertTrue(AM.clauses_satisfied(m.clauses, val), (seed, first))
            self.assertEqual(m.decode(full_model(m, val)), state)
            self.assertTrue(AP.check_pair(state, trail, first))

    def test_states_match_permutation(self):
        state, trail = real_pair(3, 4, 2)
        m = AP.PairModel(trail, 2)
        s = state
        for r, (a, b) in enumerate(m.states_from(state)):
            self.assertEqual(AM.linear(b), AM.permutation_round(s, AM.ROUND_CONSTANTS[2 + r]))
            s = AM.permutation_round(s, AM.ROUND_CONSTANTS[2 + r])

    def test_other_state_violates(self):
        state, trail = real_pair(4, 5, 8)
        m = AP.PairModel(trail, 8)
        rnd = random.Random(99)
        other = tuple(rnd.getrandbits(64) for _ in range(5))
        self.assertFalse(AM.clauses_satisfied(m.clauses, m.assignment_from_state(other)))
        self.assertFalse(AP.check_pair(other, trail, 8))

    def test_other_window_violates(self):
        state, trail = real_pair(4, 6, 8)
        m = AP.PairModel(trail, 3)
        self.assertFalse(AM.clauses_satisfied(m.clauses, m.assignment_from_state(state)))
        self.assertFalse(AP.check_pair(state, trail, 3))

    def test_window_bounds(self):
        _, trail = real_pair(4, 7, 0)
        with self.assertRaises(ValueError):
            AP.PairModel(trail, 9)
        with self.assertRaises(ValueError):
            AP.PairModel(trail, -1)
        self.assertEqual(AP.parse_windows("all", 4), list(range(9)))
        self.assertEqual(AP.parse_windows("all", 5), list(range(8)))
        self.assertEqual(AP.parse_windows("8,0,9", 4), [0, 8])

    def test_invalid_trail_rejected(self):
        _, trail = real_pair(3, 8, 0)
        bad = [list(map(list, rd)) for rd in trail]
        bad[1][0][0] ^= 1
        bad = [(tuple(x), tuple(y)) for x, y in bad]
        with self.assertRaises(ValueError):
            AP.PairModel(bad, 0)

    def test_check_pair_rejects_wrong_trail(self):
        state, trail = real_pair(3, 9, 1)
        t2 = list(trail)
        x, y = t2[2]
        t2[2] = (x, (y[0] ^ 1,) + tuple(y[1:]))
        self.assertFalse(AP.check_pair(state, t2, 1))

    def test_weight(self):
        table = AM.ddt()
        state, trail = real_pair(2, 10, 4)
        expect = 0.0
        for xw, yw in trail:
            for j in range(64):
                a, b = AM.column(xw, j), AM.column(yw, j)
                if a:
                    expect += 5 - math.log2(table[a][b])
        self.assertAlmostEqual(AP.trail_weight(trail), expect)
        self.assertEqual(AP.trail_weight(trail), int(AP.trail_weight(trail)))
        self.assertGreaterEqual(AP.trail_weight(trail), 2 * sum(AM.check_trail(trail)))

    def test_find_trail_files(self):
        d = tempfile.mkdtemp()
        try:
            _, t4 = real_pair(4, 12, 0)
            _, t5 = real_pair(5, 13, 0)
            os.makedirs(os.path.join(d, "sub"))
            with open(os.path.join(d, "a4.json"), "w") as f:
                json.dump({"trail": AM.trail_to_hex(t4)}, f)
            with open(os.path.join(d, "sub", "b5.json"), "w") as f:
                json.dump({"trail": AM.trail_to_hex(t5)}, f)
            bad = AM.trail_to_hex(t4)
            bad[1]["in"][0] = "%016x" % (int(bad[1]["in"][0], 16) ^ 1)
            with open(os.path.join(d, "bad.json"), "w") as f:
                json.dump({"trail": bad}, f)
            with open(os.path.join(d, "junk.json"), "w") as f:
                f.write("{nope")
            self.assertEqual([os.path.basename(p) for p in AP.find_trail_files(d)], ["a4.json", "b5.json"])
            self.assertEqual([os.path.basename(p) for p in AP.find_trail_files(d, 5)], ["b5.json"])
        finally:
            shutil.rmtree(d)

    def test_parse_roundtrip(self):
        _, trail = real_pair(4, 11, 0)
        obj = json.loads(json.dumps({"trail": AM.trail_to_hex(trail)}))
        self.assertEqual(AP.parse_trail_obj(obj), [(tuple(x), tuple(y)) for x, y in trail])


@unittest.skipUnless(HAVE_PYSAT, "python-sat not installed")
class TestSolveWithPysat(unittest.TestCase):
    def test_solve_window_finds_pair(self):
        name = AP.pick_solver()
        d = tempfile.mkdtemp()
        try:
            for rounds, first in ((2, 10), (3, 6)):
                _, trail = real_pair(rounds, 20 + rounds, first)
                rec = AP.solve_window(trail, first, name, os.path.join(d, "w%d.json" % rounds))
                self.assertEqual(rec["status"], "SAT", rec)
                state = tuple(int(h, 16) for h in rec["state"])
                self.assertTrue(AP.check_pair(state, trail, first))
        finally:
            shutil.rmtree(d)

    def test_main_end_to_end(self):
        if not hasattr(os, "fork"):
            self.skipTest("needs fork")
        d = tempfile.mkdtemp()
        try:
            _, trail = real_pair(2, 30, 0)
            p = os.path.join(d, "t2.json")
            with open(p, "w") as f:
                json.dump({"trail": AM.trail_to_hex(trail)}, f)
            out = os.path.join(d, "out")
            AP.main(["--trail", p, "--out", out, "--windows", "0,10", "--per-window", "120", "--jobs", "2"])
            with open(os.path.join(out, "pair_summary.json")) as f:
                summ = json.load(f)
            row = summ["rows"][0]
            self.assertEqual(row["windows_tried"], 2)
            self.assertIn(0, row["windows_with_pair"])
            self.assertTrue(os.path.exists(os.path.join(out, "pairs", "t2_w00.json")))
        finally:
            shutil.rmtree(d)


if __name__ == "__main__":
    unittest.main()
