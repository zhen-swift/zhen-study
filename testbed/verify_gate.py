"""The 0.1 gate, checked from the scanning Mac and nowhere else.

Ten addresses, five configured delays from 1 ms to 500 ms, each within 10% of its
configuration on three consecutive runs, and a distinct hardware address for every one
of them in the neighbour table.

Everything here is measured from outside the segment. The manifest says what the
instrument was set to; this says what it did. Where they disagree the disagreement is
the result, and the exit status is non-zero.
"""

from __future__ import annotations

import json
import re
import socket
import statistics
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
MANIFEST = HERE / "manifest.json"
RESULT = HERE / "gate-0.1.json"

RUNS = 3
PROBES = 30
TOLERANCE_PERCENT = 10.0


def interval_for(target_rtt_ms):
    """Probe spacing.

    Deliberately shorter than the round trip for the slow responders, so a 500 ms
    address is not measured at one sample every three quarters of a second. Overlapping
    probes do not distort the measurement: netem holds each packet for its own delay
    independently and its queue limit is a thousand, so two probes in flight are two
    independent samples rather than one sample and one queueing delay.
    """
    return max(0.1, 0.3 * target_rtt_ms / 1000.0)


def ping_rtts(address, count, interval):
    p = subprocess.run(["ping", "-c", str(count), "-i", str(interval), address],
                       capture_output=True, text=True,
                       timeout=int(count * interval) + 60)
    return [float(m) for m in re.findall(r"time=([0-9.]+)", p.stdout)]


def tcp_rtts(address, port, count, interval):
    """Round trips measured by opening a TCP connection instead of by pinging.

    The composition declared for H6 includes hosts with ICMP switched off, and those
    hosts still carry a shaped delay — netem is on the interface, so it delays their
    handshakes exactly as much as it would have delayed their pings. Ping cannot see
    them, which does not make the delay unverified; it makes it verified by the other
    thing they answer.

    The connect itself is one round trip: SYN out, SYN/ACK back, and the socket is
    writable. What follows on the connection is irrelevant and is not waited for.
    """
    out = []
    for _ in range(count):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5.0)
        start = time.perf_counter()
        try:
            sock.connect((address, port))
            out.append((time.perf_counter() - start) * 1000.0)
        except OSError:
            pass
        finally:
            sock.close()
        time.sleep(interval)
    return out


def summarise(values):
    if not values:
        return None
    v = sorted(values)
    n = len(v)
    q = lambda f: v[min(n - 1, int(f * n))]
    return {"n": n, "min": round(v[0], 4), "p10": round(q(0.10), 4),
            "p50": round(q(0.50), 4), "p90": round(q(0.90), 4),
            "max": round(v[-1], 4), "stdev": round(statistics.pstdev(v), 4) if n > 1 else 0.0}


def normalise_mac(mac):
    """macOS `arp` prints 52:55:55:d:3b:4a where Linux prints 52:55:55:0d:3b:4a.

    The same hardware address, written two ways. Comparing the strings made the gate
    fail on three of ten responders that were in fact configured correctly, which is
    exactly the kind of false alarm that gets a check quietly relaxed later. Both sides
    are reduced to zero-padded lower case before they are compared.
    """
    if mac is None:
        return None
    return ":".join(part.rjust(2, "0").lower() for part in mac.split(":"))


def neighbour_table():
    """The Mac's own view of who is on the segment, by hardware address."""
    p = subprocess.run(["arp", "-an"], capture_output=True, text=True)
    table = {}
    for line in p.stdout.splitlines():
        m = re.search(r"\((\d+\.\d+\.\d+\.\d+)\) at ([0-9a-f:]+)", line)
        if m and "incomplete" not in line:
            table[m.group(1)] = normalise_mac(m.group(2))
    return table


