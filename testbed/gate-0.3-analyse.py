#!/usr/bin/env python3
"""Read gate 0.3's captures and say which engine each run actually used.

The gate turns on the engine being confirmed from the packet capture rather than from
either tool's own claim, so nothing here reads a tool's output. It reads frames.

`tcpdump -r` needs no privilege — the BPF device is only needed to capture — so this
runs as the owner after the privileged script has written the pcaps.

Counting is done with BPF filters rather than by parsing tcpdump's text, because a
filter that is wrong returns zero and a text parser that is wrong returns something
plausible.
"""

from __future__ import annotations

import json
import pathlib
import re
import subprocess
import sys

CAP = pathlib.Path("Study/data/captures/gate-0.3")
RAW = pathlib.Path("Study/data/raw/gate-0.3")
HOST_IP = "192.168.64.1"


def host_mac() -> str:
    out = subprocess.run(["ifconfig", "bridge100"], capture_output=True, text=True).stdout
    m = re.search(r"ether ([0-9a-f:]{17})", out)
    if not m:
        sys.exit("cannot read bridge100's hardware address")
    return m.group(1)


def count(pcap: pathlib.Path, expr: str) -> int:
    """Frames in `pcap` matching `expr`. A filter error is fatal, never zero."""
    r = subprocess.run(
        ["tcpdump", "-r", str(pcap), "-n", "-q", expr],
        capture_output=True, text=True,
    )
    if r.returncode != 0:
        sys.exit(f"tcpdump failed on {pcap.name} with {expr!r}:\n{r.stderr}")
    return sum(1 for line in r.stdout.splitlines() if line.strip())


def syn_ports(pcap: pathlib.Path, mac: str) -> dict[str, int]:
    """Destination ports of SYNs the host sent, counted."""
    expr = (f"ether src {mac} and tcp[tcpflags] & tcp-syn != 0 "
            f"and tcp[tcpflags] & tcp-ack == 0")
    r = subprocess.run(["tcpdump", "-r", str(pcap), "-n", expr],
                       capture_output=True, text=True)
    ports: dict[str, int] = {}
    for line in r.stdout.splitlines():
        m = re.search(r"> \d+\.\d+\.\d+\.\d+\.(\d+):", line)
        if m:
            ports[m.group(1)] = ports.get(m.group(1), 0) + 1
    return dict(sorted(ports.items(), key=lambda kv: -kv[1]))


def main() -> int:
    if not CAP.is_dir():
        sys.exit(f"{CAP} does not exist — run gate-0.3-privileged.sh first")
    mac = host_mac()
    print(f"host {HOST_IP} at {mac} on bridge100\n")

    rows = []
    for pcap in sorted(CAP.glob("*.pcap")):
        name = pcap.stem
        probes = {
            "arp_request": count(pcap, f"ether src {mac} and arp and arp[6:2] == 1"),
            "icmp_echo": count(pcap, f"ether src {mac} and icmp[icmptype] == 8"),
            "tcp_syn": count(pcap, f"ether src {mac} and tcp[tcpflags] & tcp-syn != 0 "
                                   f"and tcp[tcpflags] & tcp-ack == 0"),
            "udp": count(pcap, f"ether src {mac} and udp and not port 53"),
        }
        replies = {
            "arp_reply_in": count(pcap, f"ether dst {mac} and arp and arp[6:2] == 2"),
            "icmp_echoreply_in": count(pcap, f"ether dst {mac} and icmp[icmptype] == 0"),
            "syn_ack_in": count(pcap, f"ether dst {mac} and tcp[tcpflags] & tcp-syn != 0 "
                                      f"and tcp[tcpflags] & tcp-ack != 0"),
        }
        # ARP appears in every run and means two different things, so the raw count
        # cannot be the discriminator. A host that sends an IP packet to a local
        # address with no neighbour entry makes the KERNEL emit an ARP request first;
        # that is a side-effect of the probe, not the probe. The signal that a tool is
        # genuinely ARP-sweeping is ARP *and nothing else* — it sent no ICMP and no
        # SYN, so the ARP frames cannot be next-hop resolution for anything.
        ip_probes = probes["icmp_echo"] + probes["tcp_syn"]
        engine = []
        if probes["arp_request"]:
            engine.append("ARP" if ip_probes == 0 else "arp(nexthop)")
        if probes["icmp_echo"]:
            engine.append("ICMP")
        if probes["tcp_syn"]:
            engine.append("TCP")
        rows.append({
            "run": name,
            "engine_observed": "+".join(engine) or "none",
            "probes_sent": probes,
            "replies_received": replies,
            "syn_ports": syn_ports(pcap, mac),
            "total_frames": count(pcap, ""),
        })

    width = max(len(r["run"]) for r in rows)
    print(f"{'run'.ljust(width)}  {'engine':18}  {'ARP':>5} {'ICMP':>5} {'SYN':>5}"
          f"  {'arp<-':>5} {'echo<-':>6} {'sa<-':>5}")
    for r in rows:
        p, q = r["probes_sent"], r["replies_received"]
        print(f"{r['run'].ljust(width)}  {r['engine_observed']:18}  "
              f"{p['arp_request']:5} {p['icmp_echo']:5} {p['tcp_syn']:5}  "
              f"{q['arp_reply_in']:5} {q['icmp_echoreply_in']:6} {q['syn_ack_in']:5}")

    print("\nSYN destination ports, per run:")
    for r in rows:
        if r["syn_ports"]:
            print(f"  {r['run']}: {r['syn_ports']}")

    out = RAW / "engines.json"
    out.write_text(json.dumps(rows, indent=1) + "\n")
    print(f"\nwritten to {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
