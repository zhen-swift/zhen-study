"""Recompute `REPRODUCIBILITY.md`'s claims from the NDJSON, and say which hold.

`REPRODUCIBILITY.md` ends with a table asserting what the collection contains.  A table
is a claim about a file, and a claim about a file is checkable.  This module checks
every line of it against `data/runs.ndjson` and the stratum sidecar, prints a verdict
per claim, and exits non-zero if any of them fail.

It also answers two questions the table raises and does not settle:

* **Which apparatus commit did each block run under, and did any of them move the
  measurement path?**  Seven commits appear in the data.  The check diffs the frozen
  packages and the harness across all seven and diffs the testbed manifests field by
  field, because a manifest whose declared design moved between rebuilds is a
  between-block confound correlated with time.

* **Is any rebuild's calibration materially worse than the others?**  The worst
  final-round error per rebuild is recomputed from the committed manifests and held
  against the 10% tolerance `PHASE0.md` gate 0.1 fixed.

Run it:

    python3 analysis/verify.py
    python3 analysis/verify.py --artifact-root /path/to/collection/worktree/Study
"""

from __future__ import annotations

import argparse
import collections
import datetime as dt
import json
import subprocess
from pathlib import Path

import strata as strata_module  # noqa: E402  (same directory)

HERE = Path(__file__).resolve().parent
STUDY = HERE.parent
REPO = STUDY.parent

# ── the claims, as `REPRODUCIBILITY.md` states them ───────────────────────────────
CLAIMED = {
    "records": 1580,
    "schema_version": 2,
    "exclusions": 2,
    "exclusion_reasons": {"host_asleep": 2},
    "exclusion_rate": 0.0013,
    "exclusion_ceiling": 0.05,
    "partial_blocks": [19, 68],
    "complete_blocks": 120,
    "blocks_per_stratum": 30,
    "distinct_days": 10,
    "conditions": 13,
    "runs_per_condition_range": (120, 122),
    "warm": 1458,
    "cold": 122,
    "netsanity_sha256": "b4220600b75acd10b46d033cb315a9e5c035021494a93afe381e0014eff6e4ed",
    "nmap_sha256": "b522bd2f0ae39f389fcaa0263c8170938b6c4e33f9fda8c849934a05ea0b2f62",
    "runs_by_apparatus_commit": {
        "47113b8": 65, "1bf4371": 192, "d286272": 221, "a77783a": 413,
        "5ec05e4": 78, "cde9020": 598, "6273119": 13,
    },
    "flagged_blocks": [36, 74, 93],
    "window_start_local": "2026-09-13 18:19",
    "window_end_local": "2026-09-22 00:14",
    "cooldown_seconds": 10.0,
    "calibration_tolerance_percent": 10.0,
    "frozen_tag": "study/binary-2026-09-12b",
}

#: The identity of the instrument: the fields that say what the testbed *is*, as
#: against the achieved column, which says how well it was hitting its marks that day.
MANIFEST_IDENTITY = ("name", "address", "mac", "target_rtt_ms", "loss_percent",
                     "role", "answers_icmp", "tcp_ports")


class Ledger:
    def __init__(self) -> None:
        self.rows: list[tuple[str, bool, str]] = []

    def check(self, claim: str, ok: bool, detail: str) -> bool:
        self.rows.append((claim, ok, detail))
        return ok

    @property
    def failures(self) -> list[tuple[str, bool, str]]:
        return [row for row in self.rows if not row[1]]

    def render(self) -> str:
        width = max(len(c) for c, _, _ in self.rows)
        lines = []
        for claim, ok, detail in self.rows:
            lines.append(f"  {'OK  ' if ok else 'FAIL'}  {claim:<{width}}  {detail}")
        return "\n".join(lines)


def git(*args: str) -> str | None:
    try:
        out = subprocess.run(["git", "-C", str(REPO), *args],
                             capture_output=True, text=True, check=False)
    except OSError:
        return None
    return out.stdout if out.returncode == 0 else None


