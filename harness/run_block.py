#!/usr/bin/env python3
"""One block is one run of every condition, in randomised order. The only entry point.

    for block in range(n):
        seed and record the shuffle
        flush the neighbour table          # cache state is a condition, not an accident
        for condition in shuffled(conditions):
            cooldown()
            start capture
            run
            stop capture
            read the oracles
            append one NDJSON record, fsync

Four things this module refuses to do, each of which would produce data that looks fine
and is not:

**A dirty tree aborts the block.**  Before anything runs, not after.  A `--dry-run` may
proceed on a dirty tree only if asked twice (`--allow-dirty`), and its records are
stamped `dry_run: true` so they can never be mistaken for evidence.

**A denied Local Network permission aborts the block.**  Denial returns zero results
rather than an error, so a denied run is a well-formed artifact reporting an empty
network.  `provenance.assert_local_network_permission` runs a positive control before
each block and the verdict is written into every record.

**A missing oracle stops a live block.**  Recall is meaningless without knowing what was
there.  The three oracles are `oracles.py` (gate 0.4): the manifest is read once per
block and a live block refuses to start without it; the per-responder capture is started
around every run and a capture that fails stops the block; the inventory is read after
every run.  A run whose three oracles disagree is recorded and excluded with
`oracle_disagreement`, per PROTOCOL.md section 3 — never dropped.  Until the 0.6 pilot
this module aborted every live block with a message saying `oracles.py` did not exist,
which had stopped being true when 0.4 was met; the module had been built and never
wired in, and the first live block is what found it.

**A refused `sudo -n` stops the block.**  Not a per-run exclusion: if root is not
arranged, every privileged run in every remaining block fails identically, and a study
that quietly drops half its conditions overnight is worse than one that halts.

Resumable by block id, because a seven-day run will be interrupted.
"""

from __future__ import annotations

import argparse
import ast
import json
import math
import os
import random
import statistics
import sys
import textwrap
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from harness import capture as capture_mod           # noqa: E402
from harness import oracles as oracles_mod           # noqa: E402
from harness import conditions as conditions_mod     # noqa: E402
from harness import provenance as provenance_mod     # noqa: E402
from harness import runners, schema                  # noqa: E402

HARNESS_DIR = Path(__file__).resolve().parent
STUDY = HARNESS_DIR.parent
DATA = STUDY / "data"


# ── independence, asserted rather than asserted-in-a-comment ──────────────────────

FORBIDDEN = ("netsanity", "NetSanity", "swift")


def self_check() -> list[str]:
    """The harness must not import from the thing it measures.

    Checked by parsing this package's own source, because the rule is only worth
    anything if something enforces it. Parsed rather than grepped: the first version of
    this function matched line prefixes and flagged a docstring sentence beginning
    "from this process", which is the failure mode of every textual import check. Only
    real `Import` and `ImportFrom` nodes are examined, so the harness stays free to
    *name* netsanity in prose and in argv — which it must, in order to run it.
    """
    problems = []
    for source in sorted(HARNESS_DIR.glob("*.py")):
        tree = ast.parse(source.read_text(), filename=str(source))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""] + [alias.name for alias in node.names]
            else:
                continue
            hits = [n for n in names if any(t in n for t in FORBIDDEN)]
            if hits:
                problems.append(f"{source.name}:{node.lineno}: imports {hits}")
    return problems


# ── how many blocks, from nmap's measured variance ────────────────────────────────
#
# 0.3 timed three consecutive identical `nmap -sn 10.10.20.0/24` invocations at 3.61 s,
# 12.61 s and 21.0 s — a factor of six. A fourth, taken while building this harness on
# 2026-09-08 under the same command with `-T3 --reason`, came in at 21.96 s. All four
# are diagnostics from the development network, not the testbed, and they are the only
# variance estimate that exists before the pilot.
#
# The number that matters is not the point estimate. It is that four samples pin sigma
# very weakly, and the block count scales with sigma squared — so the honest output of
# this function is a range, and the pilot's job in 0.6 is to replace it with something
# narrower rather than to confirm it.

NMAP_SECONDS = [3.61, 12.61, 20.98, 21.96]

