# Copyright 2026 Munim, Inc.
# SPDX-License-Identifier: Apache-2.0
# Made with AI agents working in the name of MV2 of Munim, Inc.
"""Checks of ascon_family5.py (fam5-v1 F0 in PREREG_FAM5_V1.md): the S-box facts the
family rests on, the reconstruction of the published record characteristic, the
round-5 lower bound, and the enumeration against a direct, table-free computation."""

import importlib.util
import json
import math
import os
import random
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))


def _load(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(_HERE, name + ".py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


AM = _load("ascon_model")
AE = _load("ascon_extend")
F5 = _load("ascon_family5")

W125 = os.path.join(_HERE, "data", "third_party", "ascon-41-trail", "ascon_p4_41active_w125.json")


def load_trail(path):
    with open(path, encoding="utf-8") as f:
        obj = json.load(f)
    return [(tuple(int(h, 16) for h in rd["in"]), tuple(int(h, 16) for h in rd["out"]))
            for rd in obj["trail"]]


def pc(x):
    return bin(x).count("1")


def record_v():
    return load_trail(W125)[2][1][4]


class TestSboxFacts(unittest.TestCase):
    def test_ddt_facts(self):
        d = AM.ddt()
        self.assertEqual(d[1][1], 0)        # 00001 -> 00001 impossible
        self.assertEqual(d[8][1], 0)        # 01000 -> 00001 impossible
        self.assertGreater(d[9][1], 0)      # 01001 -> 00001 possible
        outs = [b for b in range(32) if d[1][b] > 0]
        self.assertEqual(len(outs), 8)
        self.assertTrue(all(b & 8 for b in outs))   # every output of 00001 flips x1

    def test_sbox_matches_spec(self):
        self.assertEqual(tuple(AM.sbox5(v) for v in range(32)), AM.SBOX_SPEC)


class TestLinearAlgebra(unittest.TestCase):
    def test_sigma_inverse(self):
        rng = random.Random(5)
        for i in range(5):
            for _ in range(40):
                x = rng.getrandbits(64)
                self.assertEqual(F5.sigma(i, F5.sigma_inv(i, x)), x)
                self.assertEqual(F5.sigma_inv(i, F5.sigma(i, x)), x)
                self.assertEqual(F5.sigma(i, x), AM.linear((x,) * 5)[i])

    def test_anchor_maps(self):
        rng = random.Random(6)
        for _ in range(40):
            v = rng.getrandbits(64)
            z, v2, o4, o1, s1 = F5.words_from_v(v)
            self.assertEqual(v2, v)
            self.assertEqual(F5.v_from_anchor("z", z), v)
            self.assertEqual(F5.v_from_anchor("v", v), v)
            self.assertEqual(F5.v_from_anchor("o4", o4), v)
            self.assertEqual(F5.v_from_anchor("o1", o1), v)

    def test_rotation_invariance(self):
        rng = random.Random(7)
        for _ in range(30):
            v = rng.getrandbits(64) & rng.getrandbits(64) & rng.getrandbits(64)
            if not v:
                continue
            s = rng.randrange(64)
            self.assertEqual(F5.quick_lb(v), F5.quick_lb(AM.rotr(v, s)))
            self.assertEqual(F5.canonical(v), F5.canonical(AM.rotr(v, s)))


class TestFamilyReconstruction(unittest.TestCase):
    def test_w125_is_a_family_member(self):
        trail = load_trail(W125)
        self.assertEqual(AM.check_trail(trail), [14, 11, 9, 7])
        v = record_v()
        self.assertEqual(trail[2][1], (0, 0, 0, 0, v))
        y2, x3, y3, x4 = F5.family_rounds(v)
        self.assertEqual(y2, trail[1][1])
        self.assertEqual(x3, trail[2][0])
        self.assertEqual(y3, trail[2][1])
        self.assertEqual(x4, trail[3][0])
        self.assertEqual(AM.check_trail([(trail[1][0], y2), (x3, y3), (x4, trail[3][1])]),
                         [11, 9, 7])
        z, _v, o4, o1, s1 = F5.words_from_v(v)
        self.assertEqual((pc(o1 | o4), pc(v), pc(z), pc(o4)), (11, 9, 7, 3))
        lb4, lb5 = F5.quick_lb(v)
        self.assertEqual(lb4, 28)
        self.assertEqual(lb5, 28 + pc(s1))

    def test_round5_lower_bound(self):
        v = record_v()
        z = F5.words_from_v(v)[0]
        r5 = AE.best_extension((0, 0, 0, 0, z))["min"]
        self.assertEqual(r5, 26)
        self.assertGreaterEqual(r5, pc(F5.sigma(1, z)))
        rng = random.Random(8)
        for _ in range(25):
            k = rng.choice([1, 2, 3, 4])
            z = 0
            while pc(z) != k:
                z |= 1 << rng.randrange(64)
            r5 = AE.best_extension((0, 0, 0, 0, z))["min"]
            self.assertGreaterEqual(r5, pc(F5.sigma(1, z)))


def direct(anchor, k, bound4, bound5, p1_lo=1, p1_hi=63):
    """Table-free reference for scan()."""
    import itertools
    out = set()
    n = 0
    for rest in itertools.combinations(range(1, 64), k - 1):
        if rest and not (p1_lo <= rest[0] <= p1_hi):
            continue
        a = 1
        for p in rest:
            a |= 1 << p
        n += 1
        v = F5.v_from_anchor(anchor, a)
        lb4, lb5 = F5.quick_lb(v)
        if lb4 <= bound4 or lb5 <= bound5:
            out.add(v)
    return sorted(out), n


class TestScan(unittest.TestCase):
    def test_enumerates_every_word(self):
        for anchor in F5.ANCHORS:
            for k in (1, 2, 3):
                hits, n = F5.scan(anchor, k, bound4=10 ** 6, bound5=10 ** 6)
                self.assertEqual(n, math.comb(63, k - 1))
                self.assertEqual(len(hits), n)

    def test_partition(self):
        h_all, n_all = F5.scan("z", 4, 1, 63, 80, 120)
        h_a, n_a = F5.scan("z", 4, 1, 10, 80, 120)
        h_b, n_b = F5.scan("z", 4, 11, 63, 80, 120)
        self.assertEqual(n_all, n_a + n_b)
        self.assertEqual(n_all, math.comb(63, 3))
        self.assertEqual(h_all, sorted(set(h_a) | set(h_b)))

    def test_matches_direct(self):
        for anchor in F5.ANCHORS:
            for k in (1, 2, 3):
                for b4, b5 in ((40, 66), (60, 90), (80, 120)):
                    self.assertEqual(F5.scan(anchor, k, 1, 63, b4, b5),
                                     direct(anchor, k, b4, b5), (anchor, k, b4, b5))
        self.assertEqual(F5.scan("v", 4, 2, 5, 80, 120), direct("v", 4, 80, 120, 2, 5))

    def test_record_found_by_o4_anchor(self):
        hits, _n = F5.scan("o4", 3)
        self.assertIn(F5.canonical(record_v()), {F5.canonical(h) for h in hits})


class TestExact(unittest.TestCase):
    def test_record_ok_at_bars(self):
        r = F5.exact(record_v())
        self.assertEqual((r["round2"], r["round3"], r["round4"], r["r5"]), (11, 9, 7, 26))
        self.assertTrue(r["r5_exact"])
        self.assertEqual(r["r1_needed"], 14)
        self.assertEqual(r["status"], "ok")

    def test_candidate_path(self):
        # With the 4-round bar raised to 41 the published round 1 (14 active) must be found.
        r = F5.exact(record_v(), bound4=41, bound5=66)
        self.assertEqual(r["status"], "candidate")
        self.assertEqual(r["r1_min_found"], 14)


if __name__ == "__main__":
    unittest.main()
