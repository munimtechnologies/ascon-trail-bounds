# Copyright 2026 Munim, Inc.
# SPDX-License-Identifier: Apache-2.0
# Made with AI agents working in the name of MV2 of Munim, Inc.
"""Tests for ascon_extend: the exact one-round extension is checked against an
independent brute force on small random states, and the extension of the last round
of the 41-active-S-box characteristic published by L. Sotomayor (ascon-41-trail v1.0.0,
trails/ascon_p4_41active_w125.json, profile 14-11-9-7) is checked exhaustively over all
8^7 output choices of its last round."""

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
AE = _load("ascon_extend")

Z = 0
C = 0x0220000008202208            # round-4 input of the w125 trail lives in x4 only
X4 = (Z, Z, Z, Z, C)
Y4_PUBLISHED = (Z, C, Z, Z, C)    # every round-4 S-box: 00001 -> 01001
Y4_NEW = (0x0000000000200000, C, Z, Z, 0x0220000008002208)  # column 21: 00001 -> 11000
X5_NEW = (0x0200000000200004, 0x1330404459257248, Z, Z, 0x122040110C11324C)
COLS4 = [3, 9, 13, 21, 27, 53, 57]
COLS5 = [2, 3, 6, 9, 12, 13, 14, 16, 18, 20, 21, 24, 26, 27, 28, 30, 32, 34, 36, 38,
         46, 52, 53, 56, 57, 60]


def brute_min(xw):
    """Independent: build every full output y and apply the real linear layer."""
    table = AM.ddt()
    cols = AE.active_columns(xw)
    rows = [[b for b in range(32) if table[AM.column(xw, j)][b] > 0] for j in cols]
    best = 65
    for bs in itertools.product(*rows):
        y = [0, 0, 0, 0, 0]
        for j, b in zip(cols, bs):
            for i in range(5):
                y[i] |= ((b >> (4 - i)) & 1) << j
        best = min(best, AE.n_active(AM.linear(tuple(y))))
    return best


class TestExtend(unittest.TestCase):
    def test_ddt_row_00001(self):
        table = AM.ddt()
        row = {b: table[1][b] for b in range(32) if table[1][b]}
        self.assertEqual(sorted(row), [9, 11, 13, 15, 24, 26, 28, 30])
        self.assertTrue(all(v == 4 for v in row.values()))

    def test_against_brute_force(self):
        rng = random.Random(20261119)
        for _ in range(25):
            words = [0, 0, 0, 0, 0]
            for j in rng.sample(range(64), rng.randint(1, 3)):
                a = rng.randrange(1, 32)
                for i in range(5):
                    words[i] |= ((a >> (4 - i)) & 1) << j
            xw = tuple(words)
            res = AE.best_extension(xw)
            self.assertEqual(res["min"], brute_min(xw))
            y = AE.output_from_choice(res["columns"], res["first_minimiser"])
            self.assertEqual(AE.n_active(AM.linear(y)), res["min"])
            self.assertEqual(AM.check_trail([(xw, y)]), [len(res["columns"])])

    def test_published_round4(self):
        self.assertEqual(AE.active_columns(X4), COLS4)
        self.assertEqual(AM.check_trail([(X4, Y4_PUBLISHED)]), [7])
        # with the published round-4 outputs, the next round would have 27 active S-boxes
        self.assertEqual(AE.n_active(AM.linear(Y4_PUBLISHED)), 27)

    def test_new_round4_and_round5(self):
        self.assertEqual(AM.linear(Y4_NEW), X5_NEW)
        self.assertEqual(AE.active_columns(X5_NEW), COLS5)
        suffix = [(X4, Y4_NEW), (X5_NEW, AE.next_round_output(X5_NEW))]
        self.assertEqual(AM.check_trail(suffix), [7, 26])
        # only column 21 differs from the published round-4 output
        diff = tuple(a ^ b for a, b in zip(Y4_NEW, Y4_PUBLISHED))
        self.assertEqual(AE.active_columns(diff), [21])

    def test_exhaustive_minimum_is_26(self):
        res = AE.best_extension(X4)
        self.assertEqual(res["choices"], 8 ** 7)
        self.assertEqual(res["columns"], COLS4)
        self.assertEqual(res["min"], 26)
        self.assertGreaterEqual(res["n_minimisers"], 1)

    def test_extend_trail_suffix(self):
        new, counts, best = AE.extend_trail([(X4, Y4_PUBLISHED)])
        self.assertEqual(counts, [7, 26])
        self.assertEqual(best["min"], 26)

    def test_results_json(self):
        p = os.path.join(_HERE, "ext5_w125_suffix.json")
        with open(p, encoding="utf-8") as f:
            obj = json.load(f)
        h = lambda ws: tuple(int(w, 16) for w in ws)  # noqa: E731
        self.assertEqual(h(obj["round4_in"]), X4)
        self.assertEqual(h(obj["round4_out_published"]), Y4_PUBLISHED)
        self.assertEqual(h(obj["round4_out_new"]), Y4_NEW)
        self.assertEqual(h(obj["round5_in"]), X5_NEW)
        self.assertEqual(obj["round5_active_columns"], COLS5)
        self.assertEqual(obj["round5_active_published_output"], 27)
        self.assertEqual(obj["round5_active_min"], 26)
        self.assertEqual(obj["five_round_profile"], [14, 11, 9, 7, 26])
        self.assertEqual(obj["five_round_active"], 67)

    def test_parse_trail_obj(self):
        obj = {"R": 1, "trail": [{"in": ["%016x" % w for w in X4],
                                  "out": ["%016x" % w for w in Y4_PUBLISHED]}]}
        self.assertEqual(AE.parse_trail_obj(obj), [(X4, Y4_PUBLISHED)])
        self.assertEqual(AE.parse_trail_obj({"rounds": obj["trail"]}), [(X4, Y4_PUBLISHED)])


if __name__ == "__main__":
    unittest.main()
