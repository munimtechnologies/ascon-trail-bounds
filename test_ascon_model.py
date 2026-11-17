# Copyright 2026 Munim, Inc.
# SPDX-License-Identifier: Apache-2.0
# Made with AI agents working in the name of MV2 of Munim, Inc.
"""Tests for ascon_model: the formula must accept every real characteristic
(no over-constraint, which would make an UNSAT result meaningless) and reject
every impossible S-box transition (no under-constraint)."""

import importlib.util
import itertools
import os
import random
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location("ascon_model", os.path.join(_HERE, "ascon_model.py"))
AM = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(AM)


class TestSbox(unittest.TestCase):
    def test_bitsliced_matches_spec_table(self):
        self.assertEqual(tuple(AM.sbox5(v) for v in range(32)), AM.SBOX_SPEC)

    def test_is_permutation(self):
        self.assertEqual(sorted(AM.sbox5(v) for v in range(32)), list(range(32)))

    def test_ddt_rows_and_uniformity(self):
        t = AM.ddt()
        self.assertEqual(t[0][0], 32)
        for a in range(32):
            self.assertEqual(sum(t[a]), 32)
        self.assertEqual(max(t[a][b] for a in range(1, 32) for b in range(32)), 8)
        for a in range(1, 32):
            self.assertEqual(t[a][0], 0)

    def test_quadratic_sbox_output_sets_are_affine(self):
        # Ascon's S-box has degree 2, so each derivative is affine and every set
        # {b : DDT[a][b] > 0} is an affine subspace (closed under x ^ y ^ z).
        t = AM.ddt()
        for a in range(1, 32):
            outs = {b for b in range(32) if t[a][b]}
            for x, y, z in itertools.product(sorted(outs), repeat=3):
                self.assertIn(x ^ y ^ z, outs)

    def test_sbox_cnf_is_exact(self):
        t = AM.ddt()
        for a in range(32):
            for b in range(32):
                self.assertEqual(AM.eval_local_sbox_cnf(a, b), t[a][b] > 0, (a, b))


class TestLinearAndRound(unittest.TestCase):
    def test_rotr(self):
        self.assertEqual(AM.rotr(1, 1), 1 << 63)
        self.assertEqual(AM.rotr(1 << 5, 5), 1)

    def test_linear_is_linear(self):
        rnd = random.Random(1)
        for _ in range(50):
            u = tuple(rnd.getrandbits(64) for _ in range(5))
            v = tuple(rnd.getrandbits(64) for _ in range(5))
            uv = tuple(a ^ b for a, b in zip(u, v))
            self.assertEqual(AM.linear(uv), tuple(a ^ b for a, b in zip(AM.linear(u), AM.linear(v))))

    def test_sbox_layer_is_columnwise(self):
        rnd = random.Random(2)
        for _ in range(20):
            w = tuple(rnd.getrandbits(64) for _ in range(5))
            out = AM.sbox_layer(w)
            for j in range(64):
                self.assertEqual(AM.column(out, j), AM.sbox5(AM.column(w, j)))


