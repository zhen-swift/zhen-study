"""Study 2's testbed: build it, calibrate it per dispersion, put a dispersion on it, verify it.

Runs on the Mac mini as a runner job (user `zhenstudy`, nobody logged in), from the repo root:

    python3 v2/testbed/netbed2.py up [--only netbedN]    create and start the machines (pinned image)
    python3 v2/testbed/netbed2.py status                  what is running, and can the host reach it
    python3 v2/testbed/netbed2.py rebuild                 delete every machine, then `up`
    python3 v2/testbed/netbed2.py configure --dispersion D    calibrate to ladder D, write d<D>.json
    python3 v2/testbed/netbed2.py apply --manifest d<D>.json  put a calibrated dispersion on the segment
    python3 v2/testbed/netbed2.py verify [--manifest d<D>.json]   S1's gate on what is applied now

The mechanics are study 1's (`testbed/netbed.py`, `testbed/verify_gate.py`), imported and not edited: study 1's
instrument stays as it was measured. What is new here is the ladder per dispersion (`ladder.py`), the cold
first-contact time, `apply` without recalibration, and the record of what is on the segment right now.

Everything is written to `$ZHEN_STUDY2_DATA/testbed/` (default `/Users/Shared/zhen-study2/data/testbed/`); the
repository is read-only to the runner. `/study-sync` brings it back to the MacBook.

`applied.json` is the segment **as it is now**: which manifest's delays are on it, and each responder's current
address and hardware address. A rebuild gives the machines new hardware addresses, so vmnet's DHCP may hand out
new IP addresses; anything that needs to know where the responders are reads `applied.json`, not a manifest.
"""

from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
import os
import re
import statistics
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / "testbed"))

import ladder  # noqa: E402
import netbed  # noqa: E402  study 1's mechanics
import plan  # noqa: E402  study 1's composition
import verify_gate  # noqa: E402  study 1's measurement helpers

TEMPLATE = HERE / "lima-responder.yaml"
LIMACTL = netbed.LIMACTL
OUT = Path(os.environ.get("ZHEN_STUDY2_DATA", "/Users/Shared/zhen-study2/data")) / "testbed"

#: S1's gate (STEPS.md): every measured responder within 10% of its designed round trip.
TOLERANCE_PERCENT = verify_gate.TOLERANCE_PERCENT
VERIFY_RUNS = verify_gate.RUNS
VERIFY_PROBES = verify_gate.PROBES
#: Cold first-contact trials per responder. Each one deletes the host's neighbour entry first.
COLD_TRIALS = 5
#: A calibration that leaves netem more than this below the designed round trip is compensating for something that
#: is not the link. The path itself (virtio, vmnet, netem's timer) costs 0.1-0.3 ms; on 2026-11-19 a ~10 ms host
#: artefact (see `host_conditions`) was calibrated into four manifests and only the rebuild exposed it.
MAX_CORRECTION_MS = 1.0
#: `ps -o pri` of a process macOS runs in background policy (darwinbg). Its timers fire late by up to half their
#: interval, capped near 10 ms, and so do the timers of the virtual machines it starts.
BACKGROUND_PRIORITY = 4


def now_iso():
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")


def stamp():
    return time.strftime("%Y%m%d-%H%M%S")


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=1) + "\n")
    tmp.replace(path)
    print(f"wrote {path}", flush=True)


