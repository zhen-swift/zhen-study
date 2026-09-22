"""Derive each block's time-of-day stratum, and write it down beside the data.

`PROTOCOL.md` section 5 stratifies collection by time of day, and **no record in
`data/runs.ndjson` stores its stratum.**  `harness/collect.py` assigned strata with a
naive `datetime.now()` on the collection Mac (`census()` buckets
`datetime.fromtimestamp(block["at"]).hour`), and no field in the record carries a
timezone or a UTC offset.  Any analysis that re-derives the stratum from
`started_at_unix` therefore buckets by whatever timezone the *analysing* machine
happens to have.

That is not a small hazard.  The four strata are six-hour buckets, so a six-hour shift
permutes them cleanly: a reader six hours away gets identical per-stratum counts —
thirty in each — with every block relabelled, overnight becoming morning, and no
sanity check anywhere in the analysis fires.  `REPRODUCIBILITY.md` claims every number
is recomputable from the NDJSON alone, and this one is not.

This module closes the hole the only way that leaves the evidence intact: it does not
touch `runs.ndjson`.  It emits a derived sidecar, `strata.json`, carrying the block →
stratum map, the offset, and how the offset was established, and every stratified
number in the analysis reads the sidecar rather than the analysing machine's clock.

Run it:

    python3 analysis/strata.py                       # regenerate the sidecar
    python3 analysis/strata.py --check               # verify the committed sidecar
    python3 analysis/strata.py \\
        --driver-log /path/to/collect.log            # re-derive the offset from the log

Without `--driver-log` the offset is the documented constant below, which is what makes
the mapping reproducible on a machine that has neither the log nor the collection
Mac's timezone.  With it, the constant is re-derived from the artefact and the run
fails loudly if the two disagree.
"""

from __future__ import annotations

import argparse
import collections
import datetime as dt
import hashlib
import json
import re
import statistics
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
STUDY = HERE.parent
DEFAULT_RUNS = STUDY / "data" / "runs.ndjson"
DEFAULT_SIDECAR = HERE / "strata.json"

SIDECAR_SCHEMA = 1

# ── the constant, and where it comes from ─────────────────────────────────────────
#
# Established empirically from two independent artefacts, neither of them an
# assumption about where the machine is:
#
#   1. `Study/data/collect.log` in the collection worktree.  `collect.py`'s logger
#      stamps every line with a naive `datetime.now().isoformat()`, so each line is a
#      local wall-clock string.  Its 120 "block finished in Ns" lines each follow the
#      last record of a block, whose `finished_at_unix` is in the NDJSON.  Reading the
#      log stamp as if it were UTC and subtracting the record's epoch time gives
#      offset + write-lag on every one of the 120 anchors; the lag is 1.5 to 2.7 s and
#      the offset is -21600 s on all of them, with no drift across the ten-day window.
#
#   2. `git log` on the seven apparatus commits the data references.  Commit dates
#      carry the committer's offset verbatim, and all seven read `-0600`.  The
#      collection tag `47113b8` is dated 2026-09-13 17:45:38 -0600 against the driver
#      log's "2026-09-13T17:45:39  driver starting" — the same event, one second apart,
#      from two artefacts that do not share a writer.
#
# Both say UTC-06:00, constant for the whole window.  September 2026 contains no
# daylight-saving transition at that offset, and the anchors confirm it directly rather
# than by appeal to a timezone database.
COLLECTION_UTC_OFFSET_SECONDS = -21600
COLLECTION_UTC_OFFSET = "-06:00"

# `harness/collect.py` STRATA, reproduced here rather than imported.  The analysis may
# not import the harness's *driver* — HARNESS.md keeps collection and analysis apart —
# and these four boundaries are part of the frozen protocol, not a tunable.
STRATA: dict[str, tuple[int, int]] = {
    "overnight": (0, 6),
    "morning": (6, 12),
    "afternoon": (12, 18),
    "evening": (18, 24),
}

#: A block is complete when every live condition produced a record.  `collect.py`
#: counts 13; a block with fewer is partial and no census counts it.
LIVE_CONDITIONS = 13