#: chi-square quantiles for the two-sided 95% interval on a variance, indexed by
#: degrees of freedom. Hard-coded so the harness has no scipy dependency: it has to run
#: unattended for seven days and every import is a thing that can break at 03:00.
_CHI2 = {2: (0.05064, 7.37776), 3: (0.21580, 9.34840), 4: (0.48442, 11.14329),
         9: (2.70039, 19.02277), 29: (16.04707, 45.72229)}
_Z = 1.959964
#: The asymptotic standard error of a median is ~1.2533 sigma/sqrt(n) for a normal
#: sample. Scan times are right-skewed, so this is an approximation and it is used only
#: to size a pilot, never to report an interval.
_MEDIAN_FACTOR = 1.2533


def sizing(samples=None, fractions=(0.10, 0.20, 0.25, 0.50)) -> dict:
    samples = list(samples or NMAP_SECONDS)
    n = len(samples)
    mean = statistics.mean(samples)
    sd = statistics.stdev(samples)
    lo_q, hi_q = _CHI2[n - 1]
    sigma_lo = math.sqrt((n - 1) * sd * sd / hi_q)
    sigma_hi = math.sqrt((n - 1) * sd * sd / lo_q)

    rows = []
    for fraction in fractions:
        half_width = fraction * mean
        rows.append({
            "half_width_fraction": fraction,
            "half_width_seconds": half_width,
            "blocks_point": (_Z * sd / half_width) ** 2,
            "blocks_sigma_low": (_Z * sigma_lo / half_width) ** 2,
            "blocks_sigma_high": (_Z * sigma_hi / half_width) ** 2,
            "blocks_point_median": (_Z * _MEDIAN_FACTOR * sd / half_width) ** 2,
        })
    return {"samples": samples, "n": n, "mean": mean, "sd": sd, "cv": sd / mean,
            "median": statistics.median(samples),
            "sigma_ci": (sigma_lo, sigma_hi), "rows": rows}


def print_sizing() -> None:
    s = sizing()
    print(f"nmap -sn wall clock, n={s['n']}: {s['samples']}")
    print(f"  mean {s['mean']:.2f}s  median {s['median']:.2f}s  sd {s['sd']:.2f}s  "
          f"cv {s['cv']:.2f}")
    print(f"  sigma 95% CI [{s['sigma_ci'][0]:.2f}s, {s['sigma_ci'][1]:.2f}s]  "
          f"— a factor of {s['sigma_ci'][1] / s['sigma_ci'][0]:.0f}, which is what four "
          f"samples buys")
    print()
    print(f"  {'CI half-width':>16}  {'blocks (mean)':>13}  {'if sigma low':>12}  "
          f"{'if sigma high':>13}  {'blocks (median)':>15}")
    for row in s["rows"]:
        print(f"  +/-{row['half_width_fraction'] * 100:>3.0f}% "
              f"({row['half_width_seconds']:>5.2f}s)  "
              f"{row['blocks_point']:>13.0f}  {row['blocks_sigma_low']:>12.0f}  "
              f"{row['blocks_sigma_high']:>13.0f}  {row['blocks_point_median']:>15.0f}")
    print()
    print(sizing_note(s))


