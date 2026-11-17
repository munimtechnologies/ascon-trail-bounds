# Copyright 2026 Munim, Inc.
# SPDX-License-Identifier: Apache-2.0
# Made with AI agents working in the name of MV2 of Munim, Inc.
"""Tests for the grading logic of run_bounds.py (no SAT solver needed)."""

import importlib.util
import os
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location("run_bounds", os.path.join(_HERE, "run_bounds.py"))
RB = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(RB)


def _calibrated():
    return {(1, 0): {"status": "UNSAT"}, (1, 1): {"status": "SAT", "total_active": 1},
            (2, 3): {"status": "UNSAT"}, (2, 4): {"status": "SAT", "total_active": 4},
            (3, 14): {"status": "UNSAT"}, (3, 15): {"status": "SAT", "total_active": 15}}


class TestGrade(unittest.TestCase):
    def test_all_timeouts_after_calibration(self):
        g = RB.grade(_calibrated())
        self.assertTrue(g["model_calibrated"])
        self.assertTrue(g["rows"][3]["verdict"].startswith("inconclusive"))
        self.assertTrue(g["rows"][4]["verdict"].startswith("inconclusive"))

    def test_new_bound(self):
        res = _calibrated()
        res[(4, 35)] = {"status": "UNSAT"}
        res[(4, 36)] = {"status": "UNSAT"}
        g = RB.grade(res)
        self.assertTrue(g["rows"][3]["verdict"].startswith("held"))
        self.assertTrue(g["rows"][4]["verdict"].startswith("NEW (solver result)"))

    def test_record_trail_and_contradiction(self):
        res = _calibrated()
        res[(4, 36)] = {"status": "SAT", "total_active": 36}
        self.assertTrue(RB.grade(res)["rows"][4]["verdict"].startswith("NEW RECORD TRAIL"))
        res[(4, 36)] = {"status": "SAT", "total_active": 35}
        self.assertTrue(RB.grade(res)["rows"][4]["verdict"].startswith("CONTRADICTS"))
        res[(4, 35)] = {"status": "SAT", "total_active": 35}
        self.assertTrue(RB.grade(res)["rows"][3]["verdict"].startswith("CONTRADICTS"))

    def test_failed_calibration_blocks_claims(self):
        res = _calibrated()
        res[(3, 14)] = {"status": "SAT", "total_active": 14}
        res[(4, 36)] = {"status": "UNSAT"}
        g = RB.grade(res)
        self.assertFalse(g["model_calibrated"])
        self.assertTrue(g["rows"][4]["verdict"].startswith("NOT GRADED"))

    def test_lanes_cover_prereg_tasks(self):
        tasks = [t for lane in RB.LANES for t in lane]
        for t in ((1, 0), (1, 1), (2, 3), (2, 4), (3, 14), (3, 15), (4, 35), (4, 36)):
            self.assertIn(t, tasks)


if __name__ == "__main__":
    unittest.main()
