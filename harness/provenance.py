"""What was true about the machine when a run happened.

Called once per run.  Most of it is bookkeeping — versions, hashes, hardware, power —
and one part of it is load-bearing evidence: the assertion that the macOS Local Network
permission was actually granted at the moment of the run.

Why that one matters more than the rest.  On current macOS, ICMP to the local network,
mDNS, SSDP and NetBIOS all sit behind the Local Network grant, **denial returns zero
results rather than an error**, and there is no API to query the grant.  So a denied run
looks exactly like a run against a network with nothing on it: exit 0, a well-formed
artifact, an empty address set.  A study that recorded that as "recall 0" would be
publishing a fabricated number.  Section 6 of the protocol requires the permission state
to be asserted per run, and this module is where the assertion is made.

The assertion is a positive control, not a query.  It sends an unprivileged ICMP echo
from this process — `SOCK_DGRAM`/`IPPROTO_ICMP`, the same socket family netsanity's
unprivileged engine uses, which macOS grants without root — to addresses known to
answer, and it reads the kernel's neighbour table, which is readable *without* the
permission.  Three outcomes, and only one of them is admissible:

    controls answered              -> granted
    no control answered, but the
      neighbour table lists live
      hosts on the segment         -> denied_likely   (the signature: the machine has
                                     demonstrably been talking to those hosts and our
                                     probes to them got nothing back)
    no control answered and the
      neighbour table is empty     -> indeterminate   (an empty network and a denied
                                     permission are not distinguishable from here, and
                                     saying otherwise would be a guess)

The scope of what that proves, stated plainly: the grant attaches to the responsible
application rather than to the binary, and a bare SPM executable has no bundle of its
own, so what is asserted is the grant held by the process tree this harness runs in —
which is exactly the population of processes it launches.  It is not a claim about any
other terminal, and it is not a claim the kernel is willing to answer directly.
"""

from __future__ import annotations

import hashlib
import os
import platform
import random
import re
import select
import shutil
import socket
import struct
import subprocess
import time
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]


class DirtyTree(Exception):
    """The one condition that aborts a block outright."""


def _run(argv: list[str], timeout: float = 20.0, strip: bool = True) -> tuple[int, str, str]:
    """Run a command and return (status, stdout, stderr).

    `strip=False` for output whose leading whitespace is data. `git status --porcelain`
    is the case that matters: its first two columns are the status code, and a modified
    unstaged file begins with a space — stripping it shifts every path by one character
    and silently corrupts the abort message that names what made the tree dirty.
    """
    try:
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
        out, err = proc.stdout, proc.stderr
        return proc.returncode, (out.strip() if strip else out), err.strip()
    except (OSError, subprocess.SubprocessError) as error:
        return -1, "", f"{type(error).__name__}: {error}"


def _sha256(path: str | os.PathLike | None) -> str | None:
    if not path:
        return None
    try:
        digest = hashlib.sha256()
        with open(path, "rb") as handle:
            for chunk in iter(lambda: handle.read(1 << 20), b""):
                digest.update(chunk)
        return digest.hexdigest()
    except OSError:
        return None


# ── git ───────────────────────────────────────────────────────────────────────────

def git_state(repo: Path = REPO) -> dict[str, Any]:
    """The commit, and whether the tree is dirty.

    Untracked files count as dirty.  That is stricter than it needs to be for a file
    that is only ever a scratch note, and it is the right side to err on: the harness
    cannot tell a scratch note from a source file someone forgot to add, and the
    difference between those two is the difference between reproducible and not.
    """
    code, commit, _ = _run(["git", "-C", str(repo), "rev-parse", "HEAD"])
    if code != 0:
        raise DirtyTree(f"cannot read the git commit in {repo}")
    code, status, _ = _run(["git", "-C", str(repo), "status", "--porcelain"], strip=False)
    if code != 0:
        raise DirtyTree(f"cannot read git status in {repo}")
    dirty_paths = [line[3:] for line in status.splitlines() if line.strip()]
    return {
        "git_commit": commit,
        "git_dirty": bool(dirty_paths),
        "git_dirty_paths": dirty_paths[:50],
    }


