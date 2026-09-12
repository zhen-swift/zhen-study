"""Ground truth: what was actually on the segment while a run was measured.

Recall is a fraction, and its denominator is not something a scanner can be asked for.
`PROTOCOL.md` section 3 names three independent oracles and this module is all three.

    manifest    what the instrument was built to be
    inventory   what the machines hosting it say they are running, right now
    capture     what each responder actually sent and received during the run

The first two can both be wrong in the same direction — a responder configured and then
quietly dead still appears in the plan and still reports an address. Only the capture
separates "the scanner missed it" from "it was not answering", which is why the protocol
calls it the one that decides recall.

── Where the capture is taken, and why it is not on the Mac ─────────────────────────

`PROTOCOL.md` describes a passive capture on the segment. On this apparatus that would
mean `/dev/bpf*` on the scanning Mac, which is `crw------- root:wheel`, and `PHASE0.md`
assigns unattended root to JC rather than to the agent. That is a real constraint and it
is not worked around here.

Instead the capture happens AT each responder, inside its own network namespace, using
the guest's passwordless sudo. This is a deliberate change to the method and it is not
merely a substitute:

  * It attributes. A segment-wide capture shows a probe and a silence; a per-responder
    capture shows that the probe arrived at that host and that the host did not answer,
    which is precisely the distinction the oracle exists to make.
  * It reaches the hosts that answer nothing. Presence is "emitted a frame from its own
    hardware address", so a host with ICMP filtered and no ports open is still visible
    by its ARP replies — and this segment has one of those on purpose.

What it gives up is stated rather than hidden. It cannot see a device that is not one of
ours, so it cannot detect a stranger joining the segment mid-block; the manifest and the
inventory are both closed-world too, so on this testbed no oracle would. It also cannot
see a probe that never reached the segment at all, which a capture on the Mac would. Both
are recorded as limitations of the programmable segment, and the physical secondary
testbed — where a Mac-side capture is possible — is where they would be answered.
"""

from __future__ import annotations

import json
import socket
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "testbed"))
import plan  # noqa: E402

LIMACTL = "/opt/homebrew/bin/limactl"
MANIFEST = Path(__file__).resolve().parent.parent / "testbed" / "manifest.json"


def _guest(vm, script, check=True, timeout=120):
    return subprocess.run([LIMACTL, "shell", vm, "--", "sudo", "bash", "-c", script],
                          capture_output=True, text=True, check=check, timeout=timeout)


def _vm_running(vm):
    out = subprocess.run([LIMACTL, "list", "--format", "{{.Status}}", vm],
                         capture_output=True, text=True).stdout.strip()
    return out == "Running"


# ── Oracle one: the manifest ────────────────────────────────────────────────────

def manifest_oracle():
    """What the instrument was built to be.

    Read from `manifest.json`, which records what `netbed.py configure` actually did
    rather than what `plan.py` asked for — the two differ, and the difference is the
    calibration.
    """
    if not MANIFEST.exists():
        return {"status": "absent", "addresses": [], "detail": "no manifest.json"}
    data = json.loads(MANIFEST.read_text())
    return {
        "status": "ok",
        "addresses": sorted(r["address"] for r in data["responders"]),
        "by_address": {r["address"]: {"name": r["name"], "role": r["role"],
                                      "answers_icmp": r["answers_icmp"],
                                      "tcp_ports": r["tcp_ports"]}
                       for r in data["responders"]},
        "generated_at_unix": data.get("generated_at_unix"),
    }


# ── Oracle two: the guests' own inventory ───────────────────────────────────────

def inventory_oracle():
    """What the machines hosting the segment say they are running.

    Independent of the manifest in the way that matters: it is produced by the hosts that
    answer the probes, it is read at the moment it is asked, and it knows nothing about
    what any scanner found. A responder whose namespace was destroyed appears here as
    absent while the manifest still lists it.
    """
    addresses = []
    machines = []
    for vm, responders in plan.machines():
        if not _vm_running(vm):
            machines.append({"machine": vm, "status": "not running", "responders": []})
            continue
        found = []
        for responder in responders:
            r = _guest(vm, f"ip netns exec {responder.name} ip -j addr show", check=False)
            try:
                entries = json.loads(r.stdout.strip().splitlines()[-1])
            except (json.JSONDecodeError, IndexError):
                entries = []
            for entry in entries:
                if not entry.get("ifname", "").startswith("lima"):
                    continue
                inet = [a["local"] for a in entry.get("addr_info", [])
                        if a.get("family") == "inet"]
                if inet:
                    addresses.append(inet[0])
                    found.append({"name": responder.name, "address": inet[0],
                                  "mac": entry.get("address")})
        machines.append({"machine": vm, "status": "running", "responders": found})
    return {"status": "ok", "addresses": sorted(addresses), "machines": machines}


