"""Read the simulation output and nothing else.

This is the only module in ``analysis/`` that touches a file on disk, and no module in
``analysis/`` may import anything from ``sim/``.  The two halves meet at the CSV and
nowhere else; that is what makes the figures reproducible by someone who does not
trust — or does not want to rerun — the simulator.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

# The harness and the analysis meet at the NDJSON file, and they share exactly one
# module: the schema that defines it. Sharing the *definition* of the record is what
# lets the reader refuse a file the writer would not have produced; sharing anything
# else would put the measurement apparatus inside the analysis, which is the thing
# HARNESS.md forbids.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from harness import schema as run_schema  # noqa: E402

DATA = Path(__file__).resolve().parents[1] / "data"
FIGURES = Path(__file__).resolve().parents[1] / "figures"

# Each file carries its own schema version; the loader refuses a file that mixes
# versions, and refuses a version it was not written against.
SIM_SCHEMA = 3
C3_SCHEMA = 1


def _check(df, path, expected):
    if df.empty:
        raise SystemExit(f"{path} is empty")
    versions = set(df["schema_version"].unique())
    if versions != {expected}:
        raise SystemExit(f"{path} carries schema versions {sorted(versions)}; "
                         f"this analysis was written against {expected}")
    return df


def results(path=None):
    path = Path(path) if path else DATA / "sim_results.csv"
    return _check(pd.read_csv(path), path, SIM_SCHEMA)


def c3_runs(path=None):
    path = Path(path) if path else DATA / "c3_runs.csv"
    return _check(pd.read_csv(path), path, C3_SCHEMA)


def c3_misses(path=None):
    path = Path(path) if path else DATA / "c3_misses.csv"
    df = pd.read_csv(path)
    if df.empty:
        return df
    return _check(df, path, C3_SCHEMA)


def c3_scratch(path=None):
    path = Path(path) if path else DATA / "c3_scratch_runs.csv"
    return _check(pd.read_csv(path), path, C3_SCHEMA)


# ── collection data ───────────────────────────────────────────────────────────────
#
# Everything above reads the simulator's CSVs. Everything below reads the harness's
# NDJSON, which is the only file the collection phase produces and the only input to
# any number the paper cites.

RUNS_SCHEMA = run_schema.SCHEMA_VERSION


def validate_runs_file(path) -> tuple[list[dict], list[str]]:
    """Read every line, validate every record, and report every problem.

    Returns the records and the warnings rather than raising on the first one: a
    seven-day file with one bad line in the middle should tell you about that line, not
    about the first thing that happened to fail. `runs()` is the strict wrapper.
    """
    path = Path(path)
    records, warnings = [], []
    versions = set()
    with open(path, encoding="utf-8") as handle:
        for number, line in enumerate(handle, 1):
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as error:
                warnings.append(f"{path}:{number}: not JSON: {error}")
                continue
            versions.add(record.get("schema_version"))
            for problem in run_schema.validate(record):
                warnings.append(f"{path}:{number}: {problem}")
            records.append(record)
    if not records:
        warnings.append(f"{path} contains no records")
    if len(versions) > 1:
        # Section 8 of the protocol: the loader refuses a file that mixes versions
        # without an explicit merge, because a silently mixed file is a set of columns
        # that mean different things in different rows.
        warnings.append(
            f"{path} mixes schema versions {sorted(versions)}; an explicit merge is "
            f"required before this file can be analysed"
        )
    return records, warnings


def runs(path=None, *, strict: bool = True) -> pd.DataFrame:
    """The NDJSON as a DataFrame, one row per run.

    Nested objects are kept whole in their own columns rather than exploded: the
    analysis wants `provenance` and `oracle` as objects, and flattening them here would
    bake one reading of the record into the loader.  Four things are lifted out because
    every downstream module needs them and reaching into a dict for them in each is how
    a typo becomes a silent NaN.
    """
    path = Path(path) if path else DATA / "runs.ndjson"
    records, warnings = validate_runs_file(path)
    if warnings and strict:
        raise SystemExit(
            f"{path} is not schema-valid ({len(warnings)} problem(s)):\n  "
            + "\n  ".join(warnings[:20])
        )
    frame = pd.DataFrame.from_records(records)
    if frame.empty:
        return frame
    frame["excluded"] = frame["exclusion"].notna()
    frame["exclusion_reason"] = frame["exclusion"].map(
        lambda e: e["reason"] if isinstance(e, dict) else None
    )
    frame["permission_verdict"] = frame["provenance"].map(
        lambda p: p["local_network_permission"]["verdict"]
    )
    frame["git_commit"] = frame["provenance"].map(lambda p: p["git_commit"])
    return frame


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else DATA / "runs.ndjson"
    found, problems = validate_runs_file(target)
    print(f"{target}: {len(found)} record(s), {len(problems)} validation warning(s)")
    for problem in problems[:40]:
        print(f"  {problem}")
    raise SystemExit(1 if problems else 0)