def stratum_of_hour(hour: int) -> str:
    for name, (start, end) in STRATA.items():
        if start <= hour < end:
            return name
    raise AssertionError(f"no stratum contains hour {hour}")


def local(unix: float, offset_seconds: int = COLLECTION_UTC_OFFSET_SECONDS) -> dt.datetime:
    """The collection machine's local wall clock for an epoch time."""
    return dt.datetime.fromtimestamp(unix, dt.timezone.utc) + dt.timedelta(seconds=offset_seconds)


def read_runs(path: Path) -> list[dict]:
    with open(path, encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def blocks_from(records: list[dict]) -> dict[int, dict]:
    """One entry per block id, keyed exactly the way `collect.census()` keys it.

    `census()` takes the block's moment to be the *earliest* `started_at_unix` across
    its records, counts a block complete when every live condition appears, and does
    not exclude a run from either count.  Reproducing that rule rather than inventing a
    better one is the point: the sidecar has to relabel the blocks the driver labelled,
    not label them differently and call the driver wrong.
    """
    seen: dict[int, dict] = {}
    for record in records:
        if record.get("dry_run"):
            continue
        block = seen.setdefault(record["block_id"], {
            "conditions": set(), "at": None, "runs": 0, "commits": set(),
        })
        block["conditions"].add(record["condition_id"])
        block["runs"] += 1
        block["commits"].add(record["provenance"]["git_commit"])
        started = record.get("started_at_unix")
        if started is not None and (block["at"] is None or started < block["at"]):
            block["at"] = started
    return seen


# ── re-deriving the offset from the driver's log ──────────────────────────────────

_FINISHED = re.compile(r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})\s+block finished in (\d+)s")
_BLOCK_ID = re.compile(r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})\s+\|\s+block (\d+) seed")
_STRATUM = re.compile(
    r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})\s+(overnight|morning|afternoon|evening):"
    r"\s+\d+/\d+ today"
)


def derive_offset(log_path: Path, blocks: dict[int, dict], records: list[dict]) -> dict:
    """Read the offset off the driver's log, and read the driver's own labels with it.

    Returns the evidence rather than just the number, because a constant with no
    derivation beside it is the bug this module exists to remove, wearing a different
    hat.
    """
    finished_at: dict[int, float] = collections.defaultdict(float)
    for record in records:
        if record.get("dry_run"):
            continue
        block = record["block_id"]
        finished_at[block] = max(finished_at[block], record["finished_at_unix"])

    anchors: list[dict] = []
    labels: dict[int, str] = {}
    pending_block: int | None = None
    pending_stratum: str | None = None
    for line in log_path.read_text(encoding="utf-8").splitlines():
        match = _STRATUM.match(line)
        if match:
            pending_stratum = match.group(2)
            continue
        match = _BLOCK_ID.match(line)
        if match:
            pending_block = int(match.group(2))
            if pending_stratum is not None:
                labels[pending_block] = pending_stratum
                pending_stratum = None
            continue
        match = _FINISHED.match(line)
        if match and pending_block is not None and pending_block in finished_at:
            stamp = dt.datetime.strptime(match.group(1), "%Y-%m-%dT%H:%M:%S")
            as_if_utc = stamp.replace(tzinfo=dt.timezone.utc).timestamp()
            anchors.append({
                "block_id": pending_block,
                "log_local": match.group(1),
                "block_last_finished_unix": round(finished_at[pending_block], 6),
                "offset_plus_lag_seconds": round(as_if_utc - finished_at[pending_block], 6),
            })
            pending_block = None

    if not anchors:
        raise SystemExit(f"{log_path}: no usable anchors — is this a driver log?")

    # The log line is written after the block's last record, so every anchor is
    # offset + a small positive lag.  The offset is the whole-minute value that leaves
    # every lag non-negative and small; anything else would need the driver to log a
    # block before it finished.
    deltas = [a["offset_plus_lag_seconds"] for a in anchors]
    candidates = []
    for quarter_hours in range(-48, 57):
        offset = quarter_hours * 900
        lags = [d - offset for d in deltas]
        if all(0.0 <= lag < 120.0 for lag in lags):
            candidates.append((offset, min(lags), max(lags)))
    if len(candidates) != 1:
        raise SystemExit(
            f"{log_path}: the anchors admit {len(candidates)} offsets "
            f"{[c[0] for c in candidates]}; the derivation is not decisive"
        )
    offset, lag_min, lag_max = candidates[0]

    return {
        "source": log_path.name,
        "method": (
            "collect.py stamps every log line with a naive datetime.now(); each "
            "'block finished' line follows that block's last record, whose epoch time "
            "is in the NDJSON. Reading the stamp as UTC and subtracting the record's "
            "finished_at_unix gives offset + write-lag. The offset is the unique "
            "quarter-hour value leaving every lag in [0, 120) seconds."
        ),
        "anchors": len(anchors),
        "offset_seconds": offset,
        "write_lag_seconds": {
            "min": round(lag_min, 3),
            "max": round(lag_max, 3),
            "median": round(statistics.median(d - offset for d in deltas), 3),
        },
        "drift_across_window_seconds": round(max(deltas) - min(deltas), 3),
        "driver_labels": {str(k): v for k, v in sorted(labels.items())},
        "per_anchor": anchors,
    }