# ── Oracle three: what each responder actually did ──────────────────────────────

class Capture:
    """A per-responder packet capture, running for the length of one measured run.

    Two numbers per responder, and the difference between them is the whole point.

        frames_in    frames that arrived at this host's interface
        frames_out   frames this host sent, from its own hardware address

    **Present** is either being non-zero. **Answering** is `frames_out`. That separation
    is what `PROTOCOL.md` asks the capture oracle for: a scanner reporting nothing at an
    address where frames arrived and none came back was not wrong about the network, and
    an address where nothing arrived at all is a different failure entirely — a probe
    that never left, or a segment that is not the one being scanned.

    Presence was first defined as `frames_out` alone, and it under-reported by exactly
    the two hosts the composition exists for. A host with ICMP filtered ignores the echo
    request, and the Mac's neighbour table was already warm, so it was never asked for an
    ARP either: it sat there entirely healthy, receiving every probe, and transmitted
    nothing for the whole window. Defining presence by what a host says makes silent
    hosts invisible, which is the one thing an oracle for a segment containing silent
    hosts must not do.
    """

    def __init__(self, run_id):
        self.run_id = run_id
        self.started = []
        self.error = None

    def unit(self, ns):
        return f"netbed-cap-{self.run_id}-{ns}"

    def path(self, ns):
        return f"/tmp/{self.run_id}-{ns}.pcap"

    def start(self):
        manifest = manifest_oracle()
        if manifest["status"] != "ok":
            self.error = "no manifest; nothing to capture on"
            return self
        # The responder's real interface, not `-i any`. The `any` pseudo-interface
        # captures as LINUX_SLL2, which has no Ethernet header — so `ether src` is
        # rejected outright and, worse, ARP is not visible as ARP. The first version did
        # this and reported that no responder had transmitted at all, while the files it
        # had written contained the echo replies proving they had.
        interfaces = {r["name"]: r["interface"] for r in
                      json.loads(MANIFEST.read_text())["responders"]}
        by_name = {v["name"]: k for k, v in manifest["by_address"].items()}
        for vm, responders in plan.machines():
            if not _vm_running(vm):
                self.error = f"{vm} is not running"
                return self
            script = ["set -e"]
            for responder in responders:
                if responder.name not in by_name:
                    continue
                ns, unit = responder.name, self.unit(responder.name)
                script += [
                    f"systemctl stop {unit}.service 2>/dev/null || true",
                    f"rm -f {self.path(ns)}",
                    # `-U` so packets reach the file as they arrive rather than when a
                    # buffer fills: a capture that is still buffered when the run ends is
                    # a capture that reports silence it did not observe.
                    f"systemd-run --unit={unit} --collect "
                    f"ip netns exec {ns} tcpdump -i {interfaces[ns]} -n -U -s 0 "
                    f"-w {self.path(ns)} >/dev/null 2>&1",
                ]
            try:
                _guest(vm, "\n".join(script))
                self.started.append(vm)
            except subprocess.CalledProcessError as exc:
                self.error = f"{vm}: {exc.stderr.strip()[:200]}"
                return self
        # tcpdump takes a moment to attach; frames sent before it does are not captured,
        # and a capture that starts after the first probe under-reports exactly the hosts
        # that answered fastest.
        time.sleep(1.5)
        return self

    def stop(self):
        """Stop every capture and report which responders transmitted."""
        if self.error:
            return {"status": "failed", "error": self.error, "addresses": []}
        manifest = manifest_oracle()
        seen = {}
        for vm, responders in plan.machines():
            if vm not in self.started:
                continue
            for responder in responders:
                ns = responder.name
                _guest(vm, f"systemctl stop {self.unit(ns)}.service 2>/dev/null || true",
                       check=False)
        # Stopped everywhere first, then read: reading a file that is still being written
        # races the writer for the last packet, and the last packet is often the reply
        # that decides whether a host was present.
        for vm, responders in plan.machines():
            if vm not in self.started:
                continue
            for responder in responders:
                ns = responder.name
                address = next((a for a, v in manifest["by_address"].items()
                                if v["name"] == ns), None)
                if address is None:
                    continue
                mac = _mac(manifest, ns)
                out = _guest(
                    vm,
                    f"o=$(tcpdump -r {self.path(ns)} -n 'ether src {mac}' 2>/dev/null "
                    f"| wc -l); "
                    f"i=$(tcpdump -r {self.path(ns)} -n 'ether dst {mac} or broadcast' "
                    f"2>/dev/null | wc -l); "
                    f"echo \"$o $i\"",
                    check=False,
                ).stdout.strip()
                try:
                    sent, received = (int(x) for x in out.splitlines()[-1].split())
                except (ValueError, IndexError):
                    sent, received = 0, 0
                seen[address] = {"frames_out": sent, "frames_in": received}
        return {
            "status": "ok",
            "frames_by_address": seen,
            "addresses": sorted(a for a, n in seen.items()
                                if n["frames_out"] > 0 or n["frames_in"] > 0),
            "answering": sorted(a for a, n in seen.items() if n["frames_out"] > 0),
        }


