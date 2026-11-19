#!/usr/bin/env python3
"""Reads study 2's run records and reports every problem and every warning. Exit 1 if there is any.

    python3 v2/harness/check.py [runs.ndjson …]      default: every runs.ndjson under v2/data/

S2's gate is a dry run of every condition with this printing none.
"""

from __future__ import annotations

import collections
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import record as R  # noqa: E402


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    paths = [Path(p) for p in argv] or sorted((HERE.parent / "data").rglob("runs.ndjson"))
    if not paths:
        print("no runs.ndjson found")
        return 1
    bad = 0
    for path in paths:
        rows = R.read(path)
        kinds, by_condition, excluded = collections.Counter(), collections.Counter(), []
        for n, r, problems in rows:
            if r:
                kinds[r.get("kind")] += 1
                if r.get("kind") == "run":
                    by_condition[(r.get("condition") or {}).get("id")] += 1
                    if r.get("exclusion"):
                        excluded.append(f"{r.get('run_id')}: {r['exclusion']}")
            for p in problems:
                print(f"{path}:{n}: problem: {p}")
                bad += 1
            for w in (r or {}).get("warnings") or []:
                print(f"{path}:{n}: warning ({(r.get('condition') or {}).get('id')}): {w}")
                bad += 1
            for i, s in enumerate(((r or {}).get("priming") or {}).get("scans") or []):
                for w in s.get("warnings") or []:
                    print(f"{path}:{n}: warning (priming scan {i + 1}): {w}")
                    bad += 1
        print(f"{path}: {kinds['block']} blocks, {kinds['run']} runs, {len(by_condition)} conditions, "
              f"{len(excluded)} excluded")
        for e in excluded:
            print(f"  excluded {e}")
    print(f"{bad} problems and warnings")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
