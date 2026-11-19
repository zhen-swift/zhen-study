"""Study 2's harness: the parser, the records, the conditions and the generator. Stdlib only, Python 3.9.

    /usr/bin/python3 -m unittest v2/harness/test_harness.py

The fixtures are three artifacts the frozen binary wrote on the testbed (the S2 contract job, 2026-11-19): scan 4
(the default, cold, history read), scan 2 (`--reach learned --no-neighbor-watch`) and scan 1i0 (`--ipv6-window
0`). Testbed addresses only; no hardware address in any of them (unprivileged zhen on macOS 27).
"""

from __future__ import annotations

import json
import random
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import conditions as C  # noqa: E402
import generate as G  # noqa: E402
import record as R  # noqa: E402
import zhen as Z  # noqa: E402

FIX = HERE / "fixtures"


def fixture(name):
    return (FIX / f"g9-{name}.json").read_text()


class Parser(unittest.TestCase):
    def test_default_artifact_parses_without_warnings(self):
        p, w = Z.parse(fixture("4"))
        self.assertTrue(p["ok"])
        self.assertEqual(w, [])
        self.assertEqual(p["local"], ["192.168.64.1"])
        self.assertNotIn("192.168.64.1", p["addresses"])
        self.assertEqual(len(p["addresses"]), 7)
        self.assertEqual(p["reach"]["policy"], "history")
        self.assertEqual(p["discovery"]["stage"], "discovery")

    def test_learned_without_watch_matches_its_flags(self):
        flags = ("--reach", "learned", "--no-neighbor-watch")
        p, w = Z.parse(fixture("2"), flags=flags)
        self.assertEqual(w, [])
        self.assertFalse(p["neighbor_watch"]["enabled"])

    def test_ipv6_window_zero_matches(self):
        p, w = Z.parse(fixture("1i0"), flags=C.MATCHED)
        self.assertEqual(w, [])
        self.assertEqual(p["ipv6_window"]["policy"], "off")

    def test_flags_the_artifact_contradicts_are_warnings(self):
        _, w = Z.parse(fixture("4"), flags=C.MATCHED)        # scan 4 ran with the default window
        self.assertTrue(any("--ipv6-window 0" in x for x in w))
        _, w = Z.parse(fixture("4"), flags=("--reach", "learned"))
        self.assertTrue(any("--reach learned" in x for x in w))
        _, w = Z.parse(fixture("4"), flags=("--reach", "history", "--reach-percentile", "0.99"))
        self.assertTrue(any("--reach-percentile" in x for x in w))
        _, w = Z.parse(fixture("4"), flags=("--no-neighbor-watch",))
        self.assertTrue(any("watch" in x for x in w))

    def test_schema_and_version_drift_are_warnings(self):
        a = json.loads(fixture("4"))
        a["schema"] = 5
        a["run"]["tool"]["version"] = "0.9.0"
        del a["run"]["reach"]["history_samples"]
        _, w = Z.parse(json.dumps(a))
        self.assertIn("schema is 5, not 4", w)
        self.assertIn("run.tool.version is '0.9.0'", w)
        self.assertIn("run.reach.history_samples missing", w)

    def test_root_run_on_the_unprivileged_engine_is_a_warning(self):
        _, w = Z.parse(fixture("4"), privilege="root")
        self.assertIn("a root run reports the unprivileged engine", w)

    def test_unknown_discovery_source_is_a_warning(self):
        a = json.loads(fixture("4"))
        a["devices"][1]["discovered_via"] = ["telepathy"]
        _, w = Z.parse(json.dumps(a))
        self.assertTrue(any("telepathy" in x for x in w))

    def test_unparseable_is_not_an_empty_set(self):
        p, w = Z.parse("zhen: something went wrong\n")
        self.assertFalse(p["ok"])
        self.assertTrue(p["error"])
        p, _ = Z.parse("{}")
        self.assertFalse(p["ok"])

    def test_stub_goes_through_the_real_parser(self):
        flags = C.BY_ID["p2.zhen.root"].flags
        p, w = Z.parse(Z.stub_artifact(["192.168.64.2"], privilege="root", flags=flags), privilege="root", flags=flags)
        self.assertTrue(p["ok"])
        self.assertEqual(w, [])
        self.assertEqual(p["addresses"], ["192.168.64.2"])

    def test_sudo_refusal_is_recognised(self):
        self.assertTrue(Z.sudo_refused(1, "sudo: a password is required\n"))
        self.assertFalse(Z.sudo_refused(0, "sudo: a password is required\n"))
        self.assertFalse(Z.sudo_refused(1, "zhen: bad flag\n"))


