"""Bring up the programmable segment, calibrate it, and record what it actually is.

Host side. Talks to lima and to `ping`; the shaping itself happens inside the guests,
where a delay is imposed by the host that answers rather than by the host that asks.

Three commands:

    python3 netbed.py up          create and start the machines
    python3 netbed.py configure   namespace each responder, shape it, calibrate it
    python3 netbed.py inventory   ask the guests what they are running, as an oracle

`configure` writes `manifest.json`, which records the achieved round-trip time next to
the requested one. The manifest is not a plan — it is a measurement of the instrument,
and every later stage of the study reads the achieved column rather than the target.
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
import subprocess
import sys
import time
from pathlib import Path

import plan

HERE = Path(__file__).resolve().parent
LIMACTL = "/opt/homebrew/bin/limactl"
TEMPLATE = HERE / "lima-responder.yaml"
MANIFEST = HERE / "manifest.json"


def run(cmd, check=True, capture=True, timeout=300):
    p = subprocess.run(cmd, shell=isinstance(cmd, str), capture_output=capture,
                       text=True, timeout=timeout)
    if check and p.returncode != 0:
        raise SystemExit(f"command failed ({p.returncode}): {cmd}\n{p.stderr}")
    return p


def guest(vm, script, check=True):
    """Run a shell script as root inside one machine."""
    return run([LIMACTL, "shell", vm, "--", "sudo", "bash", "-c", script], check=check)


def vm_status(vm):
    p = run([LIMACTL, "list", "--format", "{{.Status}}", vm], check=False)
    return p.stdout.strip()


# --------------------------------------------------------------------------------
# up
# --------------------------------------------------------------------------------

def cmd_up(args):
    for name, responders in plan.machines():
        status = vm_status(name)
        if status == "":
            print(f"{name}: creating ({len(responders)} responders)", flush=True)
            run([LIMACTL, "start", f"--name={name}", "--tty=false", str(TEMPLATE)],
                timeout=900)
        elif status != "Running":
            print(f"{name}: starting", flush=True)
            run([LIMACTL, "start", name, "--tty=false"], timeout=900)
        else:
            print(f"{name}: already running", flush=True)
    print("\nall machines up")


# --------------------------------------------------------------------------------
# configure
# --------------------------------------------------------------------------------

IDLE_INHIBITOR = r"""
set -e
# One core per machine kept out of deep idle, as a supervised unit.
#
# Measured: with the guest allowed into deep idle the round trip from the Mac has a
# median of 0.87 ms and a standard deviation of 1.0 ms; with one core kept busy the
# median falls to 0.33 ms and the deviation to 0.4. The idle-exit path is half a
# millisecond of jitter, which is larger than the smallest delay this segment exists to
# impose -- so without this the 1 ms responder is not merely noisy, it is unmeasurable.
# Four spinners on four cores is worse than one, because the softirq that answers the
# probe then has to compete for a core; the number was measured, not assumed.
#
# systemd-run rather than a detached background job. Two earlier shapes failed: a plain
# `nohup ... &` keeps the ssh channel open so limactl hangs and reports 255, and
# `pkill -f netbed-spin` matches the command line of the very shell running this script
# and kills the session installing the spinner. A transient unit has neither problem,
# survives the session that created it, and can be stopped by name -- which a study
# that runs for seven days needs anyway.
cat > /usr/local/bin/netbed-spin <<'EOS'
#!/bin/sh
while :; do :; done
EOS
chmod +x /usr/local/bin/netbed-spin
systemctl stop netbed-spin.service 2>/dev/null || true
systemd-run --unit=netbed-spin --collect --property=CPUSchedulingPolicy=other \
    /usr/local/bin/netbed-spin >/dev/null 2>&1
