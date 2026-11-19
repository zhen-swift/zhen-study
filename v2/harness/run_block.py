#!/usr/bin/env python3
"""One block of phase 1 or phase 2: every condition once, in an order shuffled by the block's seed. One job.

    python3 v2/harness/run_block.py --phase 2 --block p2-d50-run-007 --dispersion 50 --flush run --seed 123 \
        [--dry-run] [--stub-root] [--only ID,ID] [--cooldown 5]

    shape the testbed to the dispersion (netbed2 apply)
    prime one history store: five scans, the table flushed before each      (if a primed condition runs)
    flush the neighbour table                                                (per block, or before every run)
    for condition in shuffled(conditions):
        cooldown; wait out thermal pressure
        give the run its own history store: absent (empty) or a copy of the primed one
        start the capture; run, timed here; stop the capture
        parse; check what the run reports against what it was given
        append one validated record, fsync

It stops (exit 1, the job goes to `failed/`) rather than skip a condition: the testbed cannot be shaped, the
binary is not the frozen one, the table cannot be flushed, a capture fails, `sudo -n` is refused, the machine
stays hot. A run that went wrong in a way the record can carry (an unparseable artifact, a nonzero exit) is
recorded and excluded with its reason, never dropped.

`--dry-run` runs everything for real but writes under `data/dryrun/`, every record `dry_run: true`. `--stub-root`
(dry runs only) replaces zhen as root, whose line arrives at the freeze (S5), by a stub artifact through the
real parser, `stubbed: true`. Runs under Apple's `/usr/bin/python3`, as the runner starts it (`runner.sh`).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import re
import shutil
import subprocess
import sys
import time
import uuid
from pathlib import Path

HERE = Path(__file__).resolve().parent
V2 = HERE.parent
REPO = V2.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(REPO))

import conditions as C  # noqa: E402
import record as R  # noqa: E402
import zhen as Z  # noqa: E402
from harness import capture as study1_capture  # noqa: E402  study 1's capture, unchanged
from harness import runners as study1_runners  # noqa: E402  study 1's nmap runner and parser, unchanged

STUDY2 = Path(os.environ.get("ZHEN_STUDY2_HOME", "/Users/Shared/zhen-study2"))
DATA = Path(os.environ.get("ZHEN_STUDY2_DATA", str(STUDY2 / "data")))
#: pcaps stay on the mini, outside `data/`: they hold the testbed VMs' hardware addresses, and `/study-sync` copies
#: `data/`. Each record carries the pcap's path, sha256 and the wire counts read from it.
CAPTURES = Path(os.environ.get("ZHEN_STUDY2_CAPTURES", str(STUDY2 / "captures")))
NETBED2 = V2 / "testbed" / "netbed2.py"
ARP = "/usr/sbin/arp"
THERMAL_KEY = "com.apple.system.thermalpressurelevel"
THERMAL_MAX_WAIT = 900.0
THERMAL_POLL = 15.0


def now_iso():
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def text(argv):
    p = subprocess.run(argv, capture_output=True, text=True)
    return p.stdout.strip() if p.returncode == 0 else None


def provenance():
    head = text(["git", "-C", str(REPO), "rev-parse", "HEAD"])
    dirty = text(["git", "-C", str(REPO), "status", "--porcelain", "--untracked-files=no"])
    binary = sha256(C.ZHEN) if os.path.exists(C.ZHEN) else None
    return {
        "repo_commit": head, "repo_dirty": bool(dirty), "binary": C.ZHEN, "binary_sha256": binary,
        "binary_matches_freeze": binary == C.FROZEN["sha256"], "freeze_tag": C.FROZEN["tag"],
        "nmap": C.NMAP, "nmap_version": (text([C.NMAP, "--version"]) or "").splitlines()[:1],
        "python": sys.executable, "python_version": sys.version.split()[0],
        "sw_vers": text(["sw_vers", "-productVersion"]), "build": text(["sw_vers", "-buildVersion"]),
        "model": text(["sysctl", "-n", "hw.model"]), "zone": (os.path.realpath("/etc/localtime").split("zoneinfo/") + [""])[1],
        "utc_offset": time.strftime("%z"), "user": text(["id", "-un"]),
    }


def host_conditions():
    """netbed2's record of the scheduling the job and the VMs run under (S1's finding: it moves timing)."""
    p = subprocess.run([sys.executable, "-c", "import sys, json; sys.path.insert(0, sys.argv[1]); import netbed2; "
                        "print(json.dumps(netbed2.host_conditions()))", str(NETBED2.parent)],
                       capture_output=True, text=True)
    try:
        return json.loads(p.stdout)
    except ValueError:
        return {"error": (p.stderr or p.stdout).strip()[-300:]}


def thermal_level():
    out = text(["notifyutil", "-g", THERMAL_KEY]) or ""
    m = re.search(r"(\d+)\s*$", out)
    return int(m.group(1)) if m else None


def wait_cool():
    """Waits while macOS reports thermal pressure. Returns the record; stops the block if it never clears."""
    start, levels = time.monotonic(), []
    while True:
        level = thermal_level()
        levels.append(level)
        if level in (0, None):
            return {"level": level, "waited_seconds": round(time.monotonic() - start, 1), "levels_seen": levels,
                    "source": f"notifyutil -g {THERMAL_KEY}"}
        if time.monotonic() - start > THERMAL_MAX_WAIT:
            raise SystemExit(f"thermal pressure {level} for {THERMAL_MAX_WAIT:.0f}s: the block stops here")
        time.sleep(THERMAL_POLL)


def table_entries():
    out = text([ARP, "-an"]) or ""
    return sum(1 for line in out.splitlines() if " at " in line and "(incomplete)" not in line)


def flush():
    """`sudo -n arp -a -d` (zhenstudy's grant). A flush that fails stops the block: its cache state is unknown."""
    before = table_entries()
    p = subprocess.run(["sudo", "-n", ARP, "-a", "-d"], capture_output=True, text=True)
    after = table_entries()
    if p.returncode != 0:
        raise SystemExit(f"the neighbour table could not be flushed: {p.stderr.strip()[:200]}")
    return {"argv": ["sudo", "-n", ARP, "-a", "-d"], "entries_before": before, "entries_after": after,
            "at_unix": time.time()}


def load_manifest(d):
    path = DATA / "testbed" / f"d{d}.json"
    m = json.loads(path.read_text())
    if m.get("dispersion") != d:
        raise SystemExit(f"{path} is dispersion {m.get('dispersion')}, not {d}")
    responders = [{k: r.get(k) for k in ("name", "address", "role", "designed_rtt_ms", "answers_icmp",
                                         "tcp_ports", "loss_percent")} for r in m["responders"]]
    return {"path": str(path), "sha256": sha256(path), "dispersion": d,
            "addresses": sorted((r["address"] for r in responders), key=Z._ip_key), "responders": responders}


def apply_testbed(d):
    started = time.monotonic()
    p = subprocess.run([sys.executable, str(NETBED2), "apply", "--manifest", f"d{d}.json"],
                       capture_output=True, text=True)
    if p.returncode != 0:
        raise SystemExit(f"netbed2 apply d{d} failed ({p.returncode}): {(p.stderr or p.stdout).strip()[-400:]}")
    return {"argv": ["netbed2.py", "apply", "--manifest", f"d{d}.json"], "exit_status": 0,
            "seconds": round(time.monotonic() - started, 1), "output_tail": p.stdout.strip().splitlines()[-3:]}


def require_root(chosen, stub_root):
    """`sudo -n -l <binary>` for every root binary the block will run: refused means the block cannot be whole."""
    needed = sorted({c.argv(nmap_xml="x")[2] for c in chosen if c.root and not (c.tool == "zhen" and stub_root)})
    for binary in needed:
        if subprocess.run(["sudo", "-n", "-l", binary], capture_output=True).returncode != 0:
            raise SystemExit(f"`sudo -n` will not run {binary} for this account, so this block's root conditions "
                             f"cannot run. zhen's root line is added at the freeze (S5); a dry run before it "
                             f"passes --stub-root.")


def store_lines(path):
    try:
        with open(path, "rb") as f:
            return sum(1 for _ in f)
    except OSError:
        return None


def prime(store, env_base, log):
    """Five scans of the testbed into `store`, the table flushed before each, so its samples are cold contacts."""
    argv = [C.ZHEN, *C.ZHEN_BASE, *C.MATCHED]
    scans = []
    for i in range(C.PRIMING_SCANS):
        f = flush()
        code, out, err, secs, _, _ = Z.run(argv, env=dict(env_base, ZHEN_HISTORY=str(store)))
        parsed, warnings = Z.parse(out, flags=tuple(C.MATCHED))
        if code != 0 or not parsed["ok"]:
            raise SystemExit(f"priming scan {i + 1} failed ({code}): {(parsed.get('error') or err)[:300]}")
        scans.append({"exit_status": code, "seconds": round(secs, 3), "addresses": parsed["addresses"],
                      "history_samples": parsed["reach"].get("history_samples"), "warnings": warnings,
                      "flush": f})
        log(f"  priming {i + 1}/{C.PRIMING_SCANS}: {len(parsed['addresses'])} hosts, {secs:.2f}s")
    return {"argv": argv, "store": str(store), "store_sha256": sha256(store), "store_lines": store_lines(store),
            "scans": scans}


def run_checks(cond, parsed):
    """What the run reports against what it was given, beyond the parser's own checks. Warnings, as text."""
    out = []
    if cond.tool != "zhen" or not parsed.get("ok"):
        return out
    reach = parsed.get("reach") or {}
    if cond.history == C.EMPTY:
        # `first_scan` is the history policy's state: a learned or fixed run reports false on an empty store
        # (seen in the S2 dry run). Samples are 0 under every policy.
        first_scan_ok = reach.get("first_scan") is True or reach.get("policy") != "history"
        if not first_scan_ok or reach.get("history_samples") not in (0, None):
            out.append(f"empty history but first_scan {reach.get('first_scan')!r}, "
                       f"samples {reach.get('history_samples')!r}")
    elif cond.history == C.PRIMED:
        # zhen read a store with samples. Run as root without env_keep for ZHEN_HISTORY, it would read root's own
        # (SUDO_USER's) store instead, and this is where that shows.
        if reach.get("history_read") is not True or not reach.get("history_samples"):
            out.append(f"primed history but history_read {reach.get('history_read')!r}, "
                       f"samples {reach.get('history_samples')!r}: the run did not read its store")
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--phase", type=int, choices=(1, 2), required=True)
    ap.add_argument("--block", required=True, help="the block's id, unique within the phase")
    ap.add_argument("--dispersion", type=int, choices=(1, 5, 50, 500), required=True)
    ap.add_argument("--flush", choices=("run", "block"), default="run")
    ap.add_argument("--seed", type=int, required=True)
    ap.add_argument("--block-index", type=int, default=0, help="the block's index in its cell (-T2 when %% 4 == 0)")
    ap.add_argument("--only", default="", help="comma-separated condition ids (dry runs)")
    ap.add_argument("--cooldown", type=float, default=5.0)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--stub-root", action="store_true")
    args = ap.parse_args(argv)
    if args.stub_root and not args.dry_run:
        ap.error("--stub-root is for dry runs only")
    if args.phase == 1 and args.flush != "run":
        ap.error("phase 1 flushes before every run (PLAN.md)")

    def log(message):
        print(message, flush=True)

    chosen = C.for_phase(args.phase, block_index=args.block_index)
    if args.only:
        wanted = args.only.split(",")
        unknown = [w for w in wanted if w not in C.BY_ID or C.BY_ID[w].phase != args.phase]
        if unknown:
            ap.error(f"not phase {args.phase} conditions: {unknown}")
        chosen = [c for c in chosen if c.id in wanted]
    order = list(chosen)
    random.Random(args.seed).shuffle(order)

    root = DATA / ("dryrun" if args.dry_run else "") / f"phase{args.phase}"
    raw, stores, caps = root / "raw" / args.block, root / "stores" / args.block, CAPTURES / f"phase{args.phase}" / args.block
    out = root / "runs.ndjson"
    for d in (raw, stores, caps):
        d.mkdir(parents=True, exist_ok=True)
    job = os.environ.get("ZHEN_STUDY2_JOB")
    common = {"schema_version": R.SCHEMA_VERSION, "study": 2, "phase": args.phase, "block_id": args.block,
              "job": job, "dry_run": args.dry_run}

    prov = provenance()
    if not prov["binary_matches_freeze"]:
        raise SystemExit(f"{C.ZHEN} is not the frozen binary ({prov['binary_sha256']})")
    if prov["repo_dirty"] and not args.dry_run:
        raise SystemExit("the repo has uncommitted changes: what ran could not be reproduced")
    require_root(order, args.stub_root)

    applied = apply_testbed(args.dispersion)
    manifest = load_manifest(args.dispersion)
    prov["host_conditions"] = host_conditions()
    # The VMs' own environment variables never reach a scan: each run gets exactly this, plus its store.
    env_base = {"PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "HOME": os.environ.get("HOME", "/var/empty"),
                "LANG": "C"}

    log(f"block {args.block}: phase {args.phase}, d{args.dispersion}, flush per {args.flush}, seed {args.seed}"
        f"{' (dry run)' if args.dry_run else ''}\n  order: {' '.join(c.id for c in order)}")
    primed = None
    if any(c.history == C.PRIMED for c in order):
        primed = prime(stores / "primed.ndjson", env_base, log)
    first_flush = flush()
    R.append(out, {**common, "kind": "block", "written_at": now_iso(), "seed": args.seed,
                   "block_index": args.block_index, "dispersion": args.dispersion, "flush_policy": args.flush,
                   "order": [c.id for c in order], "manifest": manifest, "provenance": prov, "priming": primed,
                   "testbed_apply": applied, "flush_at_start": first_flush})

    for index, cond in enumerate(order):
        if index:
            time.sleep(args.cooldown)
        thermal = wait_cool()
        f = flush() if (args.flush == "run" and index) else None
        cache_state = "cold" if (index == 0 or args.flush == "run") else "warm"
        run_id = f"{args.block}-{index:02d}-{uuid.uuid4().hex[:8]}"

        history, env = {"state": cond.history}, dict(env_base)
        if cond.tool == "zhen":
            store = stores / f"{run_id}.history.ndjson"
            if cond.history == C.PRIMED:
                shutil.copyfile(primed["store"], store)
            history.update(store=str(store), sha256_before=sha256(store) if store.exists() else None,
                           lines_before=store_lines(store))
            env["ZHEN_HISTORY"] = str(store)
        xml = raw / f"{run_id}.nmap.xml"
        argv = cond.argv(nmap_xml=xml)

        cap = study1_capture.Capture(interface=C.IFACE, pcap_path=caps / f"{run_id}.pcap",
                                     filter_expr=f"net {C.CIDR}")
        try:
            cap.start()
        except study1_capture.CaptureFailed as error:
            raise SystemExit(f"capture failed to start for {run_id}: {error}")
        stubbed = cond.tool == "zhen" and cond.root and args.stub_root
        try:
            if stubbed:
                code, stdout, stderr, secs, t0, t1 = 0, Z.stub_artifact(manifest["addresses"], privilege="root",
                                                                        flags=cond.flags), "", 0.0, time.time(), time.time()
            elif cond.tool == "zhen":
                code, stdout, stderr, secs, t0, t1 = Z.run(argv, env=env)
            else:
                nm = study1_runners.run_nmap(argv, raw_dir=raw, run_id=run_id, xml_path=xml)
        finally:
            capture_record = cap.stop()
        if capture_record["status"] != "ok":
            raise SystemExit(f"capture failed for {run_id}: {capture_record.get('error')}")
        capture_record["sha256"] = sha256(capture_record["path"])

        if cond.tool == "zhen":
            if Z.sudo_refused(code, stderr):
                raise SystemExit(f"`sudo -n` refused zhen for {run_id}: {stderr.strip()[:200]}")
            (raw / f"{run_id}.zhen.json").write_text(stdout)
            (raw / f"{run_id}.zhen.err").write_text(stderr)
            parsed, warnings = Z.parse(stdout, privilege=cond.privilege, flags=cond.flags)
            if stubbed:
                warnings = [w for w in warnings if not w.startswith("engine kind")]
            parsed["artifact_path"] = str(raw / f"{run_id}.zhen.json")
            history.update(sha256_after=sha256(history["store"]) if os.path.exists(history["store"]) else None,
                           lines_after=store_lines(history["store"]))
            warnings += run_checks(cond, parsed)
        else:
            code, secs, t0, t1 = nm["exit_status"], nm["wall_clock_seconds"], nm["started_at_unix"], nm["finished_at_unix"]
            parsed, warnings = dict(nm["parsed"]), []
            parsed.update(stdout_path=nm["stdout_path"], stderr_path=nm["stderr_path"], xml_path=nm["xml_path"])
            if parsed.get("ok"):
                parsed["addresses"] = sorted(parsed["addresses"], key=Z._ip_key)

        exclusion = None
        if code != 0:
            exclusion = "timeout" if code == -9 else "nonzero_exit"
        elif not parsed.get("ok"):
            exclusion = "unparseable"
        rec = {**common, "kind": "run", "written_at": now_iso(), "run_id": run_id, "index": index,
               "dispersion": args.dispersion, "flush_policy": args.flush,
               "condition": cond.as_record(), "argv": argv, "env": {k: v for k, v in env.items() if k == "ZHEN_HISTORY"},
               "cache_state": cache_state, "history": history, "thermal": thermal, "flush": f,
               "exit_status": code, "wall_clock_seconds": float(secs), "wall_clock_source": "harness_monotonic",
               "started_at_unix": float(t0), "finished_at_unix": float(t1),
               "binary_sha256": sha256(C.ZHEN) if cond.tool == "zhen" else None,
               "parsed": parsed, "capture": capture_record, "warnings": warnings, "stubbed": stubbed,
               "exclusion": exclusion, "manifest_addresses": manifest["addresses"]}
        R.append(out, rec)
        found = parsed.get("addresses") or []
        hit = len(set(found) & set(manifest["addresses"]))
        log(f"  {index:2d} {cond.id:24s} {cache_state:4s} {secs:7.2f}s  {hit}/{len(manifest['addresses'])} "
            f"{'stub ' if stubbed else ''}{'EXCLUDED ' + exclusion if exclusion else ''}"
            f"{' warnings: ' + '; '.join(warnings) if warnings else ''}")
    log(f"block {args.block} done: {len(order)} runs -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