def main():
    if not MANIFEST.exists():
        raise SystemExit("no manifest.json; run `netbed.py configure` first")
    manifest = json.loads(MANIFEST.read_text())
    responders = manifest["responders"]

    runs = []
    for run_index in range(1, RUNS + 1):
        print(f"\nrun {run_index} of {RUNS}", flush=True)
        print(f"  {'name':<6} {'address':<15} {'target':>8} {'p50':>10} "
              f"{'error':>8} {'p10':>9} {'p90':>10} {'sd':>7}")
        measurements = []
        for r in responders:
            # How this responder is asked depends on what it answers. A host with ICMP
            # filtered is measured over TCP; a host that answers neither is not measured
            # at all, and says so rather than being recorded as a failure.
            method = "icmp"
            if not r.get("answers_icmp", True):
                method = "tcp" if r.get("tcp_ports") else "none"
            if method == "none":
                measurements.append({"name": r["name"], "address": r["address"],
                                     "target_rtt_ms": r["target_rtt_ms"],
                                     "method": "none", "unmeasurable": True})
                print(f"  {r['name']:<6} {r['address']:<15} "
                      f"{r['target_rtt_ms']:>8} {'(answers nothing)':>10}")
                continue
            if method == "tcp":
                port = r["tcp_ports"][0]
                stats = summarise(tcp_rtts(r["address"], port, PROBES,
                                           interval_for(r["target_rtt_ms"])))
            else:
                stats = summarise(ping_rtts(r["address"], PROBES,
                                            interval_for(r["target_rtt_ms"])))
            if stats is None:
                measurements.append({"name": r["name"], "address": r["address"],
                                     "target_rtt_ms": r["target_rtt_ms"],
                                     "unreachable": True})
                print(f"  {r['name']:<6} {r['address']:<15} "
                      f"{r['target_rtt_ms']:>8} {'UNREACHABLE':>10}")
                continue
            error = 100.0 * (stats["p50"] - r["target_rtt_ms"]) / r["target_rtt_ms"]
            measurements.append({"name": r["name"], "address": r["address"],
                                 "target_rtt_ms": r["target_rtt_ms"], "method": method,
                                 "error_percent": round(error, 3), **stats})
            print(f"  {r['name']:<6} {r['address']:<15} {r['target_rtt_ms']:>8} "
                  f"{stats['p50']:>10.3f} {error:>+7.2f}% {stats['p10']:>9.3f} "
                  f"{stats['p90']:>10.3f} {stats['stdev']:>7.3f}", flush=True)
        runs.append(measurements)

    table = neighbour_table()
    seen = {}
    mac_rows = []
    for r in responders:
        mac = table.get(r["address"])
        mac_rows.append({"name": r["name"], "address": r["address"],
                         "mac_in_neighbour_table": mac,
                         "mac_reported_by_guest": normalise_mac(r["mac"]),
                         "agrees": mac == normalise_mac(r["mac"])})
        if mac:
            seen.setdefault(mac, []).append(r["address"])

    print(f"\nneighbour table")
    print(f"  {'name':<6} {'address':<15} {'MAC (arp -an)':<20} "
          f"{'MAC (guest)':<20} {'agree':>6}")
    for row in mac_rows:
        print(f"  {row['name']:<6} {row['address']:<15} "
              f"{str(row['mac_in_neighbour_table']):<20} "
              f"{row['mac_reported_by_guest']:<20} "
              f"{'yes' if row['agrees'] else 'NO':>6}")

    # --- the gate --------------------------------------------------------------
    n_expected = 10
    failures = []
    if len(responders) < n_expected:
        failures.append(f"{len(responders)} responders, gate asks for {n_expected}")
    delays = sorted({r["target_rtt_ms"] for r in responders})
    if len(delays) < 5:
        failures.append(f"{len(delays)} distinct delays, gate asks for 5")
    if delays and (min(delays) > 1.0 or max(delays) < 500.0):
        failures.append(f"delays span {min(delays)}-{max(delays)} ms, "
                        f"gate asks for 1-500")
    for run_index, measurements in enumerate(runs, 1):
        for m in measurements:
            if m.get("unmeasurable"):
                continue
            if m.get("unreachable"):
                failures.append(f"run {run_index}: {m['name']} unreachable")
            elif abs(m["error_percent"]) > TOLERANCE_PERCENT:
                failures.append(f"run {run_index}: {m['name']} "
                                f"{m['error_percent']:+.2f}% off target")
    macs = [row["mac_in_neighbour_table"] for row in mac_rows]
    if any(m is None for m in macs):
        failures.append("some addresses have no hardware address in the neighbour table")
    elif len(set(macs)) != len(macs):
        collapsed = {m: a for m, a in seen.items() if len(a) > 1}
        failures.append(f"hardware addresses collapsed: {collapsed}")
    if any(not row["agrees"] for row in mac_rows):
        failures.append("neighbour table and guest disagree about a hardware address")

    # The composition is part of the gate now. A responder that was supposed to be
    # silent and answers is not a shaping error, it is the segment failing to be the one
    # the protocol pre-declared — and every number derived from that declaration,
    # H6's 0.25 threshold included, would be about a different network.
    for r in responders:
        expected = r.get("verified", {}).get("icmp")
        wanted = "answers" if r.get("answers_icmp", True) else "silent"
        if expected and expected != wanted:
            failures.append(f"{r['name']} is '{expected}' and the plan says '{wanted}'")
    web = sum(1 for r in responders
              if r.get("answers_icmp", True) and r.get("tcp_ports"))
    declared = manifest.get("declared_web_fraction", 0.25)
    if web < declared * len(responders):
        failures.append(
            f"{web} of {len(responders)} responders answer ICMP and serve a probed "
            f"port; PROTOCOL.md's H6 declaration asks for {declared:.0%}"
        )

    worst = max((abs(m.get("error_percent", 0.0))
                 for run in runs for m in run
                 if not m.get("unreachable") and not m.get("unmeasurable")),
                default=float("nan"))
    result = {
        "schema_version": 1,
        "gate": "0.1",
        "runs": RUNS, "probes_per_run": PROBES,
        "tolerance_percent": TOLERANCE_PERCENT,
        "worst_error_percent": round(worst, 3),
        "composition": manifest.get("composition"),
        "measurements": runs,
        "neighbour_table": mac_rows,
        "failures": failures,
        "passed": not failures,
    }
    RESULT.write_text(json.dumps(result, indent=1) + "\n")

    print(f"\nworst error across all {RUNS} runs and {len(responders)} addresses: "
          f"{worst:+.2f}%  (tolerance {TOLERANCE_PERCENT}%)")
    print(f"distinct hardware addresses: {len(set(m for m in macs if m))} "
          f"of {len(mac_rows)}")
    if failures:
        print("\nGATE 0.1 NOT MET:")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("\nGATE 0.1 MET")
    return 0


if __name__ == "__main__":
    sys.exit(main())