# ── the sidecar ───────────────────────────────────────────────────────────────────

def build(records: list[dict], runs_path: Path, offset: int,
          evidence: dict | None) -> dict:
    blocks = blocks_from(records)

    entries: dict[str, dict] = {}
    counts: collections.Counter[str] = collections.Counter()
    partial: list[int] = []
    per_stratum_day: collections.Counter[str] = collections.Counter()
    for block_id, block in sorted(blocks.items()):
        when = local(block["at"], offset)
        stratum = stratum_of_hour(when.hour)
        complete = len(block["conditions"]) >= LIVE_CONDITIONS
        entries[str(block_id)] = {
            "stratum": stratum,
            "complete": complete,
            "runs": block["runs"],
            "block_started_unix": round(block["at"], 6),
            "block_started_local": when.strftime("%Y-%m-%dT%H:%M:%S") + COLLECTION_UTC_OFFSET,
            "local_day": when.date().isoformat(),
            "apparatus_commit": sorted(block["commits"])[0][:7] if len(block["commits"]) == 1 else None,
        }
        if complete:
            counts[stratum] += 1
            per_stratum_day[f"{stratum}/{when.date().isoformat()}"] += 1
        else:
            partial.append(block_id)

    digest = hashlib.sha256(runs_path.read_bytes()).hexdigest()
    sidecar = {
        "sidecar_schema": SIDECAR_SCHEMA,
        "generated_by": "Study/analysis/strata.py",
        "what_this_is": (
            "A derived index, not evidence. runs.ndjson stores no stratum and no "
            "timezone; this file records the collection machine's UTC offset, how it "
            "was established, and the block-to-stratum map that follows from it. "
            "runs.ndjson is unmodified and must stay so."
        ),
        "source_file": runs_path.name,
        "source_sha256": digest,
        "source_records": sum(1 for r in records if not r.get("dry_run")),
        "collection_utc_offset_seconds": offset,
        "collection_utc_offset": COLLECTION_UTC_OFFSET if offset == COLLECTION_UTC_OFFSET_SECONDS
        else f"{'-' if offset < 0 else '+'}{abs(offset)//3600:02d}:{abs(offset)%3600//60:02d}",
        "offset_established_by": evidence if evidence else {
            "source": "documented constant in analysis/strata.py",
            "method": (
                "Not re-derived on this run. The constant was established from "
                "collect.log's 120 block-finish anchors and from the -0600 committer "
                "offset on all seven apparatus commits; see the module docstring and "
                "the committed sidecar's evidence block."
            ),
        },
        "stratum_boundaries_local_hours": {k: list(v) for k, v in STRATA.items()},
        "assignment_rule": (
            "stratum = the local-time hour bucket of the earliest started_at_unix "
            "among the block's records, which is exactly what collect.census() did "
            "when it decided the collection was finished."
        ),
        "complete_blocks_per_stratum": dict(sorted(counts.items())),
        "complete_blocks": sum(counts.values()),
        "partial_blocks": sorted(partial),
        "per_stratum_day": dict(sorted(per_stratum_day.items())),
        "blocks": entries,
    }
    return sidecar