def sizing_note(s: dict | None = None) -> str:
    """The prose of the sizing result, with every number computed from the samples.

    Written as a formatter rather than a paragraph because a hand-typed number in a
    note beside a table it describes is a number that drifts the first time a sample is
    added — which happened once already while this module was being written.
    """
    s = s or sizing()
    sd, mean = s["sd"], s["mean"]
    sigma_lo, sigma_hi = s["sigma_ci"]

    def median_halfwidth(n, sigma=sd):
        return _Z * _MEDIAN_FACTOR * sigma / math.sqrt(n) / mean

    def blocks(fraction, sigma):
        return (_Z * sigma / (fraction * mean)) ** 2

    body = f"""\
What this implies for 0.6, so the pilot has a number to test rather than invent:

  * PROTOCOL.md fixes n >= 30 blocks per stratum. At the point estimate (sigma =
    {sd:.2f}s) that buys a +/-{_Z * sd / math.sqrt(30) / mean * 100:.0f}% confidence
    interval on nmap's MEAN time within a stratum, and about
    +/-{median_halfwidth(30) * 100:.0f}% on its median — not the +/-10% a reader will
    assume. Pooled across four strata (n = 120) the median interval tightens to about
    +/-{median_halfwidth(120) * 100:.0f}%.
  * That is adequate for the hypothesis tests and marginal for the headline number.
    H1 and H2 are rank comparisons: netsanity ran 0.37-0.71 s against nmap's
    {min(s['samples']):.1f}-{max(s['samples']):.1f} s with no overlap at all, so
    Mann-Whitney separates them at n well under 10 per group. What n >= 30 is buying
    is a publishable interval around nmap's median, and there it is thin.
  * The pilot's real job is to pin sigma, not to confirm 30. {s['n']} samples admit
    sigma anywhere in [{sigma_lo:.1f}s, {sigma_hi:.1f}s], and the block count scales
    with sigma squared: a +/-25% interval needs {blocks(0.25, sigma_lo):.0f} blocks at
    the bottom of that range and {blocks(0.25, sigma_hi):.0f} at the top. The seven-day
    window supplies about 120 per condition. If the pilot's sigma lands in the upper
    half of that interval, the protocol's headline number has to become a wider
    interval or a different statistic, and that is an amendment to write before
    collection rather than a surprise to find after it.
  * Recommended pilot size: at least 10 blocks rather than the 3 PHASE0 names, because
    3 cannot distinguish those cases -- with 3 samples the 95% interval on sigma spans
    a factor of 12. 10 blocks roughly halves it, and costs about an hour at a 15 s
    cooldown.
"""
    # Reflowed rather than hand-wrapped: the numbers above are interpolated and change
    # width, so any fixed line breaks around them go ragged the moment a sample is added.
    out = []
    for para in body.split("\n  * "):
        prefix, indent = ("  * ", "    ") if out else ("", "")
        out.append(textwrap.fill(" ".join(para.split()), width=84,
                                 initial_indent=prefix, subsequent_indent=indent))
    return "\n".join(out) + "\n"


# ── the block ─────────────────────────────────────────────────────────────────────

def _break_responder(name: str, *, down: bool) -> dict:
    """Take one responder's link down, or bring it back. The 0.6 pilot's injected fault.

    A link that is down receives nothing and sends nothing, while the namespace, the
    address and the listeners are all still there — so the manifest and the inventory
    both still list the host and only the capture does not. That is exactly the
    disagreement PROTOCOL.md section 3 says excludes a run, produced by a fault a real
    testbed could suffer, rather than by a flag that stamps a record "excluded".
    """
    entry = next((r for r in json.loads(oracles_mod.MANIFEST.read_text())["responders"]
                  if r["name"] == name), None)
    if entry is None:
        raise SystemExit(f"--inject-fault names {name!r}, which is not in the manifest")
    state = "down" if down else "up"
    proc = oracles_mod._guest(
        entry["machine"],
        f"ip netns exec {name} ip link set {entry['interface']} {state}",
        check=False,
    )
    if proc.returncode != 0:
        raise SystemExit(f"could not take {name}'s link {state}: {proc.stderr.strip()}")
    return {"responder": name, "address": entry["address"], "machine": entry["machine"],
            "interface": entry["interface"], "state": state,
            "detail": f"{name} ({entry['address']}) link {state} on {entry['machine']}"}


def existing_blocks(path: Path) -> set[int]:
    if not path.exists():
        return set()
    seen = set()
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                try:
                    seen.add(json.loads(line)["block_id"])
                except (json.JSONDecodeError, KeyError):
                    raise SystemExit(
                        f"{path} contains a line that is not a run record. The harness "
                        f"will not append to a file it cannot read back."
                    )
    return seen


