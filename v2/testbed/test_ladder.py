"""Tests for study 2's ladders and S1's gate check. Standard library only, no machines needed.

    python3 -m unittest v2/testbed/test_ladder.py
"""

import math
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ladder  # noqa: E402
import netbed2  # noqa: E402
import plan  # noqa: E402  (study 1's, on the path through ladder)


class Ladder(unittest.TestCase):
    def test_500_is_study_1_exactly(self):
        self.assertEqual([r.target_rtt_ms for r in ladder.responders(500)],
                         [r.target_rtt_ms for r in plan.RESPONDERS])
        self.assertEqual(ladder.ladder(500), (1.0, 5.0, 25.0, 100.0, 500.0))

    def test_1_is_flat_at_the_anchor(self):
        self.assertEqual(set(ladder.ladder(1)), {500.0})

    def test_slowest_is_fixed(self):
        for d in ladder.DISPERSIONS:
            self.assertEqual(ladder.ladder(d)[-1], 500.0)

    def test_dispersion_is_what_it_says(self):
        for d in ladder.DISPERSIONS:
            self.assertTrue(math.isclose(ladder.achieved_dispersion(d), d, rel_tol=0.01), d)

    def test_levels_rise(self):
        for d in (5, 50, 500):
            lv = ladder.ladder(d)
            self.assertTrue(all(a < b for a, b in zip(lv, lv[1:])), lv)

    def test_agreed_values(self):
        # The table JC chose on 2026-11-18, to the rounding shown there.
        self.assertEqual([round(x) for x in ladder.ladder(5)], [100, 152, 230, 330, 500])
        self.assertEqual([round(x) for x in ladder.ladder(50)], [10, 28, 76, 182, 500])

    def test_composition_is_study_1s(self):
        for d in ladder.DISPERSIONS:
            for new, old in zip(ladder.responders(d), plan.RESPONDERS):
                self.assertEqual((new.name, new.role, new.loss_percent, new.answers_icmp, new.tcp_ports),
                                 (old.name, old.role, old.loss_percent, old.answers_icmp, old.tcp_ports))

    def test_machines_group_as_study_1(self):
        self.assertEqual([(n, [r.name for r in rs]) for n, rs in ladder.machines(50)],
                         [(n, [r.name for r in rs]) for n, rs in plan.machines()])

    def test_unknown_dispersion_refused(self):
        with self.assertRaises(ValueError):
            ladder.ladder(10)

    def test_template_is_pinned(self):
        pin = netbed2.image_pin()
        self.assertRegex(pin["location"], r"/release-\d{8}/")
        self.assertRegex(pin["digest"], r"^sha256:[0-9a-f]{64}$")


def applied(d):
    rs = []
    for i, r in enumerate(ladder.responders(d)):
        rs.append({"name": r.name, "address": f"192.168.64.{i + 4}", "mac": f"52:55:55:00:00:{i:02x}",
                   "designed_rtt_ms": r.target_rtt_ms, "role": r.role, "answers_icmp": r.answers_icmp,
                   "tcp_ports": list(r.tcp_ports)})
    return rs


def measured(responders, error):
    return [{"name": r["name"], "unmeasurable": True} if netbed2.probe_method(r) == "none"
            else {"name": r["name"], "error_percent": error} for r in responders]


def macs(responders):
    return [{"name": r["name"], "mac_in_neighbour_table": r["mac"], "mac_reported_by_guest": r["mac"]}
            for r in responders]


class Gate(unittest.TestCase):
    def test_passes_inside_tolerance(self):
        rs = applied(50)
        self.assertEqual(netbed2.gate_failures(50, rs, [measured(rs, 9.9)] * 3, macs(rs)), [])

    def test_fails_outside_tolerance(self):
        rs = applied(50)
        f = netbed2.gate_failures(50, rs, [measured(rs, 9.9), measured(rs, -10.5), measured(rs, 1)], macs(rs))
        self.assertTrue(f and all("run 2" in x for x in f), f)

    def test_unreachable_fails(self):
        rs = applied(5)
        run = measured(rs, 0)
        run[0] = {"name": rs[0]["name"], "unreachable": True}
        self.assertIn("run 1: r01 unreachable", netbed2.gate_failures(5, rs, [run], macs(rs)))

    def test_wrong_ladder_fails(self):
        rs = applied(5)
        self.assertTrue(netbed2.gate_failures(50, rs, [measured(rs, 0)], macs(rs)))

    def test_collapsed_or_missing_macs_fail(self):
        rs = applied(1)
        rows = macs(rs)
        rows[1]["mac_in_neighbour_table"] = rows[0]["mac_in_neighbour_table"]
        self.assertTrue(netbed2.gate_failures(1, rs, [measured(rs, 0)], rows))
        rows = macs(rs)
        rows[3]["mac_in_neighbour_table"] = None
        self.assertTrue(netbed2.gate_failures(1, rs, [measured(rs, 0)], rows))

    def test_silent_host_is_not_measured(self):
        silent = [r for r in applied(500) if netbed2.probe_method(r) == "none"]
        self.assertEqual([r["name"] for r in silent], ["r08"])


class HostRecords(unittest.TestCase):
    ARP = ("? (192.168.64.1) at ca:80:6d:74:ed:64 on bridge100 ifscope permanent [bridge]\n"
           "? (192.168.64.2) at 52:55:55:ab:97:9 on bridge100 ifscope [bridge]\n"
           "? (192.168.64.3) at (incomplete) on bridge100 ifscope [bridge]\n")

    def test_arp_parsed_and_normalised_like_study_1(self):
        table = netbed2.parse_arp(self.ARP)
        self.assertEqual(table["192.168.64.2"], "52:55:55:ab:97:09")
        self.assertNotIn("192.168.64.3", table)
        self.assertEqual(len(table), 2)

    def test_small_corrections_pass(self):
        entries = [{"name": "r01", "designed_rtt_ms": 1.0, "netem_delay_ms": 0.8835},
                   {"name": "r09", "designed_rtt_ms": 500.0, "netem_delay_ms": 499.789}]
        self.assertEqual(netbed2.large_corrections(entries), [])

    def test_the_10_ms_artefact_is_caught(self):
        # d500.json of 2026-11-19: r07 calibrated to 89.87 ms for a 100 ms design.
        entries = [{"name": "r07", "designed_rtt_ms": 100.0, "netem_delay_ms": 89.8705},
                   {"name": "r05", "designed_rtt_ms": 500.0, "netem_delay_ms": 489.752}]
        self.assertEqual(netbed2.large_corrections(entries), ["r07", "r05"])


if __name__ == "__main__":
    unittest.main()