def cross_check(sidecar: dict, evidence: dict | None) -> list[str]:
    """Everything that would make the map wrong, checked out loud."""
    problems: list[str] = []
    counts = sidecar["complete_blocks_per_stratum"]
    if sorted(counts) != sorted(STRATA):
        problems.append(f"strata present are {sorted(counts)}, expected {sorted(STRATA)}")
    if set(counts.values()) != {30}:
        problems.append(f"per-stratum complete-block counts are {counts}, expected 30 each")
    if sidecar["complete_blocks"] != 120:
        problems.append(f"{sidecar['complete_blocks']} complete blocks, expected 120")
    if sidecar["partial_blocks"] != [19, 68]:
        problems.append(f"partial blocks are {sidecar['partial_blocks']}, expected [19, 68]")
    if evidence and "driver_labels" in evidence:
        labels = evidence["driver_labels"]
        disagreed = [
            (b, labels[b], sidecar["blocks"][b]["stratum"])
            for b in labels
            if b in sidecar["blocks"] and labels[b] != sidecar["blocks"][b]["stratum"]
        ]
        if disagreed:
            problems.append(
                f"{len(disagreed)} block(s) relabelled against the driver's own log: "
                f"{disagreed[:5]}"
            )
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--runs", type=Path, default=DEFAULT_RUNS)
    parser.add_argument("--out", type=Path, default=DEFAULT_SIDECAR)
    parser.add_argument("--driver-log", type=Path, default=None,
                        help="collect.log from the collection worktree; re-derives the "
                             "offset from it and refuses to write if it disagrees")
    parser.add_argument("--check", action="store_true",
                        help="rebuild in memory and compare against the committed "
                             "sidecar instead of writing")
    args = parser.parse_args(argv)

    records = read_runs(args.runs)
    evidence = None
    offset = COLLECTION_UTC_OFFSET_SECONDS
    if args.driver_log:
        evidence = derive_offset(args.driver_log, blocks_from(records), records)
        offset = evidence["offset_seconds"]
        if offset != COLLECTION_UTC_OFFSET_SECONDS:
            print(f"the log gives UTC offset {offset}s; the module constant is "
                  f"{COLLECTION_UTC_OFFSET_SECONDS}s. One of them is wrong and it is "
                  f"not safe to guess which.", file=sys.stderr)
            return 2

    sidecar = build(records, args.runs, offset, evidence)
    problems = cross_check(sidecar, evidence)

    if args.check:
        if not args.out.exists():
            print(f"{args.out} does not exist", file=sys.stderr)
            return 1
        committed = json.loads(args.out.read_text())
        drift = [
            b for b in sidecar["blocks"]
            if committed.get("blocks", {}).get(b, {}).get("stratum")
            != sidecar["blocks"][b]["stratum"]
        ]
        if drift:
            print(f"{len(drift)} block(s) differ from the committed sidecar: {drift[:10]}",
                  file=sys.stderr)
            return 1
        if committed.get("source_sha256") != sidecar["source_sha256"]:
            print("the committed sidecar was generated from a different runs.ndjson",
                  file=sys.stderr)
            return 1
        print(f"{args.out.name}: 120 complete blocks, "
              f"{sidecar['complete_blocks_per_stratum']}, matches {args.runs.name}")
        return 1 if problems else 0

    if evidence is None and args.out.exists():
        # Preserve the evidence block a `--driver-log` run wrote, rather than replacing
        # it with the weaker "documented constant" note on every regeneration.
        committed = json.loads(args.out.read_text())
        if committed.get("collection_utc_offset_seconds") == offset:
            sidecar["offset_established_by"] = committed.get(
                "offset_established_by", sidecar["offset_established_by"])

    args.out.write_text(json.dumps(sidecar, indent=1, sort_keys=False) + "\n")
    print(f"{args.out}: {sidecar['complete_blocks']} complete blocks, "
          f"{sidecar['complete_blocks_per_stratum']}, offset "
          f"{sidecar['collection_utc_offset']}")
    for problem in problems:
        print(f"  ! {problem}", file=sys.stderr)
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
