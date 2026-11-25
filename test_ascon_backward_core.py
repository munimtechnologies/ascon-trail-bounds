# Copyright 2026 Munim, Inc.
# SPDX-License-Identifier: Apache-2.0
# Made with AI agents working in the name of MV2 of Munim, Inc.
"""Claim B2 of PREREG_BACK_V1.md, checked exhaustively (stated before this test ran).

Fix the round-2 S-box output of L. Sotomayor's 41-active 4-round characteristic
(ascon-41-trail v1.0.0, MIT, data/third_party). The same round-2 output, rotated, also
occurs in Sotomayor's second 41-trail and in N. Otoi's 42-trail (test_ascon_extend_full.py).
Claim: over EVERY allowed round-2 input difference (any of the 2^55 row patterns on the
11 active columns that the S-box allows), round 1 has at least 14 active S-boxes. So no
4-round characteristic that ends with this 11-9-7 tail has fewer than 41.

If this test fails while test_ascon_backward.py passes, the search found a round 1 with
13 or fewer active S-boxes, i.e. a candidate 4-round characteristic with 40 or fewer.
"""

import importlib.util
import json
import os
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


class TestCoreRound1Bound(unittest.TestCase):
    def test_round1_needs_14(self):
        trail = load_trail(W125)
        self.assertEqual(AM.check_trail(trail), [14, 11, 9, 7])
        y2 = trail[1][1]
        # sanity: the inverse layer is exact on this state
        self.assertEqual(AM.linear(AB.inv_linear(trail[1][0])), trail[1][0])
        self.assertEqual(AB.search(y2, 13), [])


if __name__ == "__main__":
    unittest.main()
