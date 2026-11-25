# Copyright 2026 Munim, Inc.
# SPDX-License-Identifier: Apache-2.0
# Made with AI agents working in the name of MV2 of Munim, Inc.
"""Claim B3b of PREREG_BACK_V1.md, checked exhaustively (stated before this test ran).

As B3a, for L. Sotomayor's second 41-active 4-round characteristic (ascon-41-trail
v1.0.0, weight 140, MIT, data/third_party), whose round 1 differs from the weight-125 one.
Claim: over EVERY allowed round-1 input difference, a round put in front of it has at
least 26 active S-boxes, so (new round) + 14-11-9-7 cannot beat 67.

If this test fails while test_ascon_backward.py passes, the search found a prepended round
with 25 or fewer active S-boxes, i.e. a candidate 5-round characteristic with 66 or fewer.
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

DATA = os.path.join(_HERE, "data", "third_party", "ascon-41-trail", "ascon_p4_41active_w140.json")


def load_trail(path):
    with open(path, encoding="utf-8") as f:
        obj = json.load(f)
    return [(tuple(int(h, 16) for h in rd["in"]), tuple(int(h, 16) for h in rd["out"]))
            for rd in obj["trail"]]


class TestPrepend(unittest.TestCase):
    def test_prepended_round_needs_26(self):
        trail = load_trail(DATA)
        self.assertEqual(AM.check_trail(trail), [14, 11, 9, 7])
        y1 = trail[0][1]
        self.assertEqual(len(AB.active_columns(y1)), 14)
        self.assertEqual(AB.search(y1, 25), [])


if __name__ == "__main__":
    unittest.main()