class TestModel(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m4 = AM.TrailModel(4)

    def _real_trails(self, rounds, n, seed):
        rnd = random.Random(seed)
        out = []
        for k in range(n):
            state = tuple(rnd.getrandbits(64) for _ in range(5))
            if k % 3 == 0:     # one-bit difference
                delta = [0] * 5
                delta[rnd.randrange(5)] = 1 << rnd.randrange(64)
            elif k % 3 == 1:   # one random active column
                j = rnd.randrange(64)
                col = rnd.randrange(1, 32)
                delta = [((col >> (4 - i)) & 1) << j for i in range(5)]
            else:              # dense
                delta = [rnd.getrandbits(64) for _ in range(5)]
            out.append(AM.trail_from_pair(state, tuple(delta), rounds, rnd.randrange(12)))
        return out

    def test_real_pairs_satisfy_structural_clauses(self):
        for trail in self._real_trails(4, 12, 3):
            AM.check_trail(trail)
            val = self.m4.assignment_from_trail(trail)
            self.assertTrue(AM.clauses_satisfied(self.m4.clauses, val))

    def test_rotated_real_trails_still_valid(self):
        for trail in self._real_trails(4, 6, 4):
            counts = AM.check_trail(trail)
            for s in (1, 17, 63):
                rt = AM.rotate_trail(trail, s)
                self.assertEqual(AM.check_trail(rt), counts)
                self.assertTrue(AM.clauses_satisfied(self.m4.clauses, self.m4.assignment_from_trail(rt)))

    def test_flipped_linear_bit_is_rejected(self):
        trail = self._real_trails(4, 1, 5)[0]
        val = self.m4.assignment_from_trail(trail)
        v = self.m4.x[2][3][10]
        val[v] = not val[v]
        # keep the active flag consistent so only the linear/S-box clauses can fail
        col = [val[self.m4.x[2][i][10]] for i in range(5)]
        val[self.m4.act[2][10]] = any(col)
        self.assertFalse(AM.clauses_satisfied(self.m4.clauses, val))

    def test_decode_roundtrip(self):
        trail = self._real_trails(4, 2, 6)[1]
        val = self.m4.assignment_from_trail(trail)
        model = [v if val.get(v, False) else -v for v in range(1, self.m4.nv + 1)]
        self.assertEqual(self.m4.decode(model), [(tuple(x), tuple(y)) for x, y in trail])

    def test_symmetry_normalisation_exists(self):
        # Any real trail can be rotated so column 0 of the symmetry round is active.
        r = AM.symmetry_round(4)
        for trail in self._real_trails(4, 6, 7):
            xw = trail[r][0]
            j = next(j for j in range(64) if AM.column(xw, j))
            rt = AM.rotate_trail(trail, j)   # rotr by j moves column j to column 0
            self.assertNotEqual(AM.column(rt[r][0], 0), 0)

    def test_build_cnf_accepts_real_trail_under_its_count(self):
        trail = self._real_trails(2, 1, 8)[0]
        counts = AM.check_trail(trail)
        r = AM.symmetry_round(2)
        j = next(j for j in range(64) if AM.column(trail[r][0], j))
        trail = AM.rotate_trail(trail, j)
        m, clauses, nvars = AM.build_cnf(2, sum(counts))
        # extend the assignment to the counter's auxiliary variables by brute
        # unit propagation: set every aux var to the true running count.
        val = m.assignment_from_trail(trail)
        acts = m.active_vars()
        k = sum(counts)
        if k < len(acts):
            nxt = m.nv + 1
            running = 0
            for i in range(len(acts) - 1):
                running += val[acts[i]]
                for jj in range(1, k + 1):
                    val[nxt] = running >= jj
                    nxt += 1
            self.assertEqual(nxt - 1, nvars)
        self.assertTrue(AM.clauses_satisfied(clauses, val))


class TestCardinality(unittest.TestCase):
    def _sat_with_aux(self, clauses, xvals, n, nvars):
        aux = list(range(n + 1, nvars + 1))
        for bits in range(1 << len(aux)):
            val = {i + 1: xvals[i] for i in range(n)}
            for idx, v in enumerate(aux):
                val[v] = bool(bits >> idx & 1)
            if AM.clauses_satisfied(clauses, val):
                return True
        return False

    def test_seq_counter_brute_force(self):
        for n, ks in ((4, (0, 1, 2, 3, 4)), (5, (1, 2))):
            lits = list(range(1, n + 1))
            for k in ks:
                clauses, nxt = AM.seq_counter_atmost(lits, k, n + 1)
                for bits in range(1 << n):
                    xvals = [bool(bits >> i & 1) for i in range(n)]
                    self.assertEqual(self._sat_with_aux(clauses, xvals, n, nxt - 1),
                                     sum(xvals) <= k, (n, k, bits))


class TestXor(unittest.TestCase):
    def test_xor_zero_clauses(self):
        cl = AM.xor_zero_clauses([1, 2, 3, 4])
        for bits in range(16):
            val = {i + 1: bool(bits >> i & 1) for i in range(4)}
            self.assertEqual(AM.clauses_satisfied(cl, val), bin(bits).count("1") % 2 == 0)


if __name__ == "__main__":
    unittest.main()
