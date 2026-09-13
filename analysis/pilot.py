"""Every number in FINDINGS-0.6-pilot.md, recomputed from the pilot's NDJSON alone.

    python3 Study/analysis/pilot.py Study/data/pilot.ndjson

Standard library only, on purpose: the pilot's gate says every number in it must be
recomputable from the NDJSON, and a reader should be able to check that with the
python that ships on the machine rather than with the analysis environment. The
hypothesis tests live in `stats.py` and are not here — nothing in a pilot is evidence,
so nothing here is a test. What is here is what 0.6 is gated on: the exclusion rate and
its reasons, the spread of every timed condition, what that spread implies for the
protocol's block count, recall against the oracle, and `-T2` measured to completion.
"""

from __future__ import annotations

import json
import math
import statistics
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from harness import conditions, schema  # noqa: E402

_Z = 1.959964
#: Asymptotic standard error of a median, ~1.2533 sigma/sqrt(n), for a normal sample.
#: Scan times are right-skewed, so this sizes; it never reports an interval.
_MEDIAN_FACTOR = 1.2533
#: chi-square quantiles for the two-sided 95% interval on a variance, by degrees of
#: freedom, so sigma's own uncertainty is stated beside sigma.
_CHI2 = {2: (0.05064, 7.37776), 3: (0.21580, 9.34840), 4: (0.48442, 11.14329),
         5: (0.83121, 12.83250), 6: (1.23734, 14.44938), 7: (1.68987, 16.01276),
         8: (2.17973, 17.53455), 9: (2.70039, 19.02277), 10: (3.24697, 20.48318)}


def load(path: Path) -> list[dict]:
    records = []
    with open(path, encoding="utf-8") as handle:
        for number, line in enumerate(handle, 1):
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            problems = schema.validate(record)
            if problems:
                raise SystemExit(f"{path}:{number} is not schema-valid: {problems}")
            if record.get("dry_run"):
                raise SystemExit(f"{path}:{number} is a dry-run record; a pilot is live")
            records.append(record)
    return records


def quartiles(values: list[float]) -> tuple[float, float, float]:
    """Median and the two hinges, by the inclusive method; n >= 2."""
    q = statistics.quantiles(values, n=4, method="inclusive")
    return q[0], q[1], q[2]


def recall(record: dict, truth: set[str]) -> float | None:
    if not truth:
        return None
    return len(set(record["found_addresses"]) & truth) / len(truth)


