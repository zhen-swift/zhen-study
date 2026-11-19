"""Study 2's NDJSON records: one `block` record when a block starts, one `run` record per condition.

Validated on write (`append` refuses an invalid record) and on read (`check.py`). A field added is a version
bump. The harness writes evidence and never a statistic: address sets, not recall.
"""

from __future__ import annotations

import json
import os

SCHEMA_VERSION = 1
KINDS = {"block", "run"}
TOOLS = {"zhen", "nmap"}
PRIVILEGES = {"user", "root"}
CACHE = {"cold", "warm"}
FLUSH = {"run", "block"}
HISTORY = {"empty", "primed", None}

COMMON = {"schema_version": int, "study": int, "kind": str, "phase": int, "block_id": str, "job": (str, type(None)),
          "dry_run": bool, "written_at": str}
BLOCK = {"seed": int, "dispersion": int, "flush_policy": str, "order": list, "manifest": dict,
         "provenance": dict, "priming": (dict, type(None)), "testbed_apply": dict}
RUN = {"run_id": str, "index": int, "condition": dict, "argv": list, "env": dict, "cache_state": str,
       "history": dict, "thermal": dict, "flush": (dict, type(None)), "exit_status": int,
       "wall_clock_seconds": float, "wall_clock_source": str, "started_at_unix": float, "finished_at_unix": float,
       "binary_sha256": (str, type(None)), "parsed": dict, "capture": dict, "warnings": list, "stubbed": bool,
       "exclusion": (str, type(None))}


def _types(record, spec, problems):
    for key, kind in spec.items():
        if key not in record:
            problems.append(f"missing {key}")
        elif not isinstance(record[key], kind) or (kind is int and isinstance(record[key], bool)):
            problems.append(f"{key} is {type(record[key]).__name__}")


def validate(r):
    """Every problem with a record, as text. Empty means valid."""
    if not isinstance(r, dict):
        return ["not an object"]
    problems = []
    _types(r, COMMON, problems)
    if r.get("schema_version") != SCHEMA_VERSION:
        problems.append(f"schema_version {r.get('schema_version')!r}")
    if r.get("study") != 2:
        problems.append("study is not 2")
    if r.get("kind") not in KINDS:
        problems.append(f"kind {r.get('kind')!r}")
    if r.get("phase") not in (1, 2):
        problems.append(f"phase {r.get('phase')!r}")
    if r.get("kind") == "block":
        _types(r, BLOCK, problems)
        if r.get("flush_policy") not in FLUSH:
            problems.append(f"flush_policy {r.get('flush_policy')!r}")
        if r.get("dispersion") not in (1, 5, 50, 500):
            problems.append(f"dispersion {r.get('dispersion')!r}")
        if not (r.get("manifest") or {}).get("addresses"):
            problems.append("manifest has no addresses")
        if not (r.get("provenance") or {}).get("binary_matches_freeze"):
            problems.append("binary is not the frozen one")
        if (r.get("provenance") or {}).get("repo_dirty") and not r.get("dry_run"):
            problems.append("repo dirty")
    elif r.get("kind") == "run":
        _types(r, RUN, problems)
        c = r.get("condition") or {}
        if c.get("tool") not in TOOLS or c.get("privilege") not in PRIVILEGES:
            problems.append(f"condition tool/privilege {c.get('tool')!r}/{c.get('privilege')!r}")
        if r.get("cache_state") not in CACHE:
            problems.append(f"cache_state {r.get('cache_state')!r}")
        if c.get("history") not in HISTORY:
            problems.append(f"history {c.get('history')!r}")
        if r.get("wall_clock_source") != "harness_monotonic":
            problems.append("wall clock not the harness's")
        parsed = r.get("parsed") or {}
        if not parsed.get("ok") and r.get("exclusion") is None:
            problems.append("unparseable output without an exclusion")
        if r.get("stubbed") and not r.get("dry_run"):
            problems.append("a stubbed run outside a dry run")
        if c.get("tool") == "zhen" and r.get("exit_status") == 0 and "ZHEN_HISTORY" not in (r.get("env") or {}):
            problems.append("a zhen run without its own ZHEN_HISTORY")
        cap = r.get("capture") or {}
        if cap.get("status") not in ("ok", "stubbed"):
            problems.append(f"capture {cap.get('status')!r}")
    return problems


def append(path, record):
    """Validates, appends one line, fsyncs. Raises ValueError on an invalid record: nothing invalid is written."""
    problems = validate(record)
    if problems:
        raise ValueError(f"invalid {record.get('kind')} record: {problems}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, sort_keys=True) + "\n")
        f.flush()
        os.fsync(f.fileno())


def read(path):
    """(line number, record or None, problems) for every line."""
    out = []
    with open(path, encoding="utf-8") as f:
        for n, line in enumerate(f, 1):
            try:
                r = json.loads(line)
            except ValueError as error:
                out.append((n, None, [f"not JSON: {error}"]))
                continue
            out.append((n, r, validate(r)))
    return out
