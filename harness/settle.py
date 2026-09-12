"""How long a run's traffic persists after its process has exited. The 0.6 cooldown.

PROTOCOL.md section 5 asks for an inter-run cooldown "long enough that one scan's
traffic cannot affect the next", measured and fixed before collection begins. This is
the measurement. It runs each condition once, exactly as a block would — same argv,
same neighbour-table flush, same Mac-side capture — and then leaves the capture open
for a further `DRAIN` seconds instead of the block's one, so the frames that arrive
after the process has gone are on the record: late echo replies from the slow
responders, the kernel's ARP retries, whatever nmap's broadcast scripts provoked.

It writes the raw tail — every post-exit frame's offset from the moment the process
returned, per condition — to one JSON file, and prints a summary. The summary is a
convenience; the cooldown is chosen from the raw offsets and the choice is written up in
`FINDINGS-0.6-pilot.md` with the file it was read from. Nothing here is evidence for a
hypothesis: it is a property of the apparatus, taken so that a parameter of the
apparatus is a measurement rather than a placeholder.

Not the pilot's blocks. Those run through `collect.py` and `run_block.py`; this is a
side measurement that has to happen first, because the blocks need the number it
produces.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from harness import capture as capture_mod          # noqa: E402
from harness import conditions as conditions_mod    # noqa: E402
from harness import runners                          # noqa: E402

DATA = Path(__file__).resolve().parents[1] / "data"
#: Seconds the capture stays open after the process returns. Long enough that a tail
#: which reaches it is a finding rather than a truncation.
DRAIN = 30.0


def frames_after(pcap: Path, after_unix: float) -> list[dict]:
    """Every frame in the pcap timestamped after `after_unix`, with its offset."""
    proc = subprocess.run(["tcpdump", "-r", str(pcap), "-tt", "-n"],
                          capture_output=True, text=True)
    tail = []
    for line in proc.stdout.splitlines():
        stamp, _, rest = line.partition(" ")
        try:
            at = float(stamp)
        except ValueError:
            continue
        if at > after_unix:
            tail.append({"offset_seconds": round(at - after_unix, 4),
                         "frame": rest[:160]})
    return tail


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--cidr", default="192.168.64.0/24")
    parser.add_argument("--iface", default="bridge100")
    parser.add_argument("--netsanity", required=True)
    parser.add_argument("--nmap", default="nmap")
    parser.add_argument("--out", type=Path, default=DATA / "pilot-settle.json")
    parser.add_argument("--skip", default="nmap.sn.priv.T2",
                        help="comma-separated condition ids to leave out; privileged "
                             "-T2 is eight minutes of the same ARP the other templates "
                             "send, so its tail is theirs")
    parser.add_argument("--drain", type=float, default=DRAIN)
    parser.add_argument("--only", default=None,
                        help="comma-separated condition ids to run; results are merged "
                             "into --out over any earlier result for the same id")
    args = parser.parse_args()

    # The host sleeps after a minute idle on this machine and mach_absolute_time stops
    # while it does, so an unheld measurement of a long run is a measurement of nothing:
    # the first attempt at this reported 1800 s of `-T2` spread over 63 minutes of
    # wall time with the Mac asleep for most of it.
    awake = subprocess.Popen(["caffeinate", "-i", "-w", str(os.getpid())])

    skip = {s.strip() for s in args.skip.split(",") if s.strip()}
    only = {s.strip() for s in (args.only or "").split(",") if s.strip()}
    earlier = []
    if args.out.exists():
        earlier = [r for r in json.loads(args.out.read_text())["results"]
                   if not only or r["condition_id"] not in only]
    raw_dir = DATA / "pilot-settle"
    raw_dir.mkdir(parents=True, exist_ok=True)
    results = []
    for condition in conditions_mod.ready():
        if condition.id in skip or (only and condition.id not in only):
            continue
        run_id = f"settle-{condition.id}"
        xml_path = raw_dir / f"{run_id}.nmap.xml"
        argv = condition.render(
            netsanity=args.netsanity, nmap=args.nmap, cidr=args.cidr, iface=args.iface,
            nmap_xml=str(xml_path), fixed_ms="50",
            store=str(raw_dir / f"{run_id}.history.ndjson"),
        )
        flush = capture_mod.flush_neighbour_table()
        if not flush["flushed"]:
            print(f"cannot flush the neighbour table: {flush['error']}", file=sys.stderr)
            return 2
        cap = capture_mod.Capture(interface=args.iface, pcap_path=raw_dir / f"{run_id}.pcap",
                                  filter_expr=f"net {args.cidr}")
        cap.DRAIN_SETTLE = args.drain
        print(f"{condition.id}: running, then draining {args.drain:.0f}s", flush=True)
        cap.start()
        try:
            if condition.tool == "netsanity":
                outcome = runners.run_netsanity(
                    argv, raw_dir=raw_dir, run_id=run_id,
                    expect_mode="discovery_only" if "--discovery-only" in argv else "full")
            else:
                outcome = runners.run_nmap(argv, raw_dir=raw_dir, run_id=run_id,
                                           xml_path=xml_path)
        finally:
            record = cap.stop()
        if record["status"] != "ok":
            print(f"capture failed: {record['error']}", file=sys.stderr)
            return 2
        tail = frames_after(Path(record["path"]), outcome["finished_at_unix"])
        last = tail[-1]["offset_seconds"] if tail else 0.0
        results.append({
            "condition_id": condition.id,
            "argv": argv,
            "wall_clock_seconds": outcome["wall_clock_seconds"],
            "exit_status": outcome["exit_status"],
            "found_count": len(outcome["parsed"]["addresses"]),
            "finished_at_unix": outcome["finished_at_unix"],
            "drain_seconds": args.drain,
            "pcap": record["path"],
            "frames_after_exit": len(tail),
            "last_frame_offset_seconds": last,
            "tail": tail,
        })
        print(f"  {outcome['wall_clock_seconds']:8.3f}s  {len(outcome['parsed']['addresses']):2d} hosts  "
              f"{len(tail):4d} frames after exit, last at +{last:.3f}s", flush=True)

    args.out.write_text(json.dumps({
        "schema_version": 1,
        "what": "frames on the segment after each condition's process returned",
        "taken_at_unix": time.time(),
        "cidr": args.cidr, "iface": args.iface, "drain_seconds": args.drain,
        "results": earlier + results,
    }, indent=1) + "\n")
    awake.terminate()
    print(f"\nwrote {args.out}")
    longest = max(results, key=lambda r: r["last_frame_offset_seconds"]) if results else None
    if longest:
        print(f"longest tail: {longest['condition_id']} at "
              f"+{longest['last_frame_offset_seconds']:.3f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