def sha256_of(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def text(cmd):
    p = subprocess.run(cmd, capture_output=True, text=True)
    return (p.stdout or p.stderr).strip()


def machine_names():
    return [name for name, _ in ladder.machines(500)]


# --------------------------------------------------------------------------------
# provenance
# --------------------------------------------------------------------------------

def image_pin():
    t = TEMPLATE.read_text()
    loc = re.search(r'location:\s*"([^"]+)"', t)
    dig = re.search(r'digest:\s*"([^"]+)"', t)
    return {"location": loc.group(1) if loc else None, "digest": dig.group(1) if dig else None,
            "template_sha256": sha256_of(TEMPLATE)}


def provenance():
    """Where and with what this record was made. No hostnames or LAN addresses: the repository is public."""
    zone = os.path.realpath("/etc/localtime").split("zoneinfo/")[-1]
    commit = text(["git", "-C", str(REPO), "rev-parse", "HEAD"])
    dirty = text(["git", "-C", str(REPO), "status", "--porcelain"])
    return {
        "generated_at": now_iso(), "zone": zone, "utc_offset": time.strftime("%z"),
        "repo_commit": commit, "repo_clean": dirty == "",
        "image": image_pin(),
        "lima": text([LIMACTL, "--version"]),
        "os": f"macOS {text(['sw_vers', '-productVersion'])} ({text(['sw_vers', '-buildVersion'])})",
        "model": text(["sysctl", "-n", "hw.model"]),
        "user": text(["id", "-un"]),
        "host_conditions": host_conditions(),
    }


# --------------------------------------------------------------------------------
# host conditions
# --------------------------------------------------------------------------------

def priority_of(pid):
    out = text(["ps", "-o", "pri=", "-p", str(pid)])
    try:
        return int(out.split()[0])
    except (ValueError, IndexError):
        return None


#: What `leave_background` found and did at start, recorded in `host_conditions`.
STARTED_IN = {}


def leave_background():
    """Take this process, and so everything it starts, out of macOS background policy.

    `setpriority(PRIO_DARWIN_PROCESS, 0, 0)` clears darwinbg set by `taskpolicy -b` (tested: 4 becomes 31, and
    children start at 31), but **not** the background that launchd's `ProcessType Background` imposes (tested on the
    mini 2026-11-19 11:31: rc 0, priority stays 4). Only the runner's plist fixes that, which takes root. Kept
    because it is harmless and its result is recorded; `require_foreground` decides from the priority it reads.
    """
    import ctypes
    before = priority_of(os.getpid())
    rc = None
    if before is not None and before <= BACKGROUND_PRIORITY:
        rc = ctypes.CDLL(None, use_errno=True).setpriority(4, 0, 0)  # PRIO_DARWIN_PROCESS, self, clear
    STARTED_IN.update({"priority_at_start": before, "setpriority_rc": rc, "priority_after": priority_of(os.getpid())})


def host_conditions():
    """The scheduling the testbed runs under, recorded with every result.

    S1's first attempt (2026-11-19) ran under the runner's `ProcessType Background`: the job and lima's host agents
    at priority 4 (darwinbg). Delays came back late by min(half the netem delay, ~10 ms) on whichever responders'
    timers sat on a guest CPU that was allowed to sleep, which is what macOS timer coalescing does to a
    background process's wake-ups. Calibration absorbed it, then a rebuild moved it.
    """
    vm_pids = text(["pgrep", "-U", str(os.getuid()), "-f", "Virtualization.VirtualMachine"]).split()
    agents = text(["pgrep", "-U", str(os.getuid()), "-f", "limactl hostagent"]).split()
    job = priority_of(os.getpid())
    return {"job_priority": job,
            "hostagent_priorities": sorted(p for p in (priority_of(a) for a in agents if a.isdigit()) if p is not None),
            "vm_process_priorities": sorted(p for p in (priority_of(v) for v in vm_pids if v.isdigit())
                                            if p is not None),
            "background": job is not None and job <= BACKGROUND_PRIORITY, "at_start": dict(STARTED_IN)}


def require_foreground(machines=True):
    """Refuse to build, shape or measure the testbed from a background-policy process (see `host_conditions`), or,
    with `machines`, on machines a background-policy job started."""
    h = host_conditions()
    if h["background"]:
        raise SystemExit(f"this job runs in macOS background policy (priority {h['job_priority']}): its timers, and "
                         "those of the machines it starts, are coalesced by up to ~10 ms. The runner's plist must "
                         "say ProcessType Interactive (v2/runner/dev.zhen.study2.runner.plist)")
    stale = [p for p in h["hostagent_priorities"] if p <= BACKGROUND_PRIORITY]
    if machines and stale:
        raise SystemExit(f"{len(stale)} machine(s) were started in background policy; `netbed2.py rebuild` them "
                         "from a foreground job first")
    return h


def parse_arp(output):
    """`arp -an` output to {address: normalised hardware address}, as study 1's `verify_gate.neighbour_table`."""
    table = {}
    for line in output.splitlines():
        m = re.search(r"\((\d+\.\d+\.\d+\.\d+)\) at ([0-9a-f:]+)", line)
        if m and "incomplete" not in line:
            table[m.group(1)] = verify_gate.normalise_mac(m.group(2))
    return table


def neighbour_table():
    """The host's neighbour table, read as root. Returns (table, source).

    macOS hides link-layer addresses from a process without Local Network permission, and Homebrew's `python3`
    runs as an app (`Python.app`), so anything it starts inherits that: from it, `arp -an` and `netstat -rnl` show
    no hardware addresses at all, while the same commands from a shell show them all (2026-11-19). Root is not
    filtered, and `/usr/sbin/arp` is in zhenstudy's grant. Study 1's plain `arp -an` is the fallback, and the
    source is recorded either way.
    """
    p = subprocess.run(["sudo", "-n", "/usr/sbin/arp", "-an"], capture_output=True, text=True)
    if p.returncode == 0:
        return parse_arp(p.stdout), "sudo -n /usr/sbin/arp -an"
    p = subprocess.run(["/usr/sbin/arp", "-an"], capture_output=True, text=True)
    return parse_arp(p.stdout), "arp -an (sudo refused)"


# --------------------------------------------------------------------------------
# up · status · rebuild
# --------------------------------------------------------------------------------

def cmd_up(args):
    require_foreground()
    names = [args.only] if args.only else machine_names()
    for name in names:
        status = netbed.vm_status(name)
        if status == "":
            print(f"{name}: creating", flush=True)
            netbed.run([LIMACTL, "start", f"--name={name}", "--tty=false", str(TEMPLATE)], timeout=1800)
        elif status != "Running":
            print(f"{name}: starting ({status})", flush=True)
            netbed.run([LIMACTL, "start", name, "--tty=false"], timeout=900)
        else:
            print(f"{name}: already running", flush=True)
    print("up: done", flush=True)


def bridge_address():
    p = subprocess.run(["ifconfig", "bridge100"], capture_output=True, text=True)
    m = re.search(r"inet (\d+\.\d+\.\d+\.\d+)", p.stdout)
    return {"present": p.returncode == 0, "inet": m.group(1) if m else None}


def cmd_status(args):
    """A snapshot meant to be read by a later job: does a machine started by an earlier job still run?"""
    listing = subprocess.run([LIMACTL, "list", "--format", "json"], capture_output=True, text=True)
    vms = []
    for line in listing.stdout.splitlines():
        try:
            v = json.loads(line)
        except json.JSONDecodeError:
            continue
        vms.append({"name": v.get("name"), "status": v.get("status"), "vmType": v.get("vmType")})
    machines = []
    for v in vms:
        entry = dict(v)
        if v["status"] == "Running":
            ifaces = netbed.guest_interfaces(v["name"])
            netns = netbed.guest(v["name"], "ip netns list | wc -l", check=False).stdout.strip()
            entry["root_namespace_interfaces"] = ifaces
            entry["responder_namespaces"] = int(netns or 0)
            entry["guest_cpus"] = netbed.guest(v["name"], "nproc", check=False).stdout.strip()
            entry["ping_from_host"] = {i["address"]: verify_gate.summarise(netbed.ping_rtts(i["address"], 3, 0.2))
                                       for i in ifaces}
        machines.append(entry)
    as_root, source = neighbour_table()
    plain = verify_gate.neighbour_table()
    segment = ipaddress.ip_network(plan.SEGMENT)
    who = [" ".join(line.split()[:2]) for line in text(["who"]).splitlines()]  # user and line only: no remote hosts
    out = {"schema_version": 2, "what": "netbed2 status", "provenance": provenance(),
           "users_logged_in": who, "bridge100": bridge_address(), "machines": machines,
           "neighbour_table": {"source": source,
                               "as_root": {a: m for a, m in sorted(as_root.items()) if ipaddress.ip_address(a) in segment},
                               "plain_arp_from_python": {a: m for a, m in sorted(plain.items())
                                                         if ipaddress.ip_address(a) in segment}}}
    write_json(OUT / f"status-{stamp()}.json", out)
    for m in machines:
        print(f"  {m['name']}: {m['status']}", flush=True)
    print(f"  bridge100: {out['bridge100']}", flush=True)
    return 0 if vms and all(m["status"] == "Running" for m in machines) else 1


def cmd_rebuild(args):
    require_foreground(machines=False)  # replacing machines started in background policy is what this is for
    for name in machine_names():
        if netbed.vm_status(name):
            print(f"{name}: deleting", flush=True)
            netbed.run([LIMACTL, "delete", "-f", name], timeout=300)
    applied = OUT / "applied.json"
    if applied.exists():
        applied.unlink()  # nothing is applied to machines that no longer exist
    args.only = None
    cmd_up(args)


# --------------------------------------------------------------------------------
# cold first contact
# --------------------------------------------------------------------------------

def probe_method(r):
    """How a responder is asked, by what it answers: study 1's rule (verify_gate)."""
    if r["answers_icmp"]:
        return "icmp"
    return "tcp" if r["tcp_ports"] else "none"


def one_ping_ms(address, wait_ms):
    p = subprocess.run(["ping", "-c", "1", "-W", str(int(wait_ms)), address],
                       capture_output=True, text=True, timeout=wait_ms / 1000 + 10)
    m = re.search(r"time=([0-9.]+)", p.stdout)
    return float(m.group(1)) if m else None


def cold_first_contact(r, address):
    """The first probe to a host the scanner has no neighbour entry for.

    Before each trial the host's entry is deleted (`sudo -n /usr/sbin/arp -d`, inside zhenstudy's grant), so the
    probe waits for ARP first. netem delays the responder's ARP reply as it delays everything else it sends, so
    the expected value is about twice the round trip. Lost trials are recorded as lost, not retried.
    """
    method = probe_method(r)
    if method == "none":
        return {"method": "none", "unmeasurable": True}
    designed = r["designed_rtt_ms"]
    trials = []
    for _ in range(COLD_TRIALS):
        d = subprocess.run(["sudo", "-n", "/usr/sbin/arp", "-d", address], capture_output=True, text=True)
        if d.returncode != 0:
            return {"method": method, "unmeasured": f"arp -d failed: {(d.stderr or d.stdout).strip()}"}
        if method == "icmp":
            ms = one_ping_ms(address, max(2000, 10 * designed))
        else:
            got = verify_gate.tcp_rtts(address, r["tcp_ports"][0], 1, 0)
            ms = got[0] if got else None
        trials.append(None if ms is None else round(ms, 4))
        time.sleep(max(0.2, 2 * designed / 1000))
    answered = [t for t in trials if t is not None]
    med = statistics.median(answered) if answered else None
    return {"method": method, "trials_ms": trials, "lost": len(trials) - len(answered),
            "median_ms": None if med is None else round(med, 4),
            "ratio_to_designed": None if med is None else round(med / designed, 3)}


# --------------------------------------------------------------------------------
# configure · apply
# --------------------------------------------------------------------------------

def prepare_machine(vm, responders):
    """Study 1's sequence up to shaping: spinner, reset, namespaces, listeners. Returns the interfaces."""
    netbed.guest(vm, netbed.IDLE_INHIBITOR)
    netbed.reset_machine(vm, responders)
    interfaces = netbed.wait_for_interfaces(vm, len(responders))
    if len(interfaces) < len(responders):
        raise SystemExit(f"{vm} has {len(interfaces)} addressed vmnet interfaces after a reset, "
                         f"needs {len(responders)}")
    interfaces = interfaces[:len(responders)]
    netbed.namespace_responders(vm, responders, interfaces)
    for responder, iface in zip(responders, interfaces):
        netbed.start_listeners(vm, responder, iface)
    return interfaces


def check_policy(vm, responder, iface):
    netbed.set_icmp_policy(vm, responder)
    observed = netbed.verify_policy(vm, responder, iface)
    expected = "answers" if responder.answers_icmp else "silent"
    if observed["icmp"] != expected:
        raise SystemExit(f"{responder.name}: ICMP is '{observed['icmp']}', the plan says '{expected}'")
    shut = [p for p, s in observed["ports"].items() if s != "open"]
    if shut:
        raise SystemExit(f"{responder.name}: ports {shut} are not accepting")
    return observed


def responder_record(vm, responder, iface):
    return {"name": responder.name, "machine": vm, "interface": iface["ifname"], "address": iface["address"],
            "mac": iface["mac"], "designed_rtt_ms": responder.target_rtt_ms,
            "target_rtt_ms": responder.target_rtt_ms, "loss_percent": responder.loss_percent,
            "role": responder.role, "answers_icmp": responder.answers_icmp,
            "tcp_ports": list(responder.tcp_ports)}


def segment_header(d):
    return {"study": 2, "dispersion": d, "ladder_ms": list(ladder.ladder(d)), "ladder_rule": ladder.RULE,
            "anchor": "slowest fixed at 500 ms (JC, 2026-11-18)",
            "designed_dispersion": round(ladder.achieved_dispersion(d), 3),
            "segment": plan.SEGMENT, "composition": plan.composition(),
            "declared_web_fraction": plan.DECLARED_WEB_FRACTION,
            "responders_per_machine": plan.RESPONDERS_PER_VM}


def large_corrections(entries):
    """Pure: responders whose calibrated netem sits more than MAX_CORRECTION_MS below their designed round trip."""
    return [e["name"] for e in entries if e["designed_rtt_ms"] - e["netem_delay_ms"] > MAX_CORRECTION_MS]


def cmd_configure(args):
    require_foreground()
    d = args.dispersion
    entries = []
    for vm, responders in ladder.machines(d):
        if netbed.vm_status(vm) != "Running":
            raise SystemExit(f"{vm} is not running; run `netbed2.py up` first")
        print(f"\n{vm}", flush=True)
        interfaces = prepare_machine(vm, responders)
        # Baseline before any shaping, as study 1 does (netbed.cmd_configure).
        for responder, iface in zip(responders, interfaces):
            netbed.set_shaping(vm, responder.name, iface["ifname"], 0.02, 0.0)
        base = []
        for responder, iface in zip(responders, interfaces):
            stats = None
            for _ in range(6):
                stats = netbed.summarise(netbed.ping_rtts(iface["address"], 20, 0.1))
                if stats is not None:
                    break
                time.sleep(2.0)
            if stats is None:
                raise SystemExit(f"{vm}/{responder.name} at {iface['address']} did not answer after namespacing")
            base.append(stats["p50"])
        baseline = statistics.median(base)
        print(f"  baseline p50 {baseline:.3f} ms", flush=True)
        for responder, iface in zip(responders, interfaces):
            print(f"  {responder.name} {iface['address']} designed {responder.target_rtt_ms} ms", flush=True)
            netem, stats, history = netbed.calibrate(vm, responder, iface, baseline)
            observed = check_policy(vm, responder, iface)  # after calibration, as study 1
            rec = responder_record(vm, responder, iface)
            error = 100.0 * (stats["p50"] - responder.target_rtt_ms) / responder.target_rtt_ms
            rec.update({"netem_delay_ms": round(netem, 4),
                        "achieved": {k: round(v, 4) for k, v in stats.items()},
                        "achieved_error_percent": round(error, 3), "calibration": history,
                        "verified": observed})
            rec["cold_first_contact"] = cold_first_contact(rec, iface["address"])
            c = rec["cold_first_contact"]
            print(f"    achieved p50 {stats['p50']:.3f} ms ({error:+.2f}%), cold first contact "
                  f"{c.get('median_ms')} ms", flush=True)
            entries.append(rec)

    off = [e["name"] for e in entries if abs(e["achieved_error_percent"]) > TOLERANCE_PERCENT]
    suspect = large_corrections(entries)
    manifest = {"schema_version": 3, "what": f"study 2 testbed manifest, dispersion {d}×",
                **segment_header(d),
                "calibration_tolerance_percent": plan.CALIBRATION_TOLERANCE_PERCENT,
                "gate_tolerance_percent": TOLERANCE_PERCENT,
                "within_gate_tolerance": not off, "outside_tolerance": off,
                "max_correction_ms": MAX_CORRECTION_MS, "large_corrections": suspect,
                "provenance": provenance(), "responders": entries}
    path = OUT / f"d{d}.json"
    write_json(path, manifest)
    write_applied(manifest, path, entries)
    if off:
        print(f"OUTSIDE {TOLERANCE_PERCENT}%: {off}", flush=True)
    if suspect:
        print(f"CALIBRATION CORRECTED MORE THAN {MAX_CORRECTION_MS} ms: {suspect} (not the link; see "
              "host_conditions)", flush=True)
    return 1 if off or suspect else 0


def write_applied(manifest, manifest_path, entries):
    write_json(OUT / "applied.json", {
        "schema_version": 1, "what": "the testbed segment as it is now",
        "applied_at": now_iso(), "dispersion": manifest["dispersion"],
        "manifest": manifest_path.name, "manifest_sha256": sha256_of(manifest_path),
        "responders": [{k: e[k] for k in ("name", "machine", "interface", "address", "mac", "designed_rtt_ms",
                                          "netem_delay_ms", "loss_percent", "role", "answers_icmp", "tcp_ports")}
                       for e in entries]})


def responders_from_manifest(manifest):
    """The manifest's responders as study 1's `Responder`, grouped by machine, in manifest order."""
    groups = {}
    for e in manifest["responders"]:
        r = plan.Responder(e["name"], e["designed_rtt_ms"], loss_percent=e["loss_percent"],
                           answers_icmp=e["answers_icmp"], tcp_ports=tuple(e["tcp_ports"]))
        groups.setdefault(e["machine"], []).append((r, e))
    return groups


def cmd_apply(args):
    require_foreground()
    path = Path(args.manifest)
    if not path.is_absolute() and not path.exists():
        path = OUT / path
    manifest = json.loads(path.read_text())
    if [e["designed_rtt_ms"] for e in manifest["responders"]] != \
            [r.target_rtt_ms for r in ladder.responders(manifest["dispersion"])]:
        raise SystemExit(f"{path.name}: its delays are not ladder({manifest['dispersion']})")
    entries = []
    for vm, pairs in responders_from_manifest(manifest).items():
        if netbed.vm_status(vm) != "Running":
            raise SystemExit(f"{vm} is not running")
        responders = [r for r, _ in pairs]
        print(f"\n{vm}", flush=True)
        interfaces = prepare_machine(vm, responders)
        for (responder, e), iface in zip(pairs, interfaces):
            netbed.set_shaping(vm, responder.name, iface["ifname"], e["netem_delay_ms"], responder.loss_percent)
            check_policy(vm, responder, iface)
            rec = responder_record(vm, responder, iface)
            rec["netem_delay_ms"] = e["netem_delay_ms"]
            moved = "" if iface["address"] == e["address"] else f" (was {e['address']} at calibration)"
            print(f"  {responder.name} {iface['address']}{moved} netem {e['netem_delay_ms']} ms", flush=True)
            entries.append(rec)
    write_applied(manifest, path, entries)
    return 0


# --------------------------------------------------------------------------------
# verify — S1's gate
# --------------------------------------------------------------------------------

def gate_failures(dispersion, responders, runs, mac_rows):
    """Pure: what fails S1's gate. `responders` as in applied.json; `runs` a list of runs, each a list of
    measurements {name, unmeasurable?, unreachable?, error_percent?}; `mac_rows` {name, mac_in_neighbour_table,
    mac_reported_by_guest}."""
    failures = []
    if len(responders) != len(plan.RESPONDERS):
        failures.append(f"{len(responders)} responders, the design has {len(plan.RESPONDERS)}")
    designed = [r["designed_rtt_ms"] for r in responders]
    if designed != [r.target_rtt_ms for r in ladder.responders(dispersion)]:
        failures.append(f"designed delays are not ladder({dispersion})")
    roles = {}
    for r in responders:
        roles[r["role"]] = roles.get(r["role"], 0) + 1
    if roles != plan.composition():
        failures.append(f"composition {roles} is not study 1's {plan.composition()}")
    for i, run in enumerate(runs, 1):
        for m in run:
            if m.get("unmeasurable"):
                continue
            if m.get("unreachable"):
                failures.append(f"run {i}: {m['name']} unreachable")
            elif abs(m["error_percent"]) > TOLERANCE_PERCENT:
                failures.append(f"run {i}: {m['name']} {m['error_percent']:+.2f}% off designed")
    macs = [row["mac_in_neighbour_table"] for row in mac_rows]
    if any(m is None for m in macs):
        failures.append("an address has no hardware address in the neighbour table")
    elif len(set(macs)) != len(macs):
        failures.append("hardware addresses collapsed")
    if any(row["mac_in_neighbour_table"] != row["mac_reported_by_guest"] for row in mac_rows if
           row["mac_in_neighbour_table"]):
        failures.append("neighbour table and guest disagree about a hardware address")
    return failures


def measure(r):
    method = probe_method(r)
    base = {"name": r["name"], "address": r["address"], "designed_rtt_ms": r["designed_rtt_ms"], "method": method}
    if method == "none":
        return {**base, "unmeasurable": True}
    interval = verify_gate.interval_for(r["designed_rtt_ms"])
    if method == "tcp":
        stats = verify_gate.summarise(verify_gate.tcp_rtts(r["address"], r["tcp_ports"][0], VERIFY_PROBES, interval))
    else:
        stats = verify_gate.summarise(verify_gate.ping_rtts(r["address"], VERIFY_PROBES, interval))
    if stats is None:
        return {**base, "unreachable": True}
    error = 100.0 * (stats["p50"] - r["designed_rtt_ms"]) / r["designed_rtt_ms"]
    return {**base, "error_percent": round(error, 3), **stats}


def cmd_verify(args):
    applied_path = OUT / "applied.json"
    if not applied_path.exists():
        raise SystemExit("nothing is applied; run `netbed2.py apply` (or `configure`) first")
    applied = json.loads(applied_path.read_text())
    if args.manifest and Path(args.manifest).name != applied["manifest"]:
        raise SystemExit(f"{applied['manifest']} is applied, not {Path(args.manifest).name}")
    d, responders = applied["dispersion"], applied["responders"]
    require_foreground()

    cold = {r["name"]: cold_first_contact(r, r["address"]) for r in responders}
    runs = []
    for i in range(1, VERIFY_RUNS + 1):
        print(f"\nrun {i} of {VERIFY_RUNS}", flush=True)
        run = []
        for r in responders:
            m = measure(r)
            run.append(m)
            print(f"  {r['name']:<4} {r['address']:<15} designed {r['designed_rtt_ms']:>7} ms  " +
                  ("answers nothing" if m.get("unmeasurable") else "UNREACHABLE" if m.get("unreachable")
                   else f"p50 {m['p50']:>9.3f} ({m['error_percent']:+.2f}%)"), flush=True)
        runs.append(run)
    for r in responders:  # one probe each so the silent host is in the neighbour table too (it answers ARP)
        subprocess.run(["ping", "-c", "1", "-W", "1000", r["address"]], capture_output=True)
    table, table_source = neighbour_table()
    mac_rows = [{"name": r["name"], "address": r["address"], "mac_in_neighbour_table": table.get(r["address"]),
                 "mac_reported_by_guest": verify_gate.normalise_mac(r["mac"])} for r in responders]
    failures = gate_failures(d, responders, runs, mac_rows)
    worst = max((abs(m["error_percent"]) for run in runs for m in run if "error_percent" in m),
                default=None)
    result = {"schema_version": 1, "gate": "study 2 S1", **segment_header(d),
              "manifest": applied["manifest"], "manifest_sha256": applied["manifest_sha256"],
              "applied_at": applied["applied_at"], "runs": VERIFY_RUNS, "probes_per_run": VERIFY_PROBES,
              "tolerance_percent": TOLERANCE_PERCENT, "worst_error_percent": worst,
              "cold_first_contact": cold, "measurements": runs, "neighbour_table": mac_rows,
              "neighbour_table_source": table_source, "provenance": provenance(), "failures": failures, "passed": not failures}
    write_json(OUT / f"verify-d{d}-{stamp()}.json", result)
    print(f"\nworst error {worst}% (tolerance {TOLERANCE_PERCENT}%)", flush=True)
    if failures:
        print("S1 GATE NOT MET for d=%s:\n  - " % d + "\n  - ".join(failures), flush=True)
        return 1
    print(f"S1 gate met for d={d}", flush=True)
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("up")
    p.add_argument("--only", choices=machine_names())
    p.set_defaults(fn=cmd_up)
    sub.add_parser("status").set_defaults(fn=cmd_status)
    sub.add_parser("rebuild").set_defaults(fn=cmd_rebuild)
    p = sub.add_parser("configure")
    p.add_argument("--dispersion", type=int, required=True, choices=ladder.DISPERSIONS)
    p.set_defaults(fn=cmd_configure)
    p = sub.add_parser("apply")
    p.add_argument("--manifest", required=True, help="d<D>.json, in the output folder or a path")
    p.set_defaults(fn=cmd_apply)
    p = sub.add_parser("verify")
    p.add_argument("--manifest", help="refuse unless this manifest is the one applied")
    p.set_defaults(fn=cmd_verify)
    args = ap.parse_args()
    leave_background()
    return args.fn(args) or 0


if __name__ == "__main__":
    sys.exit(main())