def verify_records(records: list[dict], sidecar: dict, ledger: Ledger,
                   artifact_root: Path | None) -> None:
    n = len(records)
    ledger.check("record count 1,580", n == CLAIMED["records"], f"{n}")

    versions = collections.Counter(r["schema_version"] for r in records)
    ledger.check("all schema 2", set(versions) == {CLAIMED["schema_version"]},
                 f"{dict(versions)}")

    excluded = [r for r in records if r.get("exclusion")]
    reasons = collections.Counter(r["exclusion"]["reason"] for r in excluded)
    ledger.check("2 exclusions, both host_asleep",
                 len(excluded) == CLAIMED["exclusions"]
                 and dict(reasons) == CLAIMED["exclusion_reasons"],
                 f"{len(excluded)} {dict(reasons)}")
    rate = len(excluded) / n
    ledger.check("exclusion rate 0.13%, under the 5% ceiling",
                 round(rate, 4) == CLAIMED["exclusion_rate"]
                 and rate < CLAIMED["exclusion_ceiling"],
                 f"{rate:.4%} ({len(excluded)}/{n})")

    blocks = collections.Counter(r["block_id"] for r in records)
    partial = sorted(b for b, c in blocks.items() if c < 13)
    ledger.check("partial blocks 19 and 68, counted by no census",
                 partial == CLAIMED["partial_blocks"], f"{partial}")

    counts = sidecar["complete_blocks_per_stratum"]
    ledger.check("120 complete blocks, 30 per stratum",
                 sidecar["complete_blocks"] == CLAIMED["complete_blocks"]
                 and set(counts.values()) == {CLAIMED["blocks_per_stratum"]},
                 f"{sidecar['complete_blocks']} blocks, {counts}")
    days = sorted({e["local_day"] for e in sidecar["blocks"].values()})
    ledger.check("10 distinct days", len(days) == CLAIMED["distinct_days"],
                 f"{len(days)}: {days[0]} to {days[-1]}")

    per_condition = collections.Counter(r["condition_id"] for r in records)
    low, high = CLAIMED["runs_per_condition_range"]
    ledger.check("13 conditions, 120 to 122 runs each",
                 len(per_condition) == CLAIMED["conditions"]
                 and all(low <= v <= high for v in per_condition.values()),
                 f"{len(per_condition)} conditions, {min(per_condition.values())}"
                 f"-{max(per_condition.values())} runs")

    cache = collections.Counter(r["cache_state"] for r in records)
    cold_per_condition = collections.Counter(
        r["condition_id"] for r in records if r["cache_state"] == "cold")
    mean_cold = sum(cold_per_condition.values()) / len(cold_per_condition)
    ledger.check("1,458 warm and 122 cold",
                 cache.get("warm") == CLAIMED["warm"] and cache.get("cold") == CLAIMED["cold"],
                 f"{dict(cache)}; {mean_cold:.1f} cold per condition "
                 f"(range {min(cold_per_condition.values())}-{max(cold_per_condition.values())})")

    for label, key, want in (
        ("netsanity sha256 constant", "netsanity_sha256", CLAIMED["netsanity_sha256"]),
        ("nmap sha256 constant", "nmap_sha256", CLAIMED["nmap_sha256"]),
    ):
        seen = collections.Counter(r["provenance"][key] for r in records)
        ledger.check(label, set(seen) == {want},
                     f"{len(seen)} distinct, {next(iter(seen))[:8]}...")

    dirty = collections.Counter(r["provenance"]["git_dirty"] for r in records)
    ledger.check("git_dirty false throughout", set(dirty) == {False}, f"{dict(dirty)}")

    oracle = collections.Counter(r["oracle"]["status"] for r in records)
    ledger.check("oracles agree on all 1,580", set(oracle) == {"agree"}, f"{dict(oracle)}")
    capture = collections.Counter(r["capture"]["status"] for r in records)
    wire = collections.Counter(r["capture"]["wire"]["status"] for r in records)
    ledger.check("captures ok on all 1,580",
                 set(capture) == {"ok"} and set(wire) == {"ok"},
                 f"capture {dict(capture)}, wire summary {dict(wire)}")

    permission = collections.Counter(
        r["provenance"]["local_network_permission"]["verdict"] for r in records)
    ledger.check("Local Network permission granted, asserted per run",
                 set(permission) == {"granted"}, f"{dict(permission)}")

    cooldown = collections.Counter(r["covariates"]["cooldown_seconds"] for r in records)
    ledger.check("cooldown 10 s on every run",
                 set(cooldown) == {CLAIMED["cooldown_seconds"]}, f"{dict(cooldown)}")

    commits = collections.Counter(r["provenance"]["git_commit"][:7] for r in records)
    ledger.check("runs per apparatus commit",
                 dict(commits) == CLAIMED["runs_by_apparatus_commit"],
                 f"{dict(sorted(commits.items(), key=lambda kv: -kv[1]))}")

    # Every artefact the file points at.  The recorded paths are absolute and inside
    # the collection worktree; `--artifact-root` remaps them so the check can run on a
    # machine that has the release bundle at a different path.
    referenced = []
    for record in records:
        referenced.append(record["stdout_path"])
        referenced.append(record["stderr_path"])
        referenced.append(record["capture"]["path"])
    missing, checked = [], 0
    for path in referenced:
        if path is None:
            missing.append("(null path)")
            continue
        target = Path(path)
        if artifact_root is not None:
            # …/Study/data/raw/x → <root>/data/raw/x
            parts = target.parts
            if "data" in parts:
                target = artifact_root / Path(*parts[parts.index("data"):])
        if target.exists():
            checked += 1
        else:
            missing.append(str(target))
    ledger.check("every stdout, stderr and capture path exists",
                 not missing,
                 f"{checked}/{len(referenced)} present"
                 + (f"; first missing {missing[0]}" if missing else ""))

    offset = sidecar["collection_utc_offset_seconds"]
    first = min(r["started_at_unix"] for r in records)
    last = max(r["finished_at_unix"] for r in records)
    start_local = strata_module.local(first, offset).strftime("%Y-%m-%d %H:%M")
    end_local = strata_module.local(last, offset).strftime("%Y-%m-%d %H:%M")
    ledger.check("window 2026-09-13 18:19 to 2026-09-22 00:14 local",
                 start_local == CLAIMED["window_start_local"]
                 and end_local == CLAIMED["window_end_local"],
                 f"{start_local} to {end_local} (UTC{sidecar['collection_utc_offset']})")
    span_days = (dt.datetime.fromtimestamp(last, dt.timezone.utc)
                 - dt.datetime.fromtimestamp(first, dt.timezone.utc)).total_seconds() / 86400
    ledger.check("at least seven consecutive days", span_days >= 7,
                 f"{span_days:.2f} days")

    ac = collections.Counter(r["provenance"]["on_ac_power"] for r in records)
    flagged = sorted({r["block_id"] for r in records if r["block_id"] in CLAIMED["flagged_blocks"]})
    ledger.check("on_ac_power true on every record, including the three flagged blocks",
                 set(ac) == {True} and flagged == CLAIMED["flagged_blocks"],
                 f"{dict(ac)}; flagged blocks present: {flagged} — the record does not "
                 f"show the battery runs and cannot")


