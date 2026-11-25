# Copyright 2026 Munim, Inc.
# SPDX-License-Identifier: Apache-2.0
# Made with AI agents working in the name of MV2 of Munim, Inc.
"""End-to-end checks of the 5-round 67-active-S-box characteristics (RESULTS_EXT5_V2.md).

Uses the published 4-round characteristics as data (data/third_party, MIT; see
THIRD_PARTY_NOTICES.md): L. Sotomayor's two 41-active ones (ascon-41-trail v1.0.0,
weights 125 and 140) and N. Otoi's 42-active one (ascon-trails v1.1).

1. Every published characteristic passes our own formula-free check_trail with its
   published profile.
2. All three share one tail up to rotation: the same round-2 output, round 3 and
   round-4 input (rotations by 26 and 47 bits).
3. The full 5-round characteristic in ext5_full_w125.json (Sotomayor's rounds 1-3
   unchanged) passes check_trail with profile 14-11-9-7-26 = 67.
4. The same suffix, rotated by 26 bits, extends the weight-140 characteristic to a
   second, different 67 (14-11-9-7-26).
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
AE = _load("ascon_extend")

TP = os.path.join(_HERE, "data", "third_party")


def load_trail(path):
    with open(path, encoding="utf-8") as f:
        return AE.parse_trail_obj(json.load(f))


class TestFullChain(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.w125 = load_trail(os.path.join(TP, "ascon-41-trail", "ascon_p4_41active_w125.json"))
        cls.w140 = load_trail(os.path.join(TP, "ascon-41-trail", "ascon_p4_41active_w140.json"))
        cls.otoi = load_trail(os.path.join(TP, "ascon-trails", "ascon_4r_42active.json"))
        cls.full = load_trail(os.path.join(_HERE, "ext5_full_w125.json"))

    def test_published_profiles(self):
        self.assertEqual(AM.check_trail(self.w125), [14, 11, 9, 7])
        self.assertEqual(AM.check_trail(self.w140), [14, 11, 9, 7])
        self.assertEqual(AM.check_trail(self.otoi), [15, 11, 9, 7])
        self.assertNotEqual(self.w125[0], self.w140[0])

    def test_shared_tail_up_to_rotation(self):
        # Sotomayor w140 = w125 rotated by 26 bits (bit j -> j + 38) from the round-2 output on
        self.assertEqual(AM.rotate_state(self.w125[1][1], 26), self.w140[1][1])
        self.assertEqual(AM.rotate_trail(self.w125[2:], 26), list(self.w140[2:]))
        # Otoi 42 = w125 rotated by 47 bits (bit j -> j + 17) from the round-2 output to round-4 input
        self.assertEqual(AM.rotate_state(self.w125[1][1], 47), self.otoi[1][1])
        self.assertEqual(AM.rotate_trail(self.w125[2:3], 47), list(self.otoi[2:3]))
        self.assertEqual(AM.rotate_state(self.w125[3][0], 47), self.otoi[3][0])

    def test_full_w125_five_rounds(self):
        self.assertEqual(len(self.full), 5)
        self.assertEqual(list(self.full[:3]), list(self.w125[:3]))
        self.assertEqual(self.full[3][0], self.w125[3][0])
        counts = AM.check_trail(self.full)
        self.assertEqual(counts, [14, 11, 9, 7, 26])
        self.assertEqual(sum(counts), 67)
        diff = tuple(a ^ b for a, b in zip(self.full[3][1], self.w125[3][1]))
        self.assertEqual(AE.active_columns(diff), [21])
        self.assertEqual(self.full[4][1], AE.next_round_output(self.full[4][0]))
        with open(os.path.join(_HERE, "ext5_full_w125.json"), encoding="utf-8") as f:
            meta = json.load(f)
        self.assertEqual(meta["per_round"], counts)
        self.assertEqual(meta["active"], 67)

    def test_full_w125_suffix_matches_ext5_v1(self):
        with open(os.path.join(_HERE, "ext5_w125_suffix.json"), encoding="utf-8") as f:
            obj = json.load(f)
        h = lambda ws: tuple(int(w, 16) for w in ws)  # noqa: E731
        self.assertEqual(self.full[3][1], h(obj["round4_out_new"]))
        self.assertEqual(self.full[4][0], h(obj["round5_in"]))

    def test_w140_second_67(self):
        suffix = AM.rotate_trail(self.full[3:], 26)
        self.assertEqual(suffix[0][0], self.w140[3][0])
        chain = list(self.w140[:3]) + suffix
        self.assertEqual(AM.check_trail(chain), [14, 11, 9, 7, 26])
        self.assertNotEqual(chain[0], self.full[0])

    def test_records_file(self):
        with open(os.path.join(_HERE, "ext5_records.json"), encoding="utf-8") as f:
            rec = json.load(f)
        five = {r["label"]: r["active"] for r in rec["five_round_best"]}
        self.assertEqual(min(five.values()), 67)
        self.assertEqual(rec["profiles"]["this_w125"], AM.check_trail(self.full))
        self.assertEqual(rec["profiles"]["otoi_5r"][:4], AM.check_trail(self.otoi))


if __name__ == "__main__":
    unittest.main()