def require_clean_tree(repo: Path = REPO, *, allow_dirty: bool = False) -> dict[str, Any]:
    state = git_state(repo)
    if state["git_dirty"] and not allow_dirty:
        listing = "\n  ".join(state["git_dirty_paths"][:20])
        raise DirtyTree(
            "the working tree is dirty, so the block is aborted before it starts. "
            "Measuring uncommitted code produces a number nobody can reproduce.\n  "
            + listing
        )
    return state


# ── the Local Network permission ──────────────────────────────────────────────────

def _checksum(payload: bytes) -> int:
    if len(payload) % 2:
        payload += b"\0"
    total = sum(struct.unpack("!%dH" % (len(payload) // 2), payload))
    total = (total >> 16) + (total & 0xFFFF)
    total += total >> 16
    return (~total) & 0xFFFF


def icmp_echo(address: str, timeout: float = 1.0) -> bool:
    """One unprivileged ICMP echo. True if the address answered.

    `SOCK_DGRAM`/`IPPROTO_ICMP` needs no root on macOS and is what netsanity's
    unprivileged engine uses, so this probe is gated by exactly the permission it is
    testing for.  The kernel rewrites the identifier field on a datagram ICMP socket, so
    replies are matched on a random payload nonce and the source address instead.
    """
    nonce = random.randbytes(8)
    payload = b"netsanity-harness" + nonce
    header = struct.pack("!BBHHH", 8, 0, 0, 0, 1)
    packet = struct.pack("!BBHHH", 8, 0, _checksum(header + payload), 0, 1) + payload
    deadline = time.monotonic() + timeout
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_ICMP)
    except OSError:
        # No unprivileged ICMP socket at all is a different failure from a denied
        # permission, and conflating them would send someone to the wrong settings pane.
        return False
    with sock:
        sock.setblocking(False)
        try:
            sock.sendto(packet, (address, 0))
        except OSError:
            return False
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return False
            if not select.select([sock], [], [], remaining)[0]:
                return False
            try:
                data, peer = sock.recvfrom(2048)
            except OSError:
                return False
            if peer[0] != address or nonce not in data:
                continue
            # macOS hands back the IP header on a datagram ICMP socket; Linux does not.
            offset = (data[0] & 0x0F) * 4 if data and (data[0] >> 4) == 4 else 0
            if len(data) > offset and data[offset] == 0:      # ICMP echo reply
                return True


_ARP_LINE = re.compile(r"\((\d{1,3}(?:\.\d{1,3}){3})\) at ([0-9a-fA-F:]+)")


def neighbour_table(prefix: str | None = None) -> list[str]:
    """Addresses with a *complete* entry in the kernel's neighbour table.

    Readable without the Local Network permission, which is the whole point: it is the
    control that makes a silent sweep mean something.
    """
    code, out, _ = _run(["arp", "-an"])
    if code != 0:
        return []
    found = []
    for line in out.splitlines():
        match = _ARP_LINE.search(line)
        if not match or "incomplete" in line:
            continue
        address = match.group(1)
        if prefix and not address.startswith(prefix):
            continue
        found.append(address)
    return sorted(set(found))


def assert_local_network_permission(
    control_hosts: list[str], segment_prefix: str | None = None
) -> dict[str, Any]:
    """The per-run assertion PROTOCOL.md section 6 requires. See the module docstring."""
    neighbours = neighbour_table(segment_prefix)
    if not control_hosts:
        # A harness misconfiguration is not a permission denial, and reporting it as one
        # would send someone to a settings pane to fix something that is not broken.
        return {
            "verdict": "indeterminate",
            "reason": "no control host was declared, so there was nothing to probe",
            "method": "not attempted",
            "control_hosts": [],
            "controls_answered": 0,
            "controls_that_answered": [],
            "neighbour_entries": len(neighbours),
            "checked_at_unix": time.time(),
        }
    answered = [host for host in control_hosts if icmp_echo(host)]
    if answered:
        verdict, reason = "granted", None
    elif neighbours:
        verdict, reason = "denied_likely", (
            f"no declared control host answered an unprivileged ICMP echo, while the "
            f"neighbour table lists {len(neighbours)} live host(s) on this segment"
        )
    else:
        verdict, reason = "indeterminate", (
            "no control host answered and the neighbour table is empty: a denied "
            "permission and an empty segment are not distinguishable from here"
        )
    return {
        "verdict": verdict,
        "reason": reason,
        "method": "unprivileged SOCK_DGRAM/IPPROTO_ICMP echo to declared control hosts, "
                  "with the kernel neighbour table as the negative control",
        "control_hosts": list(control_hosts),
        "controls_answered": len(answered),
        "controls_that_answered": answered,
        "neighbour_entries": len(neighbours),
        "checked_at_unix": time.time(),
    }


# ── everything else ───────────────────────────────────────────────────────────────

def _thermal_pressure() -> str:
    code, out, _ = _run(["pmset", "-g", "therm"], timeout=10.0)
    return out if code == 0 else "unavailable"


def _on_ac_power() -> bool | None:
    code, out, _ = _run(["pmset", "-g", "ps"], timeout=10.0)
    if code != 0:
        return None
    return "AC Power" in out


def _uptime_seconds() -> float | None:
    code, out, _ = _run(["sysctl", "-n", "kern.boottime"], timeout=10.0)
    match = re.search(r"sec\s*=\s*(\d+)", out) if code == 0 else None
    return time.time() - int(match.group(1)) if match else None


def _display_and_power_state() -> dict[str, Any]:
    """Recorded so a reviewer can see the host was held awake and the display was not.

    `caffeinate -i` around the block loop keeps the *scanning* host up; the observed
    devices must stay free to sleep, because their sleep cycle is part of what the
    time-of-day strata sample.
    """
    code, out, _ = _run(["pmset", "-g", "assertions"], timeout=10.0)
    if code != 0:
        return {"assertions": "unavailable"}
    wanted = ("PreventUserIdleSystemSleep", "PreventUserIdleDisplaySleep",
              "PreventDisplaySleep")
    lines = [line.strip() for line in out.splitlines()
             if any(name in line for name in wanted)]
    return {"assertions": lines[:8]}


def collect(
    *,
    netsanity: str,
    nmap: str,
    control_hosts: list[str],
    segment_prefix: str | None = None,
    repo: Path = REPO,
    allow_dirty: bool = False,
) -> dict[str, Any]:
    """One provenance record. Raises `DirtyTree` rather than returning a dirty one.

    `allow_dirty` exists for `--dry-run` alone and the caller has to ask for it
    explicitly; nothing in a live block passes it.
    """
    state = require_clean_tree(repo, allow_dirty=allow_dirty)
    ns_code, ns_version, _ = _run([netsanity, "--version"], timeout=15.0)
    nmap_code, nmap_version, _ = _run([nmap, "--version"], timeout=15.0)
    swift_code, swift_version, _ = _run(["swift", "--version"], timeout=60.0)
    _, product, _ = _run(["sw_vers", "-productVersion"], timeout=10.0)
    _, build, _ = _run(["sw_vers", "-buildVersion"], timeout=10.0)
    _, model, _ = _run(["sysctl", "-n", "hw.model"], timeout=10.0)

    return {
        **state,
        "netsanity_path": netsanity,
        "netsanity_version": ns_version if ns_code == 0 else None,
        "netsanity_sha256": _sha256(shutil.which(netsanity) or netsanity),
        "nmap_path": nmap,
        # Verbatim, as the reproducibility appendix requires: nmap's version block names
        # every library it was linked against, and "nmap 7.991" alone does not.
        "nmap_version": nmap_version if nmap_code == 0 else None,
        "nmap_sha256": _sha256(shutil.which(nmap) or nmap),
        "swift_version": swift_version if swift_code == 0 else None,
        "os_product_version": product or platform.mac_ver()[0] or None,
        "os_build": build or None,
        "hw_model": model or None,
        "uptime_seconds": _uptime_seconds(),
        "on_ac_power": _on_ac_power(),
        "thermal_pressure": _thermal_pressure(),
        "power_assertions": _display_and_power_state(),
        "local_network_permission": assert_local_network_permission(
            control_hosts, segment_prefix
        ),
        "harness_pid": os.getpid(),
        "collected_at_unix": time.time(),
    }


if __name__ == "__main__":
    import json
    import sys

    ns = sys.argv[1] if len(sys.argv) > 1 else "netsanity"
    hosts = sys.argv[2:] or ["10.10.20.1"]
    try:
        print(json.dumps(collect(netsanity=ns, nmap="nmap", control_hosts=hosts,
                                 segment_prefix="10.10.20."), indent=1, sort_keys=True))
    except DirtyTree as error:
        print(f"BLOCK ABORTED: {error}")
        raise SystemExit(2)