def verify_apparatus(ledger: Ledger, commits: list[str]) -> dict:
    """Did any apparatus commit move the measurement path, or the instrument's design?"""
    findings: dict = {"commits": {}, "manifest_identity_changes": [], "calibration": {}}

    have_git = git("rev-parse", "--git-dir") is not None
    if not have_git:
        ledger.check("apparatus commits inspected", False,
                     "no git repository here; run this inside a clone")
        return findings

    # 1. The frozen packages, against the tag the appendix cites.
    diffs = {}
    for commit in commits:
        out = git("diff", "--stat", CLAIMED["frozen_tag"], commit, "--",
                  "Packages/netsanity-core", "Packages/netsanity-cli")
        diffs[commit] = None if out is None else out.strip()
    ledger.check("frozen packages byte-identical to the tag at all seven commits",
                 all(v == "" for v in diffs.values()),
                 f"{sum(1 for v in diffs.values() if v == '')}/{len(commits)} empty diffs")

    # 2. The measurement path itself: harness and analysis code.
    path_moves = {}
    for earlier, later in zip(commits, commits[1:]):
        out = git("diff", "--name-only", earlier, later, "--",
                  "Study/harness", "Study/analysis", "Packages")
        path_moves[f"{earlier}..{later}"] = [p for p in (out or "").split() if p]
    moved = {k: v for k, v in path_moves.items() if v}
    ledger.check("no apparatus commit changed the harness, the analysis or the product",
                 not moved, f"{len(moved)} of {len(path_moves)} steps touched code"
                 + (f": {moved}" if moved else ""))

    # 3. What each commit did change.
    for earlier, later in zip(commits, commits[1:]):
        out = git("diff", "--name-only", earlier, later)
        findings["commits"][f"{earlier}..{later}"] = sorted(p for p in (out or "").split() if p)

    # 4. The testbed manifests, field by field.
    manifests = {}
    for commit in commits:
        blob = git("show", f"{commit}:Study/testbed/manifest.json")
        if blob is None:
            ledger.check(f"manifest readable at {commit}", False, "git show failed")
            return findings
        manifests[commit] = json.loads(blob)

    def identity(manifest: dict) -> list[dict]:
        return sorted(({k: r[k] for k in MANIFEST_IDENTITY} for r in manifest["responders"]),
                      key=lambda r: r["name"])

    base = identity(manifests[commits[0]])
    base_shape = (manifests[commits[0]]["composition"],
                  manifests[commits[0]]["declared_web_fraction"],
                  manifests[commits[0]]["segment"])
    for commit in commits[1:]:
        here = identity(manifests[commit])
        shape = (manifests[commit]["composition"],
                 manifests[commit]["declared_web_fraction"],
                 manifests[commit]["segment"])
        if here != base or shape != base_shape:
            findings["manifest_identity_changes"].append(commit)
    ledger.check("testbed identity unchanged across all seven rebuilds",
                 not findings["manifest_identity_changes"],
                 "addresses, hardware addresses, roles, target RTTs, loss and open "
                 "ports identical at every commit"
                 if not findings["manifest_identity_changes"]
                 else f"moved at {findings['manifest_identity_changes']}")

    # 5. Calibration: worst final-round error per rebuild, against the 10% tolerance.
    worst_overall = 0.0
    for commit in commits:
        errors = {r["name"]: abs(r["calibration"][-1]["error_percent"])
                  for r in manifests[commit]["responders"]}
        name = max(errors, key=errors.get)
        findings["calibration"][commit] = {
            "worst_responder": name,
            "worst_error_percent": errors[name],
            "achieved_p50_ms": {r["name"]: r["achieved"]["p50"]
                                for r in manifests[commit]["responders"]},
            "target_rtt_ms": {r["name"]: r["target_rtt_ms"]
                              for r in manifests[commit]["responders"]},
        }
        worst_overall = max(worst_overall, errors[name])
    ledger.check("every rebuild inside the 10% calibration tolerance",
                 worst_overall <= CLAIMED["calibration_tolerance_percent"],
                 f"worst {worst_overall:.2f}% at "
                 f"{max(findings['calibration'], key=lambda c: findings['calibration'][c]['worst_error_percent'])}")
    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--runs", type=Path, default=STUDY / "data" / "runs.ndjson")
    parser.add_argument("--sidecar", type=Path, default=HERE / "strata.json")
    parser.add_argument("--artifact-root", type=Path, default=None,
                        help="the Study/ directory holding data/raw and data/captures, "
                             "if it is not where the records say it is")
    parser.add_argument("--json", type=Path, default=None,
                        help="also write the findings as JSON")
    args = parser.parse_args(argv)

    records = [json.loads(line) for line in open(args.runs, encoding="utf-8") if line.strip()]
    sidecar = json.loads(args.sidecar.read_text())
    ledger = Ledger()

    ledger.check("the sidecar was built from this runs.ndjson",
                 sidecar["source_sha256"] ==
                 __import__("hashlib").sha256(args.runs.read_bytes()).hexdigest(),
                 sidecar["source_sha256"][:12] + "...")

    verify_records(records, sidecar, ledger, args.artifact_root)

    commits = sorted(
        {r["provenance"]["git_commit"][:7] for r in records},
        key=lambda c: min(r["started_at_unix"] for r in records
                          if r["provenance"]["git_commit"].startswith(c)),
    )
    findings = verify_apparatus(ledger, commits)

    print("REPRODUCIBILITY.md, recomputed from data/runs.ndjson")
    print(ledger.render())
    print()
    print(f"{len(ledger.rows) - len(ledger.failures)}/{len(ledger.rows)} claims reconcile")
    for claim, _, detail in ledger.failures:
        print(f"  ! {claim}: {detail}")

    if args.json:
        args.json.write_text(json.dumps({
            "claims": [{"claim": c, "ok": ok, "detail": d} for c, ok, d in ledger.rows],
            "apparatus": findings,
            "apparatus_commit_order": commits,
        }, indent=1) + "\n")
    return 1 if ledger.failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