def run_block(*, block_id: int, seed: int, args, provenance: dict,
              chosen: list, out_path: Path, raw_dir: Path,
              capture_dir: Path, store_dir: Path,
              inject_fault: tuple[str, int] | None = None) -> list[dict]:
    rng = random.Random(seed)
    order = list(chosen)
    rng.shuffle(order)

    # Oracle one, read once per block: the manifest is a checked-in file and cannot
    # change under a running block, so reading it per run would record the same thing
    # thirteen times. The other two are read per run, because they can.
    if args.dry_run:
        manifest = {"status": "stubbed", "addresses": []}
    else:
        manifest = oracles_mod.manifest_oracle()
        if manifest["status"] != "ok":
            raise SystemExit(
                "the testbed manifest is missing, so there is no ground truth to score "
                "recall against and this block is not evidence: run `netbed.py "
                "configure` first"
            )

    # Sampled once per block rather than once per run, and the field says so.
    # `system_profiler` takes ~10 s to answer, which between two timed runs would be a
    # ten-second stall inside the sequence — a covariate that perturbs the thing it is
    # meant to describe. Wi-Fi state can drift inside a block; a block-level sample is
    # the honest compromise and it is labelled rather than presented as per-run.
    wifi = (
        {"status": "stubbed", "airtime_utilisation": None}
        if args.dry_run else capture_mod.wifi_covariates(args.iface)
    )
    wifi["sampled"] = "once per block, at block start"

    flush = capture_mod.flush_neighbour_table(stub=args.dry_run)
    cache_state = "cold" if flush.get("flushed") or args.dry_run else "warm"
    if not args.dry_run and not flush.get("flushed"):
        raise SystemExit(
            "the neighbour table could not be flushed, so this block's cache state is "
            f"unknown and it is not evidence: {flush.get('error')}"
        )

    print(f"block {block_id} seed {seed} cache {cache_state}: "
          + " ".join(c.id for c in order))

    records = []
    for index, condition in enumerate(order):
        if index or args.cooldown_first:
            time.sleep(args.cooldown if not args.dry_run else 0.0)

        run_id = f"b{block_id:04d}-{index:02d}-{uuid.uuid4().hex[:8]}"
        xml_path = raw_dir / f"{run_id}.nmap.xml"
        # One history store per run, named after the run, never reused.  See the note
        # above `_NS` in conditions.py: a shared store puts a compaction rewrite inside
        # one measured run in N, and which run pays drifts with the size of the file.
        # These are kept rather than deleted — each is a few lines and it is the record
        # of what that run actually wrote.
        argv = condition.render(
            netsanity=args.netsanity, nmap=args.nmap, cidr=args.cidr,
            iface=args.iface, nmap_xml=str(xml_path), fixed_ms="50",
            store=str(store_dir / f"{run_id}.history.ndjson"),
        )

        # 0.6 breaks one run on purpose, to prove a broken run is excluded rather than
        # absorbed. The fault is real — a responder's link is taken down for the length
        # of the run — so the detection machinery has to notice it unaided; the flag
        # only decides when. See `_break_responder`.
        broken = None
        if inject_fault and index == inject_fault[1] and not args.dry_run:
            broken = _break_responder(inject_fault[0], down=True)
            print(f"  ! injected fault: {broken['detail']}")

        # Oracle three is two captures. The per-responder capture inside each guest is
        # the one that decides recall (it attributes: the probe arrived, the host did
        # or did not answer); the Mac-side one is the segment-wide view the protocol
        # describes, and it is what `capture.status` and the pcap path refer to. The
        # guest captures start first because starting them is several `limactl`
        # round-trips, and the Mac-side one is started last so its attach settle is the
        # only wait between the oracles being armed and the tool running.
        oracle_cap = (None if args.dry_run
                      else oracles_mod.Capture(run_id).start())
        if oracle_cap is not None and oracle_cap.error:
            raise SystemExit(
                f"the per-responder capture could not be started for {run_id} "
                f"({oracle_cap.error}). A run without its oracle is not evidence, so "
                f"the block stops here."
            )

        cap = capture_mod.Capture(
            interface=args.iface,
            pcap_path=capture_dir / f"{run_id}.pcap",
            filter_expr=f"net {args.cidr}",
            stub=args.dry_run,
        )
        cap.start()
        try:
            if args.dry_run:
                outcome = runners.run_stub(condition, argv, raw_dir=raw_dir,
                                           run_id=run_id, xml_path=xml_path)
            elif condition.tool == "netsanity":
                outcome = runners.run_netsanity(
                    argv, raw_dir=raw_dir, run_id=run_id,
                    expect_mode="discovery_only" if "--discovery-only" in argv else "full",
                    expect_engine="privileged" if condition.privilege == "root" else None,
                )
            else:
                outcome = runners.run_nmap(argv, raw_dir=raw_dir, run_id=run_id,
                                           xml_path=xml_path)
        finally:
            capture_record = cap.stop()

        if capture_record["status"] == "failed":
            raise SystemExit(
                f"capture failed for {run_id} ({capture_record['error']}). A run without "
                f"its oracle is not evidence, so the block stops here."
            )

        if args.dry_run:
            oracle = {"status": "stubbed",
                      "note": "dry run: the tools are stubbed and so are the oracles"}
        else:
            # Stopped after the Mac-side capture's drain, so the guests see every reply
            # the Mac saw and one more second of them.
            observed = oracle_cap.stop()
            if observed["status"] != "ok":
                raise SystemExit(
                    f"the per-responder capture failed for {run_id} ({observed['error']}). "
                    f"A run without its oracle is not evidence, so the block stops here."
                )
            inventory = oracles_mod.inventory_oracle()
            verdict = oracles_mod.agree(manifest, inventory, observed)
            oracle = {
                "status": "agree" if verdict["status"] == "agreed" else "disagree",
                "addresses": verdict["addresses"],
                "counts": verdict["counts"],
                "disagreements": verdict["disagreements"],
                # What each address IS, so the analysis can score recall against the
                # composition (H6 turns on which hosts serve a web port) without
                # reaching for the manifest file, which may have been regenerated since.
                "manifest": {
                    "addresses": manifest["addresses"],
                    "by_address": manifest["by_address"],
                    "generated_at_unix": manifest.get("generated_at_unix"),
                },
                "inventory": {"addresses": inventory["addresses"],
                              "machines": inventory["machines"]},
                # Present is frames in or out; answering is frames out. The difference
                # is what separates a scanner miss from a host that was not answering,
                # and it is recorded per address so the analysis can make that call.
                "capture": {"addresses": observed["addresses"],
                            "answering": observed["answering"],
                            "frames_by_address": observed["frames_by_address"],
                            "location": "per responder, inside its network namespace"},
            }
        if broken:
            _break_responder(inject_fault[0], down=False)

        parsed = outcome["parsed"]
        exclusion = None
        if not parsed["ok"]:
            exclusion = {"reason": "parse_failure", "detail": parsed["error"]}
        elif outcome["exit_status"] not in (0, None):
            exclusion = {"reason": "nonzero_exit",
                         "detail": f"exit status {outcome['exit_status']}"}
        elif provenance["local_network_permission"]["verdict"] != "granted":
            exclusion = {
                "reason": "permission_not_asserted",
                "detail": "the Local Network permission was "
                          f"{provenance['local_network_permission']['verdict']} at block "
                          f"start; denial returns zero results rather than an error, so "
                          f"this run's empty-or-small address set is not interpretable",
            }
        elif args.dry_run:
            exclusion = {"reason": "oracle_not_configured",
                         "detail": "dry run: the tools and the oracles are stubbed, so "
                                   "there is no ground truth to score against"}
        elif oracle["status"] == "disagree":
            exclusion = {
                "reason": "oracle_disagreement",
                "detail": "the three oracles do not describe the same segment: "
                          + "; ".join(f"{a} seen by {', '.join(w) or 'nothing'}"
                                      for a, w in oracle["disagreements"].items()),
            }

        if broken:
            # The whole point of breaking a run is that the machinery above catches it
            # without being told. If it did not, the pilot has found the defect it
            # exists to find, and the block stops so the defect is looked at rather
            # than recorded as a clean run.
            if exclusion is None:
                raise SystemExit(
                    f"INJECTED FAULT NOT DETECTED: {broken['detail']}, and the run was "
                    f"about to be recorded as evidence with no exclusion. The exclusion "
                    f"machinery is not working and the pilot's gate is not met."
                )
            exclusion = {
                "reason": "injected_fault",
                "detail": f"deliberately broken by the 0.6 pilot: {broken['detail']}. "
                          f"Detected unaided as {exclusion['reason']}: "
                          f"{exclusion['detail']}",
            }

        record = schema.make_record(
            run_id=run_id, block_id=block_id, block_seed=seed, sequence_index=index,
            condition=condition, argv=argv, dry_run=args.dry_run,
            started_at_unix=outcome["started_at_unix"],
            finished_at_unix=outcome["finished_at_unix"],
            wall_clock_seconds=outcome["wall_clock_seconds"],
            tool_self_reported_seconds=parsed.get("tool_self_reported_seconds"),
            exit_status=outcome["exit_status"],
            stdout_path=outcome.get("stdout_path"),
            stderr_path=outcome.get("stderr_path"),
            found_addresses=parsed["addresses"],
            parse={k: parsed[k] for k in parsed if k != "addresses"},
            cache_state=cache_state,
            provenance=provenance,
            capture=capture_record,
            covariates={
                "wifi": wifi,
                "neighbour_flush": flush,
                "cooldown_seconds": args.cooldown,
                # `time.monotonic()` on macOS is mach_absolute_time, which stops while
                # the machine sleeps; `time.time()` does not. Their disagreement across
                # one run is therefore the seconds the host slept inside it, and a run
                # the host slept through is not a measurement of anything. Recorded
                # rather than acted on: section 7's exclusion list is fixed, and adding a
                # reason to it is an amendment. `caffeinate -i` in the driver is what
                # keeps this at zero; the 0.6 settle measurement, which held no such
                # assertion, is how the gap was noticed.
                "host_asleep_seconds": round(
                    (outcome["finished_at_unix"] - outcome["started_at_unix"])
                    - outcome["wall_clock_seconds"], 3),
            },
            oracle=oracle,
            exclusion=exclusion,
        )
        schema.append(out_path, record)
        records.append(record)
        mark = "x" if exclusion else " "
        print(f"  {mark} {condition.id:26s} {outcome['wall_clock_seconds']:7.3f}s  "
              f"{len(parsed['addresses']):2d} hosts"
              + (f"  [{exclusion['reason']}]" if exclusion else ""))
    return records


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--blocks", type=int, default=1)
    parser.add_argument("--dry-run", action="store_true",
                        help="run the whole structure with the tools stubbed")
    parser.add_argument("--allow-dirty", action="store_true",
                        help="dry runs only: proceed on a dirty tree, stamping the "
                             "records dry_run so they cannot pass for evidence")
    parser.add_argument("--sizing", action="store_true",
                        help="print what nmap's measured variance implies for the "
                             "block count, and exit")
    parser.add_argument("--self-check", action="store_true",
                        help="assert the harness imports nothing from netsanity, and exit")
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--cidr", default="10.10.20.0/24")
    parser.add_argument("--iface", default="en0")
    parser.add_argument("--netsanity", default="netsanity")
    parser.add_argument("--nmap", default="nmap")
    parser.add_argument("--cooldown", type=float, default=10.0,
                        help="fixed inter-run cooldown, seconds. Set by the 0.6 pilot "
                             "from the measured post-exit traffic tail (settle.py): the "
                             "longest, 6.1 s, is the kernel's ARP retries after a "
                             "netsanity sweep, on a fixed schedule; 10 s clears it with "
                             "margin. See FINDINGS-0.6-pilot.md.")
    parser.add_argument("--cooldown-first", action="store_true")
    parser.add_argument("--control-host", action="append", default=[],
                        help="an address known to answer ICMP, used as the positive "
                             "control for the Local Network permission. Repeatable.")
    parser.add_argument("--conditions", default=None,
                        help="comma-separated condition ids; defaults to every ready one")
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--inject-fault", default=None, metavar="RESPONDER[:INDEX]",
                        help="0.6 only: take this responder's link down for run INDEX "
                             "(default 0) of the first block, and stop if the run is "
                             "not excluded. Recorded as `injected_fault`.")
    args = parser.parse_args(argv)

    inject_fault = None
    if args.inject_fault:
        if args.dry_run:
            parser.error("--inject-fault breaks a real responder; it has no dry-run form")
        name, _, index = args.inject_fault.partition(":")
        inject_fault = (name, int(index) if index else 0)

    problems = self_check()
    if problems:
        print("the harness imports from the system under test:", file=sys.stderr)
        for problem in problems:
            print(f"  {problem}", file=sys.stderr)
        return 3
    if args.self_check:
        print(f"self-check: no forbidden imports in {len(list(HARNESS_DIR.glob('*.py')))} "
              f"harness modules")
        return 0
    if args.sizing:
        print_sizing()
        return 0

    if not args.control_host and not args.dry_run:
        parser.error(
            "a live block needs at least one --control-host: an address known to answer "
            "ICMP, used as the positive control for the Local Network permission. "
            "Without one the permission cannot be asserted, and a denied permission "
            "returns zero results rather than an error."
        )

    if args.allow_dirty and not args.dry_run:
        parser.error("--allow-dirty is for dry runs only; a live block on a dirty tree "
                     "produces a number nobody can reproduce")

    out_path = args.out or (DATA / ("dryrun.ndjson" if args.dry_run else "runs.ndjson"))
    # The raw output, captures and stores sit beside the file that references them and
    # are named after it, so the pilot's artifacts (`pilot.ndjson`) cannot be mistaken
    # for collection's (`runs.ndjson`) and a dry run's for either. `runs` keeps the bare
    # names HARNESS.md documents.
    stem = "dryrun" if args.dry_run else out_path.stem
    prefix = "" if stem == "runs" else f"{stem}-"
    raw_dir = DATA / f"{prefix}raw"
    capture_dir = DATA / f"{prefix}captures"
    store_dir = DATA / f"{prefix}stores"
    store_dir.mkdir(parents=True, exist_ok=True)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    chosen = conditions_mod.ready()
    if args.conditions:
        wanted = [w.strip() for w in args.conditions.split(",") if w.strip()]
        unknown = [w for w in wanted if w not in conditions_mod.BY_ID]
        if unknown:
            parser.error(f"unknown condition ids: {unknown}")
        chosen = [conditions_mod.BY_ID[w] for w in wanted]
        still_blocked = [c.id for c in chosen if c.status != conditions_mod.READY]
        if still_blocked:
            parser.error(f"these conditions are blocked on a missing flag: {still_blocked}")

    for condition in conditions_mod.blocked():
        print(f"note: {condition.id} is excluded from every block — it needs "
              f"{condition.requires}", file=sys.stderr)

    try:
        provenance = provenance_mod.collect(
            netsanity=args.netsanity, nmap=args.nmap,
            control_hosts=args.control_host or [],
            segment_prefix=args.cidr.rsplit(".", 1)[0] + ".",
            allow_dirty=args.allow_dirty,
        )
    except provenance_mod.DirtyTree as error:
        print(f"BLOCK ABORTED: {error}", file=sys.stderr)
        return 2

    verdict = provenance["local_network_permission"]["verdict"]
    if verdict != "granted" and not args.dry_run:
        print(
            f"BLOCK ABORTED: the Local Network permission is {verdict}. Denial returns "
            f"zero results rather than an error, so every run in this block would "
            f"produce a well-formed artifact reporting an empty network. Grant it under "
            f"Privacy & Security > Local Network (a command-line build has no bundle, so "
            f"the grant is listed under the terminal) and pass --control-host with an "
            f"address known to answer.",
            file=sys.stderr,
        )
        return 2

    done = existing_blocks(out_path)
    start = (max(done) + 1) if done else 0
    if done:
        print(f"resuming: {len(done)} block(s) already in {out_path}, starting at "
              f"{start}")

    total = 0
    for offset in range(args.blocks):
        block_id = start + offset
        seed = args.seed + block_id if args.seed is not None else random.randrange(2**31)
        total += len(run_block(
            block_id=block_id, seed=seed, args=args, provenance=provenance,
            chosen=chosen, out_path=out_path, raw_dir=raw_dir,
            capture_dir=capture_dir, store_dir=store_dir,
            inject_fault=inject_fault if offset == 0 else None,
        ))
    print(f"\n{total} record(s) appended to {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
