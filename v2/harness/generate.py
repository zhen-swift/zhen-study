#!/usr/bin/env python3
"""Turns a phase's design into runner jobs: one job per block, in an order shuffled by a recorded seed.

    python3 v2/harness/generate.py phase1 --seed 20261119       → v2/jobs/phase1-20261119/
    python3 v2/harness/generate.py phase2 --seed …
    python3 v2/harness/generate.py dryrun --seed …              (S2's gate: one block of every condition)

The jobs are committed with the code that runs them; `/study-run` copies a folder into the runner's `queue/`,
where they run in name order. `design.json` beside them records the seed, the design and every job, so the order
can be regenerated and checked.

Phase 1: every dispersion × `config.json` → `phase1.blocks_per_cell` blocks, flush per run.
Phase 2: dispersion × cache (flush per run, flush per block) × `phase2.blocks_per_cell`, randomised across blocks,
never batched; nmap -T2 in every fourth block of a cell.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
V2 = HERE.parent
sys.path.insert(0, str(HERE))

import conditions as C  # noqa: E402

DISPERSIONS = (1, 5, 50, 500)
#: Seconds around each run that are not the tool: cooldown, flush, capture settles, the record. Sizing only.
OVERHEAD_SECONDS = 10.0
APPLY_SECONDS = 60.0
PHASES = {"phase1": (1,), "phase2": (2,), "dryrun": (1, 2)}


def minutes(phase, block_index):
    runs = C.for_phase(phase, block_index=block_index)
    seconds = APPLY_SECONDS + sum(c.expected_seconds + OVERHEAD_SECONDS for c in runs)
    if any(c.history == C.PRIMED for c in runs):
        seconds += C.PRIMING_SCANS * (4.0 + OVERHEAD_SECONDS)
    return int(seconds // 60) + 1


def blocks(design, config):
    """The design's blocks as (phase, dispersion, flush, block_index, extra flags), before shuffling. Pure."""
    if design == "phase1":
        n = config["phase1"]["blocks_per_cell"]
        return [(1, d, "run", i, ()) for d in DISPERSIONS for i in range(n)]
    if design == "phase2":
        n = config["phase2"]["blocks_per_cell"]
        return [(2, d, f, i, ()) for d in DISPERSIONS for f in ("run", "block") for i in range(n)]
    if design == "dryrun":
        # Every condition once, real tools; zhen as root stubbed until its line exists (S5). -T2 included.
        # The second phase 2 block takes the other cache policy, so the warm path runs too.
        return [(1, 500, "run", 0, ("--dry-run",)), (2, 500, "run", 0, ("--dry-run", "--stub-root")),
                (2, 50, "block", 1, ("--dry-run", "--stub-root"))]
    raise ValueError(design)


def jobs(design, seed, config):
    rng = random.Random(seed)
    todo = blocks(design, config)
    rng.shuffle(todo)
    out = []
    for n, (phase, d, flush, index, extra) in enumerate(todo, 1):
        block = f"p{phase}-d{d}-{flush}-{index:03d}" + ("-dry" if "--dry-run" in extra else "")
        job_id = f"{design}-{n:04d}-{block}"
        out.append({
            "id": job_id, "arm": "testbed", "minutes": minutes(phase, index),
            "argv": ["v2/harness/run_block.py", "--phase", str(phase), "--block", block, "--dispersion", str(d),
                     "--flush", flush, "--seed", str(rng.randrange(2 ** 31)), "--block-index", str(index), *extra],
            "env": {"ZHEN_STUDY2_JOB": job_id},
        })
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("design", choices=("phase1", "phase2", "dryrun"))
    ap.add_argument("--seed", type=int, required=True)
    ap.add_argument("--out", type=Path)
    args = ap.parse_args(argv)
    config = json.loads((V2 / "config.json").read_text())
    out = args.out or V2 / "jobs" / f"{args.design}-{args.seed}"
    if out.exists() and any(out.iterdir()):
        raise SystemExit(f"{out} exists: a generated design is never overwritten")
    out.mkdir(parents=True)
    js = jobs(args.design, args.seed, config)
    for j in js:
        (out / f"{j['id']}.json").write_text(json.dumps(j, indent=1) + "\n")
    (out / "design.json").write_text(json.dumps({
        "design": args.design, "seed": args.seed, "generator": "v2/harness/generate.py",
        "config": {k: config.get(k) for k in ("phase1", "phase2", "testbed")},
        "conditions": [c.id for c in C.CONDITIONS if c.phase in PHASES[args.design]],
        "jobs": len(js), "minutes": sum(j["minutes"] for j in js),
        "order": [j["id"] for j in js]}, indent=1) + "\n")
    print(f"{len(js)} jobs, ~{sum(j['minutes'] for j in js) / 60:.1f} h, in {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
