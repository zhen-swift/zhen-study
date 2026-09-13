"""The NDJSON record: one run per line, versioned, validated on write and on read.

Written as a hand-rolled validator over plain dicts rather than against a schema
library, for one reason that outlives the convenience argument: the validator has to say
things a JSON Schema cannot, and those are the clauses that protect the study.

    * `wall_clock_source` must be the literal `harness_monotonic`.  A record whose
      timing came from either tool's own report is not admissible evidence, and the
      schema is the place that refuses it rather than a code review.
    * a parse failure must carry an exclusion.  An empty address set and an unparseable
      one are different findings, and a record that conflates them is worse than no
      record.
    * `found_count` must equal `len(found_addresses)`.  Redundant on purpose: it is the
      cheapest possible check that a record was assembled rather than hand-edited.

Adding a field bumps `SCHEMA_VERSION`, and the loader refuses a file that mixes
versions without an explicit merge.
"""

from __future__ import annotations

import json
import os
import re
from typing import Any

SCHEMA_VERSION = 1

TOOLS = {"netsanity", "nmap"}
PRIVILEGES = {"user", "root"}
CACHE_STATES = {"cold", "warm"}
WALL_CLOCK_SOURCE = "harness_monotonic"

#: Every exclusion the protocol pre-specifies, plus the two the apparatus itself can
#: raise.  Section 7 fixes the list in advance so that "excluded" cannot become a
#: category invented after the data is in.
EXCLUSION_REASONS = {
    # Pre-specified in PROTOCOL.md section 7.
    "oracle_disagreement",
    "interfering_process",
    "topology_change",
    # Apparatus failures, which are exclusions for the same reason: the run produced no
    # evidence, and pretending otherwise puts a fabricated zero in the data.
    "parse_failure",
    "capture_failure",
    "permission_not_asserted",
    "oracle_not_configured",
    "nonzero_exit",
    "tool_missing",
    # The host slept inside the run. time.monotonic() stops during sleep and the tool's
    # own timers do not, so neither the wall clock nor the address set means anything.
    # Found by the 0.6 pilot; see FINDINGS-0.6-pilot.md.
    "host_asleep",
    # 0.6 breaks one run deliberately to prove this machinery works.
    "injected_fault",
}

PERMISSION_VERDICTS = {"granted", "denied_likely", "indeterminate"}
CAPTURE_STATUSES = {"ok", "failed", "disabled", "stubbed"}
ORACLE_STATUSES = {"agree", "disagree", "not_configured", "stubbed"}

_IPV4 = re.compile(r"^\d{1,3}(?:\.\d{1,3}){3}$")


class SchemaError(Exception):
    """A record that must not be written, or must not be believed once read."""


# ── the record ────────────────────────────────────────────────────────────────────

