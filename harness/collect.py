#!/usr/bin/env python3
"""The collection driver: which blocks run, and when.

`run_block.py` runs one block of every condition and knows nothing about calendars.
This decides how many blocks each time-of-day stratum still needs, whether now is the
moment to run one, and what to do when something stops working at three in the morning.
It is the only thing in the harness that has an opinion about wall-clock time, and it
computes no statistic: it reads the same append-only NDJSON the analysis reads, counts
what is already there, and shells out to `run_block.py`.

**It keeps no bookkeeping of its own, deliberately.** Every count comes from the data
file. A driver with a progress file has two sources of truth that disagree the first
time it is killed between writing a record and updating its own state, and the
disagreement is silent — you find it in the analysis, weeks later, as a stratum that is
four blocks short of what something claimed. Reading the evidence costs one pass over a
few megabytes and cannot drift from what was actually collected.

A block counts only when the file holds a record for **every** live condition under that
block id. A block interrupted half way leaves its records behind — the file is
append-only and records what happened — and simply never becomes complete, so it is
neither lost nor counted twice. That is the whole of the restart story.

## Why a launchd agent wrapping a supervised loop, rather than one or the other

Both, layered, and the reason is that they solve different halves.

A bare supervised loop dies with its terminal and does not come back after a reboot, and
this runs for seven days. A launchd job that runs one block per invocation would survive
that, but it cannot hold `caffeinate` across the gaps between blocks — the assertion
would drop the moment each block ended, the Mac would sleep in the four-hour trough
between them, and the strata that exist to sample overnight behaviour are exactly the
ones that would not run. So launchd owns liveness across reboots and crashes, and a
long-lived loop inside it owns pacing and the wake assertion.

**A LaunchAgent as the owner, not a root LaunchDaemon, and this one is not a
preference.** A root daemon would make `sudo -n` succeed for free, since root running
sudo is never asked for a password, and that is genuinely tempting. It would also run
the *unprivileged* conditions as root — and unprivileged `nmap -sn` as root is not
unprivileged nmap, it is privileged nmap with a different argv. H1 and H6 both turn on
that distinction, and H6 is a claim about precisely the gap it would erase. Dropping
back with `sudo -u` for those conditions would change the recorded argv of the
measured conditions and put the Local Network permission's process tree in question,
which `FINDINGS-0.5-harness.md` shows is load-bearing and unqueryable. So the agent runs
as the owner, and root arrives through a sudoers entry scoped to three binaries.
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import time
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from harness import conditions  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
DATA = REPO / "Study" / "data"

# ── the strata ────────────────────────────────────────────────────────────────────
#
# Four six-hour windows in local time, because the thing being sampled is the
# household's day: when people are home, when devices are asleep, when the Wi-Fi is
# busy. Local time and not UTC for the same reason, and the driver records the offset
# so a reader can reconstruct the boundaries after a daylight-saving change.
STRATA: dict[str, tuple[int, int]] = {
    "overnight": (0, 6),
    "morning": (6, 12),
    "afternoon": (12, 18),
    "evening": (18, 24),
}

#: PROTOCOL.md section 5. Thirty per stratum is the floor, not the target.
BLOCKS_PER_STRATUM = 30
#: And at least seven consecutive days. The floor is the design: device sleep cycles
#: and household load are what the strata sample, and they have a period of one day.
#: Running thirty morning blocks on one morning samples one morning thirty times.
MINIMUM_DAYS = 7


def stratum_of(when: datetime) -> str:
    for name, (start, end) in STRATA.items():
        if start <= when.hour < end:
            return name
    raise AssertionError(f"no stratum contains hour {when.hour}")


def window_end(when: datetime) -> datetime:
    """When the stratum `when` falls in stops accepting blocks."""
    _, end = STRATA[stratum_of(when)]
    midnight = when.replace(hour=0, minute=0, second=0, microsecond=0)
    return midnight + timedelta(hours=end)


# ── the census, read from the evidence ────────────────────────────────────────────

def census(path: Path, live_ids: set[str], *, include_dry_run: bool = False,
           blocks_per_stratum: int = BLOCKS_PER_STRATUM) -> dict:
    """What has actually been collected, per stratum and per stratum-day.

    Returns complete blocks only. `partial` is reported rather than hidden: a run that
    is interrupted often is a run that is failing in a way nobody has looked at.

    `include_dry_run` is false for collection and true when the driver is itself in dry
    run, which is the only way its own logic can be proved without spending the week it
    exists to manage. The two universes never mix: a real census cannot see a stubbed
    record, so a dry run left lying in the data directory can never inflate a stratum.
    """
    by_block: dict[int, dict] = defaultdict(lambda: {"conditions": set(), "at": None})
    runs = 0
    excluded = 0
    reasons: dict[str, int] = defaultdict(int)
    if path.exists():
        with open(path, encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if record.get("dry_run") and not include_dry_run:
                    continue
                runs += 1
                exclusion = record.get("exclusion")
                if exclusion:
                    excluded += 1
                    reasons[exclusion.get("reason", "unknown")] += 1
                block = by_block[record["block_id"]]
                block["conditions"].add(record["condition_id"])
                started = record.get("started_at_unix")
                if started and (block["at"] is None or started < block["at"]):
                    block["at"] = started

    complete: dict[str, int] = {name: 0 for name in STRATA}
    per_day: dict[tuple[str, str], int] = defaultdict(int)
    days: set[str] = set()
    partial: list[int] = []
    for block_id, block in sorted(by_block.items()):
        if not live_ids.issubset(block["conditions"]) or block["at"] is None:
            partial.append(block_id)
            continue
        when = datetime.fromtimestamp(block["at"])
        name = stratum_of(when)
        day = when.date().isoformat()
        complete[name] += 1
        per_day[(name, day)] += 1
        days.add(day)

    # Coverage and usability are counted separately and on purpose. A block is
    # "complete" when every live condition produced a record, which is a statement
    # about the matrix; whether those records are evidence is the exclusion rate's
    # question and section 7's 5% ceiling answers it. Folding the two together would
    # let a night of denied permissions look like a night of missing blocks, and those
    # want different repairs.
    return {
        "target_per_stratum": blocks_per_stratum,
        "runs": runs,
        "excluded_runs": excluded,
        "exclusion_rate": round(excluded / runs, 4) if runs else 0.0,
        "exclusion_over_ceiling": bool(runs) and (excluded / runs) > 0.05,
        "exclusion_reasons": dict(sorted(reasons.items(), key=lambda kv: -kv[1])),
        "complete": complete,
        "per_stratum_day": {f"{s}/{d}": n for (s, d), n in sorted(per_day.items())},
        "days": sorted(days),
        "distinct_days": len(days),
        "partial_blocks": partial,
        "total_complete": sum(complete.values()),
    }


def daily_quota(blocks_per_stratum: int = BLOCKS_PER_STRATUM,
                minimum_days: int = MINIMUM_DAYS) -> int:
    """How many blocks one stratum may take in one day.

    Thirty blocks over a seven-day floor is 4.3 a day, so five — which reaches thirty on
    day six and leaves a day of slack for a night that fails. Capping this is the
    mechanism that stops the driver satisfying a stratum in an afternoon and calling the
    design met: `PROTOCOL.md` asks for thirty blocks *across seven days*, and thirty
    blocks in one day is a different experiment with the same block count.
    """
    return -(-blocks_per_stratum // minimum_days) + 1


# ── running one block ─────────────────────────────────────────────────────────────

class Halt(Exception):
    """Something a person has to fix. The driver stops rather than skipping."""


def run_one_block(args, log) -> None:
    argv = [
        sys.executable, str(Path(__file__).parent / "run_block.py"),
        "--blocks", "1",
        "--out", str(args.out),
        "--cidr", args.cidr,
        "--iface", args.iface,
        "--netsanity", args.netsanity,
        "--cooldown", str(args.cooldown),
    ]
    for host in args.control_host:
        argv += ["--control-host", host]
    if args.dry_run:
        argv += ["--dry-run", "--allow-dirty"]

    log(f"block starting: {' '.join(argv[1:])}")
    started = time.monotonic()
    proc = subprocess.run(argv, capture_output=True, text=True)
    elapsed = time.monotonic() - started

    for line in (proc.stdout or "").splitlines():
        log(f"  | {line}")
    if proc.returncode != 0:
        for line in (proc.stderr or "").strip().splitlines():
            log(f"  ! {line}")
        raise Halt(
            f"run_block.py exited {proc.returncode} after {elapsed:.0f}s.\n"
            f"{(proc.stderr or '').strip()}"
        )
    log(f"block finished in {elapsed:.0f}s")


# ── reporting, because nobody is watching at 03:00 ────────────────────────────────

def make_logger(path: Path):
    def log(message: str) -> None:
        stamp = datetime.now().isoformat(timespec="seconds")
        line = f"{stamp}  {message}"
        print(line, flush=True)
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(line + "\n")
            handle.flush()
            os.fsync(handle.fileno())
    return log


def write_status(path: Path, state: str, detail: str, snapshot: dict) -> None:
    payload = {
        "state": state,
        "detail": detail,
        "updated": datetime.now().isoformat(timespec="seconds"),
        "protocol_blocks_per_stratum": BLOCKS_PER_STRATUM,
        "protocol_minimum_days": MINIMUM_DAYS,
        **snapshot,
    }
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, indent=1) + "\n")
    tmp.replace(path)


def raise_alarm(path: Path, reason: str, snapshot: dict) -> None:
    """The loud failure. A file a person finds, saying what stopped and why.

    Collection halting is not the bad outcome — a gap nobody notices is. So this is
    written where someone looking at the data directory cannot miss it, and the driver
    exits 0 so launchd leaves it alone rather than restarting into the same wall.
    """
    path.write_text(
        "COLLECTION STOPPED\n"
        "==================\n\n"
        f"when:  {datetime.now().isoformat(timespec='seconds')}\n\n"
        f"why:\n{reason}\n\n"
        f"where it had got to:\n{json.dumps(snapshot, indent=1)}\n\n"
        "Nothing will run until this file is dealt with. The driver checks for it at\n"
        "startup and refuses to begin while it exists, because whatever stopped\n"
        "collection is still true until someone says otherwise.\n\n"
        "When it is fixed: delete this file. The census is read from the NDJSON, so\n"
        "the driver picks up exactly where the data says it is.\n"
    )


# ── the loop ──────────────────────────────────────────────────────────────────────

def hold_awake(log) -> subprocess.Popen | None:
    """`caffeinate -i` for as long as this process lives.

    `-i` only: it prevents idle *system* sleep and says nothing about the display, and
    nothing at all about the machines being observed. Their sleep cycle is part of what
    the strata sample, so keeping them awake would remove the thing being measured.
    `-w` on our own pid means the assertion dies when we do, including when we are
    killed, so a crashed driver does not leave a Mac that will never sleep again.
    """
    try:
        proc = subprocess.Popen(["caffeinate", "-i", "-w", str(os.getpid())])
        log(f"caffeinate -i held for pid {os.getpid()} (caffeinate pid {proc.pid})")
        return proc
    except FileNotFoundError:
        log("! caffeinate not found: the host may sleep and blocks may be missed")
        return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--out", type=Path, default=DATA / "runs.ndjson")
    parser.add_argument("--log", type=Path, default=DATA / "collect.log")
    parser.add_argument("--status", type=Path, default=DATA / "collect-status.json")
    parser.add_argument("--alarm", type=Path, default=DATA / "COLLECTION-STOPPED.txt")
    parser.add_argument("--cidr", default="192.168.64.0/24")
    parser.add_argument("--iface", default="bridge100")
    parser.add_argument("--netsanity", required=False, default=str(
        Path("/Users/jc/Dev/InfinityCastle-collection/Packages/netsanity-cli"
             "/.build/release/netsanity")))
    parser.add_argument("--control-host", action="append", default=[])
    parser.add_argument("--cooldown", type=float, default=15.0,
                        help="0.6 sets this; the default is a placeholder until then")
    parser.add_argument("--dry-run", action="store_true",
                        help="stub the tools, so the driver's own logic can be proved "
                             "without spending a week of wall clock on it")
    parser.add_argument("--once", action="store_true",
                        help="run at most one block and return, for testing the loop")
    parser.add_argument("--census", action="store_true",
                        help="print what the data says and exit, changing nothing")
    parser.add_argument("--poll", type=float, default=60.0,
                        help="seconds between decisions when there is nothing to do")
    # The protocol's numbers are the defaults and the collection run passes neither.
    # They are flags because 0.6's pilot is a handful of blocks rather than 120, and
    # because a driver whose targets are constants cannot be proved end to end without
    # waiting a week to watch it. Anything other than the defaults is a pilot or a
    # rehearsal, and the status file records what was in force.
    parser.add_argument("--blocks-per-stratum", type=int, default=BLOCKS_PER_STRATUM)
    parser.add_argument("--minimum-days", type=int, default=MINIMUM_DAYS)
    parser.add_argument("--daily-quota", type=int, default=None,
                        help="override the derived per-stratum-per-day cap")
    args = parser.parse_args()

    live = conditions.ready()
    live_ids = {c.id for c in live}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    target = args.blocks_per_stratum
    days_floor = args.minimum_days
    quota = args.daily_quota or daily_quota(target, days_floor)

    def look() -> dict:
        return census(args.out, live_ids, include_dry_run=args.dry_run,
                      blocks_per_stratum=target)

    if args.census:
        print(json.dumps(look(), indent=1))
        return 0

    log = make_logger(args.log)

    if args.alarm.exists():
        log(f"! refusing to start: {args.alarm} exists")
        log("! whatever stopped collection is still true until a person says otherwise")
        return 0

    if not args.control_host and not args.dry_run:
        log("! refusing to start: no --control-host, so the Local Network permission "
            "cannot be asserted and a denied run is indistinguishable from an empty "
            "network")
        return 0

    log(f"driver starting: {len(live)} live conditions, target {target}/stratum over "
        f"at least {days_floor} days, at most {quota} per stratum per day"
        + ("  [DRY RUN: stubbed tools, stubbed records]" if args.dry_run else ""))
    if (target, days_floor) != (BLOCKS_PER_STRATUM, MINIMUM_DAYS):
        log(f"! not the protocol's design: it asks for {BLOCKS_PER_STRATUM}/stratum "
            f"over {MINIMUM_DAYS} days. This run is a pilot or a rehearsal.")
    awake = hold_awake(log)

    stop = {"now": False}
    def on_signal(signum, _frame):
        log(f"signal {signum}: finishing the current wait and stopping")
        stop["now"] = True
    signal.signal(signal.SIGTERM, on_signal)
    signal.signal(signal.SIGINT, on_signal)

    try:
        while not stop["now"]:
            snapshot = look()
            now = datetime.now()
            name = stratum_of(now)
            today = now.date().isoformat()
            done_here = snapshot["per_stratum_day"].get(f"{name}/{today}", 0)
            done_stratum = snapshot["complete"][name]

            if all(n >= target for n in snapshot["complete"].values()) \
                    and snapshot["distinct_days"] >= days_floor:
                log(f"collection complete: {snapshot['complete']} across "
                    f"{snapshot['distinct_days']} days")
                write_status(args.status, "complete", "every stratum has its blocks",
                             snapshot)
                return 0

            reason = None
            if done_stratum >= target:
                reason = f"{name} already has {done_stratum}"
            elif done_here >= quota:
                reason = (f"{name} has its {done_here} for {today}; the "
                          f"{days_floor}-day floor is the design, not a throughput "
                          f"problem")
            else:
                remaining = (window_end(now) - now).total_seconds()
                if remaining < args.cooldown * len(live) + 120:
                    reason = f"too little of the {name} window left ({remaining:.0f}s)"

            if reason:
                write_status(args.status, "waiting", reason, snapshot)
                if args.once:
                    log(f"nothing to do: {reason}")
                    return 0
                time.sleep(args.poll)
                continue

            write_status(args.status, "running",
                         f"{name}, {done_here}/{quota} today, "
                         f"{done_stratum}/{target} overall", snapshot)
            log(f"{name}: {done_here}/{quota} today, {done_stratum}/{target} "
                f"overall — running a block")
            run_one_block(args, log)
            if args.once:
                return 0

    except Halt as halt:
        snapshot = look()
        log(f"! HALTED: {halt}")
        raise_alarm(args.alarm, str(halt), snapshot)
        write_status(args.status, "halted", str(halt), snapshot)
        log(f"! wrote {args.alarm}")
        return 0
    except Exception as unexpected:  # noqa: BLE001
        log(f"! CRASHED: {type(unexpected).__name__}: {unexpected}")
        write_status(args.status, "crashed", f"{type(unexpected).__name__}: {unexpected}",
                     look())
        return 1
    finally:
        if awake and awake.poll() is None:
            awake.terminate()

    log("stopped on request")
    write_status(args.status, "stopped", "signal", look())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
