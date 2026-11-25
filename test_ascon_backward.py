# Copyright 2026 Munim, Inc.
# SPDX-License-Identifier: Apache-2.0
# Made with AI agents working in the name of MV2 of Munim, Inc.
"""Tests for ascon_backward (exact backward one-round extension).

1. The inverse linear layer is checked on random states in both directions.
2. search() is checked against an independent brute force (every allowed input,
   through the real inverse linear layer) on random small instances: same set size,
   same minimum, same number of minimisers.
3. Sanity on published data: for the round-2 output of L. Sotomayor's 41-active
   characteristic (ascon-41-trail v1.0.0, MIT, data/third_party), the search at
   threshold 14 finds the published round-2 input, whose round 1 has 14 active S-boxes.
"""

import importlib.util
import itertools
import json
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
AB = _load("ascon_backward")

W125 = os.path.join(_HERE, "data", "third_party", "ascon-41-trail", "ascon_p4_41active_w125.json")


def load_trail(path):
    with open(path, encoding="utf-8") as f:
        obj = json.load(f)
    return [(tuple(int(h, 16) for h in rd["in"]), tuple(int(h, 16) for h in rd["out"]))
            for rd in obj["trail"]]


def brute(y):
    """Independent: every allowed input x for output y, through the inverse layer."""
    table = AM.ddt()
    cols = AB.active_columns(y)
    rows = [[a for a in range(1, 32) if table[a][AM.column(y, j)] > 0] for j in cols]
    counts = []
    for combo in itertools.product(*rows):
        x = [0, 0, 0, 0, 0]
        for j, a in zip(cols, combo):
            for i in range(5):
                x[i] |= ((a >> (4 - i)) & 1) << j
        counts.append(AB.n_active(AB.inv_linear(tuple(x))))
    return counts


def random_state(rng, ncols):
    words = [0, 0, 0, 0, 0]
    for j in rng.sample(range(64), ncols):
        b = rng.randrange(1, 32)
        for i in range(5):
            words[i] |= ((b >> (4 - i)) & 1) << j
    return tuple(words)


class TestInverse(unittest.TestCase):
    def test_inverse_both_ways(self):
        rng = random.Random(20261124)
        for _ in range(200):
            x = tuple(rng.getrandbits(64) for _ in range(5))
            self.assertEqual(AM.linear(AB.inv_linear(x)), x)
            self.assertEqual(AB.inv_linear(AM.linear(x)), x)

    def test_unit_vectors(self):
        for i in range(5):
            for j in (0, 1, 17, 63):
                z = AB.inv_row(i, 1 << j)
                a, b = AM.ROT[i]
                self.assertEqual(z ^ AM.rotr(z, a) ^ AM.rotr(z, b), 1 << j)


class TestSearch(unittest.TestCase):
    def test_against_brute_force(self):
        rng = random.Random(1124)
        for k in range(15):
            y = random_state(rng, rng.randint(1, 3))
            counts = brute(y)
            leaves = AB.search(y, 64)
            self.assertEqual(len(leaves), len(counts))
            self.assertEqual(sorted(c for c, _x in leaves), sorted(counts))
            m = min(counts)
            low = AB.search(y, m)
            self.assertEqual(len(low), counts.count(m))
            self.assertEqual(AB.search(y, m - 1), [])
            if k < 5:
                self.assertEqual(AB.minimum(y, 64), (m, counts.count(m)))
            for c, x in low:
                self.assertEqual(AB.prepend_count(x), c)
                self.assertEqual(AM.check_trail([(x, y)]), [len(AB.active_columns(y))])

    def test_published_core_sanity(self):
        trail = load_trail(W125)
        self.assertEqual(AM.check_trail(trail), [14, 11, 9, 7])
        x2, y2 = trail[1]
        self.assertEqual(AB.inv_linear(x2), trail[0][1])
        self.assertEqual(AB.prepend_count(x2), 14)
        self.assertEqual(len(AB.active_columns(y2)), 11)
        leaves = AB.search(y2, 14)
        self.assertIn((14, x2), leaves)


if __name__ == "__main__":
    unittest.main()