def make_record(
    *,
    run_id: str,
    block_id: int,
    block_seed: int,
    sequence_index: int,
    condition,
    argv: list[str],
    dry_run: bool,
    started_at_unix: float,
    finished_at_unix: float,
    wall_clock_seconds: float,
    exit_status: int | None,
    stdout_path: str | None,
    stderr_path: str | None,
    found_addresses: list[str],
    parse: dict[str, Any],
    cache_state: str,
    provenance: dict[str, Any],
    capture: dict[str, Any],
    covariates: dict[str, Any],
    oracle: dict[str, Any],
    tool_self_reported_seconds: float | None = None,
    exclusion: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Assemble one run record.

    `tool_self_reported_seconds` is recorded because throwing away an observation is
    always wrong, and is named the way it is so that no analysis can reach for it
    believing it to be the measurement.  `wall_clock_seconds` is the measurement, and it
    is taken by `runners.py` with `time.monotonic()` around the process.
    """
    addresses = sorted(set(found_addresses))
    return {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "block_id": block_id,
        "block_seed": block_seed,
        "sequence_index": sequence_index,
        "condition_id": condition.id,
        "tool": condition.tool,
        "privilege": condition.privilege,
        "hypotheses": list(condition.hypotheses),
        "argv": list(argv),
        "dry_run": bool(dry_run),
        "started_at_unix": float(started_at_unix),
        "finished_at_unix": float(finished_at_unix),
        "wall_clock_source": WALL_CLOCK_SOURCE,
        "wall_clock_seconds": float(wall_clock_seconds),
        "tool_self_reported_seconds": tool_self_reported_seconds,
        "exit_status": exit_status,
        "stdout_path": stdout_path,
        "stderr_path": stderr_path,
        "found_addresses": addresses,
        "found_count": len(addresses),
        "parse": parse,
        "cache_state": cache_state,
        "provenance": provenance,
        "capture": capture,
        "covariates": covariates,
        "oracle": oracle,
        "exclusion": exclusion,
    }


# ── validation ────────────────────────────────────────────────────────────────────

def _want(problems, cond, message):
    if not cond:
        problems.append(message)


def validate(record: Any) -> list[str]:
    """Return every problem with one record. An empty list means the record is sound."""
    p: list[str] = []
    if not isinstance(record, dict):
        return [f"record is {type(record).__name__}, not an object"]

    version = record.get("schema_version")
    if version != SCHEMA_VERSION:
        # Every other check assumes this version's shape, so stop here rather than
        # emit a cascade of confusing complaints about a record from another era.
        return [f"schema_version is {version!r}, expected {SCHEMA_VERSION}"]

    for key, kind in (
        ("run_id", str), ("block_id", int), ("block_seed", int),
        ("sequence_index", int), ("condition_id", str), ("tool", str),
        ("privilege", str), ("cache_state", str), ("wall_clock_source", str),
        ("dry_run", bool),
    ):
        value = record.get(key)
        _want(p, isinstance(value, kind) and not (kind is int and isinstance(value, bool)),
              f"{key} is {value!r}, expected {kind.__name__}")

    _want(p, record.get("tool") in TOOLS, f"tool {record.get('tool')!r} not in {sorted(TOOLS)}")
    _want(p, record.get("privilege") in PRIVILEGES,
          f"privilege {record.get('privilege')!r} not in {sorted(PRIVILEGES)}")
    _want(p, record.get("cache_state") in CACHE_STATES,
          f"cache_state {record.get('cache_state')!r} not in {sorted(CACHE_STATES)}")

    # The clause the whole apparatus turns on.
    _want(p, record.get("wall_clock_source") == WALL_CLOCK_SOURCE,
          f"wall_clock_source is {record.get('wall_clock_source')!r}; only "
          f"{WALL_CLOCK_SOURCE!r} is admissible — a tool's self-reported timing is not "
          f"the measurement")

    hypotheses = record.get("hypotheses")
    _want(p, isinstance(hypotheses, list) and all(isinstance(h, str) for h in hypotheses),
          "hypotheses must be a list of strings")
    argv = record.get("argv")
    _want(p, isinstance(argv, list) and all(isinstance(a, str) for a in argv) and argv,
          "argv must be a non-empty list of strings")

    started, finished = record.get("started_at_unix"), record.get("finished_at_unix")
    wall = record.get("wall_clock_seconds")
    for key, value in (("started_at_unix", started), ("finished_at_unix", finished),
                       ("wall_clock_seconds", wall)):
        _want(p, isinstance(value, (int, float)) and not isinstance(value, bool),
              f"{key} is {value!r}, expected a number")
    if all(isinstance(v, (int, float)) for v in (started, finished, wall)):
        _want(p, finished >= started, "finished_at_unix precedes started_at_unix")
        _want(p, wall >= 0, f"wall_clock_seconds is negative ({wall})")
        # The wall clock is measured inside the window the timestamps bracket, so it
        # cannot exceed it.  A record that fails this was assembled from two different
        # runs.
        _want(p, wall <= (finished - started) + 1.0,
              f"wall_clock_seconds {wall} exceeds the bracketing timestamps "
              f"({finished - started:.3f}s)")

    self_report = record.get("tool_self_reported_seconds")
    _want(p, self_report is None or isinstance(self_report, (int, float)),
          "tool_self_reported_seconds must be a number or null")

    exit_status = record.get("exit_status")
    _want(p, exit_status is None or (isinstance(exit_status, int) and not isinstance(exit_status, bool)),
          "exit_status must be an integer or null")

    found = record.get("found_addresses")
    if not isinstance(found, list) or not all(isinstance(a, str) for a in found):
        p.append("found_addresses must be a list of strings")
    else:
        bad = [a for a in found if not _IPV4.match(a)]
        _want(p, not bad, f"found_addresses contains non-IPv4 entries: {bad[:3]}")
        _want(p, found == sorted(set(found)),
              "found_addresses must be sorted and free of duplicates")
        _want(p, record.get("found_count") == len(found),
              f"found_count {record.get('found_count')!r} != len(found_addresses) {len(found)}")

    parse = record.get("parse")
    if not isinstance(parse, dict) or "ok" not in parse:
        p.append("parse must be an object carrying at least 'ok'")
        parse = {}
    else:
        _want(p, isinstance(parse["ok"], bool), "parse.ok must be a boolean")

    exclusion = record.get("exclusion")
    if exclusion is not None:
        if not isinstance(exclusion, dict):
            p.append("exclusion must be null or an object")
        else:
            _want(p, exclusion.get("reason") in EXCLUSION_REASONS,
                  f"exclusion.reason {exclusion.get('reason')!r} is not pre-specified; "
                  f"allowed: {sorted(EXCLUSION_REASONS)}")
            _want(p, isinstance(exclusion.get("detail"), str),
                  "exclusion.detail must be a string")

    # A parse failure with no exclusion is the silent-empty-set defect the protocol
    # names, and it is the one shape of bad record that would look entirely normal in
    # the analysis.
    if parse.get("ok") is False and exclusion is None:
        p.append("parse failed but no exclusion is recorded — an unparseable run and an "
                 "empty run are different findings")

    p += _validate_provenance(record.get("provenance"), dry_run=record.get("dry_run") is True)
    p += _validate_capture(record.get("capture"))
    p += _validate_oracle(record.get("oracle"))

    covariates = record.get("covariates")
    _want(p, isinstance(covariates, dict), "covariates must be an object")
    return p


PROVENANCE_KEYS = (
    "git_commit", "git_dirty", "netsanity_version", "netsanity_sha256",
    "nmap_version", "swift_version", "os_product_version", "os_build",
    "hw_model", "uptime_seconds", "on_ac_power", "thermal_pressure",
    "local_network_permission",
)


def _validate_provenance(prov: Any, *, dry_run: bool = False) -> list[str]:
    if not isinstance(prov, dict):
        return ["provenance must be an object"]
    p = []
    for key in PROVENANCE_KEYS:
        if key not in prov:
            p.append(f"provenance.{key} is missing")
    # A dirty tree is fatal for a record that is evidence and merely noted for one that
    # is not. A dry run measures stubs, so the commit it ran against says nothing about
    # any number in it; a live run measures the binary that commit built, and a record
    # of that which cannot name the source is not reproducible at all. The exemption is
    # narrow on purpose and `run_block.py` still refuses a dirty tree in dry-run unless
    # it is asked twice.
    if not dry_run:
        _want(p, prov.get("git_dirty") is False,
              "provenance.git_dirty is not False — measuring uncommitted code produces a "
              "number nobody can reproduce, and the block should have aborted")
    permission = prov.get("local_network_permission")
    if not isinstance(permission, dict):
        p.append("provenance.local_network_permission must be an object")
    else:
        _want(p, permission.get("verdict") in PERMISSION_VERDICTS,
              f"local_network_permission.verdict {permission.get('verdict')!r} not in "
              f"{sorted(PERMISSION_VERDICTS)}")
        for key in ("method", "neighbour_entries", "controls_answered", "control_hosts"):
            if key not in permission:
                p.append(f"provenance.local_network_permission.{key} is missing")
    return p


def _validate_capture(capture: Any) -> list[str]:
    if not isinstance(capture, dict):
        return ["capture must be an object"]
    p = []
    _want(p, capture.get("status") in CAPTURE_STATUSES,
          f"capture.status {capture.get('status')!r} not in {sorted(CAPTURE_STATUSES)}")
    if capture.get("status") == "ok" and not capture.get("path"):
        p.append("capture.status is ok but no pcap path is recorded")
    return p


def _validate_oracle(oracle: Any) -> list[str]:
    if not isinstance(oracle, dict):
        return ["oracle must be an object"]
    p = []
    _want(p, oracle.get("status") in ORACLE_STATUSES,
          f"oracle.status {oracle.get('status')!r} not in {sorted(ORACLE_STATUSES)}")
    return p


def validate_or_raise(record: dict[str, Any]) -> dict[str, Any]:
    problems = validate(record)
    if problems:
        raise SchemaError(
            f"run {record.get('run_id')!r} is not schema-valid:\n  "
            + "\n  ".join(problems)
        )
    return record


# ── writing ───────────────────────────────────────────────────────────────────────

def append(path, record: dict[str, Any]) -> None:
    """Validate, then append one line, then fsync.

    Validation happens before the line is written, never after: a file that already
    contains an invalid record has to be repaired by hand, and repairing raw data by
    hand is how a study stops being reproducible.  fsync because a seven-day unattended
    run will be interrupted at some point, and the interesting question afterwards is
    which runs completed, not which ones the page cache still remembered.
    """
    validate_or_raise(record)
    line = json.dumps(record, sort_keys=True, separators=(",", ":"))
    if "\n" in line:
        raise SchemaError("record serialised to more than one line")
    path = os.fspath(path)
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(line + "\n")
        handle.flush()
        os.fsync(handle.fileno())