systemctl is-active netbed-spin.service
"""


def guest_interfaces(vm):
    """The vmnet-attached interfaces of one machine, with their addresses and MACs."""
    # Not `-br`: brief mode omits both the address family and the hardware address,
    # which are the two fields this needs.
    out = guest(vm, "ip -j addr show").stdout
    data = json.loads(out)
    found = []
    for entry in data:
        name = entry.get("ifname", "")
        if not name.startswith("lima"):
            continue
        addrs = [a["local"] for a in entry.get("addr_info", [])
                 if a.get("family") == "inet"]
        if not addrs:
            continue
        found.append({"ifname": name, "address": addrs[0],
                      "mac": entry.get("address", "")})
    return sorted(found, key=lambda e: e["ifname"])


def reset_machine(vm, responders):
    """Return every responder interface to the root namespace and re-lease it.

    `configure` has to be runnable twice. The first version was not: it read the
    interfaces out of the root namespace, moved them into per-responder namespaces, and
    on the next run found no interfaces at all and refused. Destroying a namespace
    returns its devices to the root one, but they come back down and without addresses,
    so networkd is asked to lease them again — the hardware address has not changed, so
    vmnet's DHCP hands back the same address and the segment keeps its numbering across
    a reconfiguration.
    """
    script = ["set +e"]
    for responder in responders:
        script.append(f"ip netns del {responder.name} 2>/dev/null")
    script += ["sleep 1",
               "for d in $(ls /sys/class/net | grep '^lima'); do ip link set $d up; done",
               "networkctl reconfigure $(ls /sys/class/net | grep '^lima' | tr '\n' ' ') "
               "2>/dev/null",
               "exit 0"]
    guest(vm, "\n".join(script), check=False)


def wait_for_interfaces(vm, wanted, timeout=45):
    """Poll until the machine has `wanted` addressed vmnet interfaces."""
    deadline = time.time() + timeout
    interfaces = []
    while time.time() < deadline:
        interfaces = guest_interfaces(vm)
        if len(interfaces) >= wanted:
            return interfaces
        time.sleep(2.0)
    return interfaces


def namespace_responders(vm, responders, interfaces):
    """Put each responder's interface in its own namespace, with its address kept.

    A namespace per responder rather than a shared stack with tuned arp_ignore: two
    addresses on one stack will answer each other's ARP under some configurations and
    not others, and a testbed whose hardware addresses depend on a sysctl is a testbed
    that will collapse them the moment somebody changes one.
    """
    script = ["set -e"]
    for responder, iface in zip(responders, interfaces):
        ns = responder.name
        script += [
            f"ip netns del {ns} 2>/dev/null || true",
            f"ip netns add {ns}",
            f"ip link set {iface['ifname']} down",
            f"ip link set {iface['ifname']} netns {ns}",
            f"ip -n {ns} addr add {iface['address']}/24 dev {iface['ifname']}",
            f"ip -n {ns} link set {iface['ifname']} up",
            f"ip -n {ns} link set lo up",
        ]
    guest(vm, "\n".join(script))


def set_shaping(vm, ns, ifname, delay_ms, loss_percent):
    parts = f"delay {delay_ms:.4f}ms"
    if loss_percent > 0:
        parts += f" loss {loss_percent:.4f}%"
    guest(vm, f"ip netns exec {ns} tc qdisc replace dev {ifname} root netem {parts}")


def ping_rtts(address, count, interval):
    """Round trips measured from the scanning Mac, in milliseconds.

    Measured here rather than read from the guest: what the study cares about is the
    latency the scanner sees, and a guest reporting its own configuration would be the
    apparatus grading itself.
    """
    p = run(["ping", "-c", str(count), "-i", str(interval), address],
            check=False, timeout=int(count * interval) + 60)
    return [float(m) for m in re.findall(r"time=([0-9.]+)", p.stdout)]


def summarise(values):
    if not values:
        return None
    v = sorted(values)
    n = len(v)
    q = lambda f: v[min(n - 1, int(f * n))]
    return {"n": n, "min": v[0], "p10": q(0.10), "p50": q(0.50), "p90": q(0.90),
            "p99": q(0.99), "max": v[-1], "mean": statistics.fmean(v),
            "stdev": statistics.pstdev(v) if n > 1 else 0.0}


def calibrate(vm, responder, iface, baseline_p50):
    """Close the loop until the measured median sits on the target.

    Open-loop — setting netem to (target minus baseline) and trusting it — overshoots
    by 16% at 1 ms and 23% at 5 ms, measured. The overshoot is the virtio and vmnet path
    plus netem's own timer, it is not constant, and there is no reason to model it when
    it can be measured away. What the manifest records is the netem value that was
    arrived at and the round trip that resulted.
    """
    target = responder.target_rtt_ms
    netem = max(0.02, target - baseline_p50)
    history = []
    stats = None
    for attempt in range(plan.CALIBRATION_ROUNDS):
        set_shaping(vm, responder.name, iface["ifname"], netem, responder.loss_percent)
        time.sleep(0.5)
        stats = summarise(ping_rtts(
            iface["address"], plan.CALIBRATION_PROBES,
            plan.probe_interval_seconds(target)))
        if stats is None:
            raise SystemExit(f"{responder.name} ({iface['address']}) did not answer")
        error = 100.0 * (stats["p50"] - target) / target
        history.append({"round": attempt + 1, "netem_ms": round(netem, 4),
                        "measured_p50_ms": round(stats["p50"], 4),
                        "error_percent": round(error, 3)})
        print(f"    round {attempt + 1}: netem={netem:8.3f} ms  "
              f"p50={stats['p50']:8.3f} ms  err={error:+6.2f}%", flush=True)
        if abs(error) <= plan.CALIBRATION_TOLERANCE_PERCENT:
            break
        netem = max(0.02, netem + (target - stats["p50"]))
    return netem, stats, history


def cmd_configure(args):
    entries = []
    for vm, responders in plan.machines():
        if vm_status(vm) != "Running":
            raise SystemExit(f"{vm} is not running; run `netbed.py up` first")
        print(f"\n{vm}", flush=True)
        guest(vm, IDLE_INHIBITOR)
        reset_machine(vm, responders)
        interfaces = wait_for_interfaces(vm, len(responders))
        if len(interfaces) < len(responders):
            raise SystemExit(
                f"{vm} has {len(interfaces)} addressed vmnet interfaces after a reset, "
                f"needs {len(responders)}")
        interfaces = interfaces[:len(responders)]
        namespace_responders(vm, responders, interfaces)

        # Baseline before any shaping, so calibration starts from measurement rather
        # than from an assumed floor.
        for responder, iface in zip(responders, interfaces):
            set_shaping(vm, responder.name, iface["ifname"], 0.02, 0.0)
        base = []
        for responder, iface in zip(responders, interfaces):
            # An interface that has just changed namespace does not answer for a second
            # or two: the link is re-established and the neighbour state on both sides
            # is stale. Waiting a fixed interval and hoping is how the first version of
            # this failed, on a machine that was perfectly healthy a moment later.
            stats = None
            for attempt in range(6):
                stats = summarise(ping_rtts(iface["address"], 20, 0.1))
                if stats is not None:
                    break
                time.sleep(2.0)
            if stats is None:
                raise SystemExit(
                    f"{vm}/{responder.name} at {iface['address']} did not answer in "
                    f"12 s after being moved into its namespace")
            base.append(stats["p50"])
        baseline = statistics.median(base)
        print(f"  baseline p50 {baseline:.3f} ms", flush=True)

        for responder, iface in zip(responders, interfaces):
            print(f"  {responder.name} {iface['address']} "
                  f"target {responder.target_rtt_ms} ms", flush=True)
            netem, stats, history = calibrate(vm, responder, iface, baseline)
            entries.append({
                "name": responder.name,
                "machine": vm,
                "interface": iface["ifname"],
                "address": iface["address"],
                "mac": iface["mac"],
                "target_rtt_ms": responder.target_rtt_ms,
                "loss_percent": responder.loss_percent,
                "netem_delay_ms": round(netem, 4),
                "achieved": {k: round(v, 4) for k, v in stats.items()},
                "calibration": history,
            })

    manifest = {
        "schema_version": 1,
        "segment": plan.SEGMENT,
        "generated_at_unix": int(time.time()),
        "responders_per_machine": plan.RESPONDERS_PER_VM,
        "responders": entries,
    }
    MANIFEST.write_text(json.dumps(manifest, indent=1) + "\n")
    print(f"\nwrote {MANIFEST} with {len(entries)} responders")


# --------------------------------------------------------------------------------
# inventory
# --------------------------------------------------------------------------------

def cmd_inventory(args):
    """What the guests say they are running.

    An oracle in its own right for 0.4: it is produced by the machines that answer the
    probes, not by the machine that sends them, and it knows nothing about what any
    scanner found.
    """
    out = []
    for vm, responders in plan.machines():
        if vm_status(vm) != "Running":
            out.append({"machine": vm, "status": vm_status(vm) or "absent",
                        "responders": []})
            continue
        found = []
        for responder in responders:
            r = guest(vm, f"""
ip netns exec {responder.name} ip -j addr show 2>/dev/null || echo '[]'
""", check=False)
            try:
                data = json.loads(r.stdout.strip().splitlines()[-1])
            except (json.JSONDecodeError, IndexError):
                data = []
            for entry in data:
                if not entry.get("ifname", "").startswith("lima"):
                    continue
                addrs = [a["local"] for a in entry.get("addr_info", [])
                         if a.get("family") == "inet"]
                qdisc = guest(vm,
                              f"ip netns exec {responder.name} tc qdisc show dev "
                              f"{entry['ifname']}", check=False).stdout.strip()
                found.append({"name": responder.name, "address": addrs[0] if addrs else None,
                              "mac": entry.get("address"), "qdisc": qdisc})
        out.append({"machine": vm, "status": "Running", "responders": found})
    print(json.dumps({"schema_version": 1, "machines": out}, indent=1))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("up").set_defaults(fn=cmd_up)
    sub.add_parser("configure").set_defaults(fn=cmd_configure)
    sub.add_parser("inventory").set_defaults(fn=cmd_inventory)
    args = ap.parse_args()
    return args.fn(args) or 0


if __name__ == "__main__":
    sys.exit(main())