def _mac(manifest, name):
    data = json.loads(MANIFEST.read_text())
    for r in data["responders"]:
        if r["name"] == name:
            return r["mac"]
    return "00:00:00:00:00:00"


# ── Agreement ───────────────────────────────────────────────────────────────────

def agree(manifest, inventory, capture):
    """Do the three oracles describe the same segment?

    Disagreement is not a scanner result and is not evidence about one. `PROTOCOL.md`:
    a run whose oracles disagree is excluded, and the exclusion is reported.
    """
    sets = {
        "manifest": set(manifest.get("addresses", [])),
        "inventory": set(inventory.get("addresses", [])),
        "capture": set(capture.get("addresses", [])),
    }
    agreed = sets["manifest"] == sets["inventory"] == sets["capture"]
    detail = {}
    if not agreed:
        union = set().union(*sets.values())
        for address in sorted(union):
            where = [k for k, v in sets.items() if address in v]
            if len(where) != 3:
                detail[address] = where
    return {
        "status": "agreed" if agreed else "disagreed",
        "addresses": sorted(sets["manifest"] & sets["inventory"] & sets["capture"]),
        "counts": {k: len(v) for k, v in sets.items()},
        "disagreements": detail,
    }


# ── The 0.4 gate ────────────────────────────────────────────────────────────────

def _stimulus(addresses):
    """Give every responder a reason to transmit, without asking a scanner to.

    The capture oracle sees transmissions, and a host that is never addressed does not
    transmit. Using a scanner for this would make the oracle depend on the thing it is
    supposed to be independent of, so the stimulus is a plain ping to each address —
    which reaches even the responders that ignore it, because ignoring an echo request
    still requires answering the ARP that precedes it.
    """
    manifest = manifest_oracle()
    for address in addresses:
        subprocess.run(["ping", "-c", "2", "-W", "1500", "-i", "0.3", address],
                       capture_output=True, text=True)
        # A host that serves a port is additionally asked for it, so the segment's
        # TCP-only responder has something it will actually answer. Without this the
        # only evidence it is alive is that probes arrive at it, which is presence but
        # not liveness, and the two are worth being able to tell apart.
        for port in manifest["by_address"].get(address, {}).get("tcp_ports", []):
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(3.0)
            try:
                sock.connect((address, port))
            except OSError:
                pass
            finally:
                sock.close()


def check(rounds=3):
    """PHASE0 0.4: three consecutive checks where all three oracles agree."""
    manifest = manifest_oracle()
    if manifest["status"] != "ok":
        print("no manifest.json; run `netbed.py configure` first", file=sys.stderr)
        return 2

    results = []
    for index in range(1, rounds + 1):
        print(f"\ncheck {index} of {rounds}", flush=True)
        capture = Capture(f"gate04-{index}").start()
        _stimulus(manifest["addresses"])
        observed = capture.stop()
        inventory = inventory_oracle()
        verdict = agree(manifest, inventory, observed)
        results.append({"round": index, "verdict": verdict,
                        "frames": observed.get("frames_by_address", {}),
                        "answering": observed.get("answering", [])})
        print(f"  manifest {verdict['counts']['manifest']}  "
              f"inventory {verdict['counts']['inventory']}  "
              f"capture {verdict['counts']['capture']}  -> {verdict['status']}")
        for address, where in verdict["disagreements"].items():
            print(f"    {address}: seen by {', '.join(where) or 'nothing'}")

    passed = all(r["verdict"]["status"] == "agreed" for r in results)
    out = {
        "schema_version": 1,
        "gate": "0.4",
        "rounds": rounds,
        "capture_location": "per responder, inside its network namespace",
        "results": results,
        "passed": passed,
    }
    path = Path(__file__).resolve().parent.parent / "testbed" / "gate-0.4.json"
    path.write_text(json.dumps(out, indent=1) + "\n")
    print(f"\nwrote {path}")
    if not passed:
        print("\nGATE 0.4 NOT MET")
        return 1
    print("\nGATE 0.4 MET")
    return 0


if __name__ == "__main__":
    sys.exit(check())