def main(path: Path) -> int:
    records = load(path)
    live = {c.id for c in conditions.ready()}
    print(f"{path}: {len(records)} records")

    # ── blocks and exclusions ──────────────────────────────────────────────────────
    by_block: dict[int, set[str]] = defaultdict(set)
    for r in records:
        by_block[r["block_id"]].add(r["condition_id"])
    complete = [b for b, ids in sorted(by_block.items()) if live <= ids]
    partial = [b for b in sorted(by_block) if b not in complete]
    # The first pilot attempt predates the host_asleep exclusion, so its records carry
    # the covariate and no exclusion. The same rule the harness now applies is applied
    # here on read, so the two attempts are counted the same way.
    for r in records:
        if not r["exclusion"] and r["covariates"].get("host_asleep_seconds", 0) > 1.0:
            r["exclusion"] = {"reason": "host_asleep",
                              "detail": f"applied on read: the host slept "
                                        f"{r['covariates']['host_asleep_seconds']:.0f}s "
                                        f"inside this run"}
    excluded = [r for r in records if r["exclusion"]]
    reasons: dict[str, int] = defaultdict(int)
    for r in excluded:
        reasons[r["exclusion"]["reason"]] += 1
    rate = len(excluded) / len(records) if records else 0.0
    print(f"blocks: {len(complete)} complete {complete}, {len(partial)} partial {partial}")
    print(f"exclusions: {len(excluded)} of {len(records)} = {rate * 100:.2f}% "
          f"({'OVER' if rate > 0.05 else 'under'} the 5% ceiling)")
    for reason, n in sorted(reasons.items()):
        print(f"  {reason}: {n}")
        for r in excluded:
            if r["exclusion"]["reason"] == reason:
                print(f"    {r['run_id']} {r['condition_id']}: {r['exclusion']['detail'][:200]}")

    # ── provenance held still ──────────────────────────────────────────────────────
    hashes = {r["provenance"]["netsanity_sha256"] for r in records}
    commits = {r["provenance"]["git_commit"] for r in records}
    verdicts = {r["provenance"]["local_network_permission"]["verdict"] for r in records}
    cooldowns = {r["covariates"]["cooldown_seconds"] for r in records}
    caches = {r["cache_state"] for r in records}
    print(f"binary sha256: {sorted(hashes)}")
    print(f"git commit: {sorted(commits)}")
    print(f"permission verdicts: {sorted(verdicts)}; cooldowns: {sorted(cooldowns)}; "
          f"cache states: {sorted(caches)}")
    print(f"captures: {sum(1 for r in records if r['capture']['status'] == 'ok')} ok of "
          f"{len(records)}; oracle statuses: "
          f"{dict(sorted(((s, sum(1 for r in records if r['oracle']['status'] == s)) for s in {r['oracle']['status'] for r in records})))}")

    # ── timing per condition, admissible runs only ────────────────────────────────
    usable = [r for r in records if not r["exclusion"]]
    print("\nwall clock per condition (harness monotonic, admissible runs), seconds")
    print(f"  {'condition':26s} {'n':>2} {'median':>8} {'q1':>8} {'q3':>8} {'min':>8} "
          f"{'max':>8} {'sd':>7} {'cv':>5}  {'±% on median at n=30 (n=120)':>28}")
    sizing = {}
    for cid in sorted(live):
        times = [r["wall_clock_seconds"] for r in usable if r["condition_id"] == cid]
        if len(times) < 2:
            print(f"  {cid:26s} {len(times):>2}  (too few admissible runs)")
            continue
        q1, med, q3 = quartiles(times)
        sd = statistics.stdev(times)
        mean = statistics.mean(times)
        half30 = _Z * _MEDIAN_FACTOR * sd / math.sqrt(30) / med * 100
        half120 = _Z * _MEDIAN_FACTOR * sd / math.sqrt(120) / med * 100
        sizing[cid] = {"n": len(times), "median": med, "sd": sd, "cv": sd / mean,
                       "half30": half30, "half120": half120}
        print(f"  {cid:26s} {len(times):>2} {med:8.3f} {q1:8.3f} {q3:8.3f} "
              f"{min(times):8.3f} {max(times):8.3f} {sd:7.3f} {sd / mean:5.2f}  "
              f"{half30:8.1f} ({half120:.1f})")

    # sigma's own interval, for the conditions the block count is sized on
    print("\nsigma 95% interval by condition (what this many blocks pins it to)")
    for cid, s in sizing.items():
        dof = s["n"] - 1
        if dof not in _CHI2:
            continue
        lo_q, hi_q = _CHI2[dof]
        lo = math.sqrt(dof * s["sd"] ** 2 / hi_q)
        hi = math.sqrt(dof * s["sd"] ** 2 / lo_q)
        blocks25_hi = (_Z * _MEDIAN_FACTOR * hi / (0.25 * s["median"])) ** 2
        print(f"  {cid:26s} sd {s['sd']:7.3f}  in [{lo:7.3f}, {hi:7.3f}]  "
              f"blocks for ±25% on the median if sigma is at the top: {blocks25_hi:6.0f}")

    # ── T2 ────────────────────────────────────────────────────────────────────────
    t2 = [r for r in records if r["condition_id"] == "nmap.sn.priv.T2"]
    print("\nnmap.sn.priv.T2, every run")
    for r in t2:
        print(f"  {r['run_id']}  {r['wall_clock_seconds']:8.2f}s  exit {r['exit_status']}  "
              f"{r['found_count']} hosts  "
              f"{'excluded: ' + r['exclusion']['reason'] if r['exclusion'] else 'admissible'}")
    block_seconds = [
        sum(r["wall_clock_seconds"] for r in records if r["block_id"] == b)
        + sum(r["covariates"]["cooldown_seconds"] for r in records if r["block_id"] == b)
        for b in complete
    ]
    if block_seconds:
        print(f"block cost (tool wall clock plus cooldowns; excludes capture and oracle "
              f"overhead): {[round(s) for s in block_seconds]} s, median "
              f"{statistics.median(block_seconds):.0f} s")
        starts = {b: min(r["started_at_unix"] for r in records if r["block_id"] == b)
                  for b in complete}
        ends = {b: max(r["finished_at_unix"] for r in records if r["block_id"] == b)
                for b in complete}
        spans = [ends[b] - starts[b] for b in complete]
        print(f"block span (first process start to last process end, so including "
              f"overhead): {[round(s) for s in spans]} s, median {statistics.median(spans):.0f} s")

    # ── recall against the oracle ─────────────────────────────────────────────────
    print("\nrecall per condition, admissible runs, against the oracle-agreed address set")
    print("  (present = the three oracles agree it was there; answering = it sent a frame)")
    print(f"  {'condition':26s} {'n':>2} {'present':>8} {'answering':>10}  missed (present)")
    misses: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for cid in sorted(live):
        rows = [r for r in usable if r["condition_id"] == cid]
        if not rows:
            continue
        present = [recall(r, set(r["oracle"]["addresses"])) for r in rows]
        answering = [recall(r, set(r["oracle"]["capture"]["answering"])) for r in rows]
        for r in rows:
            for a in set(r["oracle"]["addresses"]) - set(r["found_addresses"]):
                misses[cid][a] += 1
        missed = ", ".join(f"{a}×{n}" for a, n in sorted(misses[cid].items()))
        print(f"  {cid:26s} {len(rows):>2} {statistics.median(present):8.2f} "
              f"{statistics.median(answering):10.2f}  {missed}")

    # Cold is the first run of a block, by position rather than by label: the first
    # pilot attempt stamped every run cold, and the harness has labelled by position
    # since. The gate 0.3 diagnostic that H2 turns on — the 500 ms pair missed with a
    # discovery stage shorter than their round trip — is a cold-cache observation, and
    # a warm run cannot confirm or refute it, because the neighbour table already
    # holds what the previous run's ARP provoked.
    print("\ncold runs (first in their block), every one, against the oracle-agreed set")
    for r in sorted(records, key=lambda r: r["block_id"]):
        if r["sequence_index"] != 0:
            continue
        truth = set(r["oracle"]["addresses"])
        missed = sorted(truth - set(r["found_addresses"]))
        print(f"  block {r['block_id']} {r['condition_id']:26s} recall "
              f"{recall(r, truth) if truth else float('nan'):.2f}  missed {missed}"
              + (f"  [{r['exclusion']['reason']}]" if r["exclusion"] else ""))
    # `replies_seen` against `hosts_found`.  Schema 2 carries them in `parse.discovery`
    # and the line is then recomputable from the NDJSON; a schema 1 record points at
    # the artifact by path and does not copy it, so for those the file is opened and
    # the line says so.  That difference is the deficiency the 0.6 gate was first
    # assessed against, and the heading names the source so nobody has to guess.
    print("  netsanity runs, replies seen against hosts found, by cache state:")
    for r in sorted(records, key=lambda r: (r["block_id"], r["sequence_index"])):
        if r["tool"] != "netsanity":
            continue
        disc = (r.get("parse") or {}).get("discovery")
        source = "record"
        if not disc:
            source = "ARTIFACT, not the NDJSON"
            try:
                disc = [s for s in json.load(open(r["stdout_path"]))["run"]["timing"]["stages"]
                        if s["stage"] == "discovery"][0]
            except (OSError, KeyError, IndexError):
                print(f"    block {r['block_id']} idx {r['sequence_index']:2d} "
                      f"{r['condition_id']:18s} artifact not on disk")
                continue
        truth = set(r["oracle"]["addresses"])
        print(f"    block {r['block_id']} idx {r['sequence_index']:2d} "
              f"{r['condition_id']:18s} {r['cache_state']:4s} replies {disc['replies_seen']:2d} "
              f"found {disc['hosts_found']:2d} stage {disc['elapsed_millis']:.0f} ms  "
              f"recall {recall(r, truth) if truth else float('nan'):.2f}  [{source}]")

    # ── cold against warm, per condition, when the file has both ─────────────────
    # `--flush-policy run` labels every run cold; the protocol's single flush labels
    # one per block.  With both present the file can price the policy per condition:
    # wall clock and recall, cold against warm, from the same apparatus on the same
    # segment.  Absent the flush-per-run blocks, the cold column is one run in
    # thirteen and this table says so by its n.
    policies = {r["covariates"].get("flush_policy", "block") for r in records}
    print(f"\ncold against warm, admissible runs (flush policies in file: {sorted(policies)})")
    print(f"  {'condition':26s} {'n cold':>6} {'median cold':>11} {'recall':>6} "
          f"{'n warm':>6} {'median warm':>11} {'recall':>6}   {'cold/warm':>9}")
    for cid in sorted(live):
        cold = [r for r in usable if r["condition_id"] == cid and r["cache_state"] == "cold"]
        warm = [r for r in usable if r["condition_id"] == cid and r["cache_state"] == "warm"]
        def med(rs):
            return statistics.median(r["wall_clock_seconds"] for r in rs) if rs else None
        def rec(rs):
            vals = [recall(r, set(r["oracle"]["addresses"])) for r in rs
                    if r["oracle"]["addresses"]]
            return statistics.mean(vals) if vals else None
        mc, mw, rc, rw = med(cold), med(warm), rec(cold), rec(warm)
        ratio = (mc / mw) if (mc and mw) else None
        print(f"  {cid:26s} {len(cold):>6} "
              f"{(f'{mc:.3f}' if mc is not None else '-'):>11} "
              f"{(f'{rc:.2f}' if rc is not None else '-'):>6} "
              f"{len(warm):>6} "
              f"{(f'{mw:.3f}' if mw is not None else '-'):>11} "
              f"{(f'{rw:.2f}' if rw is not None else '-'):>6}   "
              f"{(f'{ratio:.2f}x' if ratio else '-'):>9}")

    by_policy = defaultdict(list)
    for b in complete:
        rs = [r for r in records if r["block_id"] == b]
        pol = {r["covariates"].get("flush_policy", "block") for r in rs}.pop()
        span = max(r["finished_at_unix"] for r in rs) - min(r["started_at_unix"] for r in rs)
        by_policy[pol].append(span)
    for pol, spans in sorted(by_policy.items()):
        print(f"  block span under flush policy {pol!r}: {[round(x) for x in spans]} s, "
              f"median {statistics.median(spans):.0f} s")

    # ── what the wire saw, for the condition whose two modes the pilot chased ─────
    wired = [r for r in records if (r["capture"].get("wire") or {}).get("status") == "ok"]
    if wired:
        print("\nunprivileged -T2, what the Mac-side capture counted (capture.wire, schema 2)")
        print(f"  {'run':20s} {'wall':>8} {'cache':>5} {'arp req':>7} {'arp rep':>7} "
              f"{'syn':>5} {'synack':>6} {'rst':>5}  {'rst senders':>11}  {'conn-refused':>12}")
        for r in sorted(wired, key=lambda r: (r["block_id"], r["sequence_index"])):
            if r["condition_id"] != "nmap.sn.unpriv.T2":
                continue
            w = r["capture"]["wire"]
            senders = [a for a in w.get("tcp_rst_by_source", {}) if not a.endswith(".1")]
            refused = sum(1 for v in (r["parse"].get("reasons") or {}).values()
                          if v == "conn-refused")
            print(f"  {r['run_id']:20s} {r['wall_clock_seconds']:8.1f} {r['cache_state']:>5} "
                  f"{w['arp_requests']:7d} {w['arp_replies']:7d} {w['tcp_syn']:5d} "
                  f"{w['tcp_synack']:6d} {w['tcp_rst']:5d}  {len(senders):11d}  {refused:12d}")
    else:
        print("\n(no capture.wire in this file: schema 1, the wire counts were read by hand)")

    roles = {}
    for r in records:
        roles.update({a: v["role"] for a, v in r["oracle"]["manifest"]["by_address"].items()})
    print("\nroles of the addresses missed by any condition:")
    for a in sorted({a for m in misses.values() for a in m}):
        print(f"  {a}: {roles.get(a)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(Path(sys.argv[1]) if len(sys.argv) > 1 else
                          Path(__file__).resolve().parents[1] / "data" / "pilot.ndjson"))
