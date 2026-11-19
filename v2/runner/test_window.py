"""Tests for the runner's window check (`window.py`). Standard library only; no clock or network needed.

    python3 -m unittest v2/runner/test_window.py

Each test pins a zone with TZ and builds its instant in that zone, so the result does not depend on where it runs.
"""

import copy
import os
import sys
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import window  # noqa: E402

GO, WAIT, REFUSED = 0, 1, 2


def at(zone, y, mo, d, h, mi):
    """The epoch instant of a wall-clock time in `zone` (TZ is left set to `zone`)."""
    os.environ["TZ"] = zone
    time.tzset()
    return time.mktime((y, mo, d, h, mi, 0, 0, 0, -1))


def cfg_with_window(start, end):
    cfg = copy.deepcopy(window.CFG)
    cfg["home"]["window"] = {"start": start, "end": end}
    cfg["clock"]["max_ntp_offset_seconds"] = 1.0
    return cfg


class Window(unittest.TestCase):
    def setUp(self):
        self._tz = os.environ.get("TZ")
        self.cfg = cfg_with_window("00:00", "06:00")

    def tearDown(self):
        if self._tz is None:
            os.environ.pop("TZ", None)
        else:
            os.environ["TZ"] = self._tz
        time.tzset()

    def decide(self, ts, minutes=60, ntp=0.01, arm="home", cfg=None):
        return window.decide(arm, minutes, ntp, ts=ts, cfg=cfg or self.cfg)

    # -- what any arm gets
    def test_testbed_runs_at_any_time(self):
        noon = at("America/Mexico_City", 2026, 11, 19, 12, 0)
        self.assertEqual(self.decide(noon, arm="testbed", ntp=None)[0], GO)

    def test_unknown_arm_is_refused(self):
        self.assertEqual(self.decide(at("UTC", 2026, 11, 19, 1, 0), arm="lab")[0], REFUSED)

    def test_implausible_lengths_are_refused(self):
        night = at("UTC", 2026, 11, 19, 1, 0)
        self.assertEqual(self.decide(night, minutes=0)[0], REFUSED)
        self.assertEqual(self.decide(night, minutes=24 * 60 + 1)[0], REFUSED)

    # -- the clock
    def test_ntp_unknown_or_off_waits(self):
        night = at("UTC", 2026, 11, 19, 1, 0)
        self.assertEqual(self.decide(night, ntp=None)[0], WAIT)
        self.assertEqual(self.decide(night, ntp=1.5)[0], WAIT)
        self.assertEqual(self.decide(night, ntp=-1.5)[0], WAIT)
        self.assertEqual(self.decide(night, ntp=-0.5)[0], GO)

    def test_records_zone_and_offset(self):
        code, out = self.decide(at("America/Mexico_City", 2026, 11, 19, 1, 0))
        self.assertEqual(code, GO)
        self.assertEqual(out["zone"], "CST")
        self.assertEqual(out["utc_offset"], "-0600")
        self.assertEqual(out["decision"], "go")

    # -- the window, 00:00-06:00
    def test_inside(self):
        self.assertEqual(self.decide(at("UTC", 2026, 11, 19, 1, 0))[0], GO)

    def test_edges(self):
        self.assertEqual(self.decide(at("UTC", 2026, 11, 19, 0, 0))[0], GO)       # starts at the opening
        self.assertEqual(self.decide(at("UTC", 2026, 11, 19, 5, 0))[0], GO)       # ends exactly at the close
        self.assertEqual(self.decide(at("UTC", 2026, 11, 19, 5, 1))[0], WAIT)     # would end after it
        self.assertEqual(self.decide(at("UTC", 2026, 11, 18, 23, 59))[0], WAIT)   # before the opening

    def test_outside(self):
        self.assertEqual(self.decide(at("UTC", 2026, 11, 19, 12, 0))[0], WAIT)

    def test_window_crossing_midnight(self):
        cfg = cfg_with_window("22:00", "04:00")
        self.assertEqual(self.decide(at("UTC", 2026, 11, 19, 23, 0), cfg=cfg)[0], GO)
        self.assertEqual(self.decide(at("UTC", 2026, 11, 19, 1, 0), cfg=cfg)[0], GO)
        self.assertEqual(self.decide(at("UTC", 2026, 11, 19, 3, 0), cfg=cfg)[0], GO)      # 03:00 + 60 = 04:00
        self.assertEqual(self.decide(at("UTC", 2026, 11, 19, 3, 30), cfg=cfg)[0], WAIT)
        self.assertEqual(self.decide(at("UTC", 2026, 11, 19, 21, 30), cfg=cfg)[0], WAIT)
        self.assertEqual(self.decide(at("UTC", 2026, 11, 19, 12, 0), cfg=cfg)[0], WAIT)

    # -- daylight saving: the offset may not change while a job runs, in any zone
    def test_autumn_night_waits(self):
        # America/Los_Angeles leaves daylight time at 02:00 on 2026-11-01. 01:30 happens twice that night, so the
        # job starts at 00:30 (daylight time, unambiguous) and runs two hours, across the change.
        code, out = self.decide(at("America/Los_Angeles", 2026, 11, 1, 0, 30), minutes=120)
        self.assertEqual(code, WAIT)
        self.assertIn("daylight", out["why"])

    def test_spring_night_waits(self):
        # America/Los_Angeles enters daylight time at 02:00 on 2027-03-14.
        self.assertEqual(self.decide(at("America/Los_Angeles", 2027, 3, 14, 1, 30))[0], WAIT)

    def test_same_night_after_the_change_runs(self):
        self.assertEqual(self.decide(at("America/Los_Angeles", 2026, 11, 1, 3, 0))[0], GO)

    def test_zone_without_daylight_saving_never_waits_for_it(self):
        self.assertEqual(self.decide(at("America/Mexico_City", 2026, 11, 1, 1, 30))[0], GO)


if __name__ == "__main__":
    unittest.main()