class Conditions(unittest.TestCase):
    def test_every_zhen_condition_has_its_own_store_and_is_discovery_only(self):
        for c in C.CONDITIONS:
            if c.tool == "zhen":
                self.assertIn(c.history, (C.EMPTY, C.PRIMED), c.id)
                self.assertIn("--discovery-only", c.argv())

    def test_every_nmap_matched_zhen_condition_closes_the_ipv6_window(self):
        for c in C.PHASE2:
            if c.tool == "zhen" and c.id != "p2.zhen.product":
                self.assertEqual(c.flags[-2:], C.MATCHED, c.id)
        self.assertNotIn("--ipv6-window", C.BY_ID["p2.zhen.product"].flags)

    def test_phase1_is_reach_by_history_unprivileged(self):
        self.assertEqual(len(C.PHASE1), 9 * 2)
        self.assertTrue(all(c.privilege == "user" and c.tool == "zhen" for c in C.PHASE1))

    def test_root_runs_through_sudo_n(self):
        self.assertEqual(C.BY_ID["p2.zhen.root"].argv()[:3], ["sudo", "-n", C.ZHEN])
        self.assertEqual(C.BY_ID["p2.nmap.root.T4"].argv(nmap_xml="x.xml")[:3], ["sudo", "-n", C.NMAP])
        self.assertEqual(C.BY_ID["p2.nmap.user.T4"].argv(nmap_xml="x.xml")[0], C.NMAP)

    def test_t2_every_fourth_block(self):
        ids = lambda i: {c.id for c in C.for_phase(2, block_index=i)}
        self.assertIn("p2.nmap.user.T2", ids(0))
        self.assertNotIn("p2.nmap.user.T2", ids(1))
        self.assertIn("p2.nmap.root.T2", ids(8))


class Records(unittest.TestCase):
    def run_record(self, **over):
        c = C.BY_ID["p2.zhen.default"]
        p, w = Z.parse(fixture("4"))
        r = {"schema_version": 1, "study": 2, "kind": "run", "phase": 2, "block_id": "b", "job": None,
             "dry_run": False, "written_at": "t", "run_id": "r", "index": 0, "condition": c.as_record(),
             "argv": c.argv(), "env": {"ZHEN_HISTORY": "/x"}, "cache_state": "cold", "history": {},
             "thermal": {}, "flush": None, "exit_status": 0, "wall_clock_seconds": 1.0,
             "wall_clock_source": "harness_monotonic", "started_at_unix": 0.0, "finished_at_unix": 1.0,
             "binary_sha256": "x", "parsed": p, "capture": {"status": "ok"}, "warnings": w, "stubbed": False,
             "exclusion": None}
        r.update(over)
        return r

    def test_valid_run(self):
        self.assertEqual(R.validate(self.run_record()), [])

    def test_invalid_runs(self):
        self.assertIn("a stubbed run outside a dry run", R.validate(self.run_record(stubbed=True)))
        self.assertIn("a zhen run without its own ZHEN_HISTORY", R.validate(self.run_record(env={})))
        self.assertIn("unparseable output without an exclusion",
                      R.validate(self.run_record(parsed={"ok": False})))
        self.assertIn("capture 'failed'", R.validate(self.run_record(capture={"status": "failed"})))
        self.assertIn("wall_clock_seconds is int", R.validate(self.run_record(wall_clock_seconds=1)))

    def test_append_refuses_invalid(self):
        with self.assertRaises(ValueError):
            R.append(Path("/nonexistent/never-written.ndjson"), self.run_record(kind="nonsense"))


class Generator(unittest.TestCase):
    config = {"phase1": {"blocks_per_cell": 20}, "phase2": {"blocks_per_cell": 30}}

    def test_phase2_cells_are_full_and_shuffled(self):
        js = G.jobs("phase2", 7, self.config)
        self.assertEqual(len(js), 4 * 2 * 30)
        cells = {}
        for j in js:
            a = j["argv"]
            key = (a[a.index("--dispersion") + 1], a[a.index("--flush") + 1])
            cells[key] = cells.get(key, 0) + 1
        self.assertEqual(set(cells.values()), {30})
        firsts = [j["argv"][j["argv"].index("--dispersion") + 1] for j in js[:16]]
        self.assertGreater(len(set(firsts)), 1, "dispersion batched")

    def test_same_seed_same_jobs(self):
        self.assertEqual(G.jobs("phase1", 3, self.config), G.jobs("phase1", 3, self.config))
        self.assertNotEqual(G.jobs("phase1", 3, self.config), G.jobs("phase1", 4, self.config))

    def test_jobs_are_runner_jobs_with_unique_blocks(self):
        js = G.jobs("phase1", 1, self.config)
        self.assertEqual(len(js), 4 * 20)
        self.assertEqual(len({j["argv"][j["argv"].index("--block") + 1] for j in js}), len(js))
        for j in js:
            self.assertEqual(set(j), {"id", "arm", "minutes", "argv", "env"})
            self.assertEqual(j["arm"], "testbed")
            self.assertEqual(j["argv"][0], "v2/harness/run_block.py")

    def test_dryrun_covers_every_condition(self):
        js = G.jobs("dryrun", 1, self.config)
        covered = set()
        for j in js:
            a = j["argv"]
            covered |= {c.id for c in C.for_phase(int(a[a.index("--phase") + 1]),
                                                   block_index=int(a[a.index("--block-index") + 1]))}
            self.assertIn("--dry-run", a)
        self.assertEqual(covered, set(C.BY_ID))


if __name__ == "__main__":
    unittest.main()
