"""Per-run packet capture, and the Wi-Fi covariates that go with it.

The capture is oracle 3 — the only one that distinguishes "the scanner missed it" from
"it was asleep" — so a run without its capture is not evidence, and capture failure
aborts the run rather than being noted and passed over.

Root, and what that means here.  `tcpdump` needs a BPF device: `/dev/bpf*` is
`crw------- root:wheel` on this machine, this account is not in an `access_bpf` group
(the group does not exist), and no ChmodBPF daemon is installed, so there is no
unprivileged path to a capture on macOS.  Whatever arrangement PHASE0 settles on for
unattended root — a root-owned launchd job, or a sudoers entry scoped to these binaries
— has to cover `tcpdump` as well as `nmap`.  `sudo -n` throughout, so a missing
arrangement fails on the first block instead of sitting on a prompt for seven days.

Channel utilisation, honestly.  The protocol asks for it as a Wi-Fi contention
covariate.  Airtime utilisation is not readable on macOS 26 without root — `airport`
was removed and `wdutil info` is root-only and redacts — so what is recorded here is
what *is* readable without it: channel, width, band, PHY mode and the signal/noise pair
from `system_profiler`.  Those are covariates, not utilisation, and the field is named
so that nobody later mistakes one for the other.  On the programmable segment the
question does not arise: it is a vmnet bridge with no radio, and the record says
`not_applicable` rather than carrying a number from the unrelated Wi-Fi interface the
Mac also happens to have.
"""

from __future__ import annotations

import collections
import os
import re
import signal
import subprocess
import time
from pathlib import Path
from typing import Any


class CaptureFailed(Exception):
    """A run without its oracle is not evidence."""


#: What the wire summary counts, as BPF.  Names are the record's field names.  The
#: Mac is the scanning host, so on this capture "out" is what it sent and "in" is what
#: reached it; the filters count frames regardless of direction and the per-address
#: tallies below attribute the ones whose direction matters.
_WIRE_FILTERS = {
    "arp_requests": "arp and arp[6:2]=1",
    "arp_replies": "arp and arp[6:2]=2",
    "icmp_echo_requests": "icmp[icmptype]=icmp-echo",
    "icmp_echo_replies": "icmp[icmptype]=icmp-echoreply",
    "tcp_syn": "tcp[tcpflags]&(tcp-syn|tcp-ack)=tcp-syn",
    "tcp_synack": "tcp[tcpflags]&(tcp-syn|tcp-ack)=(tcp-syn|tcp-ack)",
    "tcp_rst": "tcp[tcpflags]&tcp-rst!=0",
}
_ARP_REPLY_LINE = re.compile(r"ARP, Reply (\d+\.\d+\.\d+\.\d+) is-at")
_IP_SOURCE_LINE = re.compile(r" IP (\d+\.\d+\.\d+\.\d+)\.\d+ > ")


def summarise_pcap(pcap_path: Path, *, timeout: float = 60.0) -> dict[str, Any]:
    """Count on the wire what the 0.6 pilot counted by hand, and put it in the record.

    The pilot explained unprivileged `-T2`'s two modes by ARP request counts (1679
    against 507) and explained nmap's recall difference by which responders sent RSTs —
    both read with `tcpdump -r` over the pcap, which is git-ignored, so neither number
    was recomputable from the NDJSON.  This is the same `tcpdump -r`, run by the harness
    at the end of every capture, with the counts written beside the pcap path.  Schema 2.

    Reading a pcap needs no privilege, only the file, and the seven passes cost about
    25 ms on the largest capture the pilot produced.  They run after the tool's wall
    clock has been taken and before the next cooldown, so they are block span and not
    measured time.  A failure here is recorded and does not exclude the run: the
    counts are a convenience for the analysis, and the pcap they came from is still the
    oracle.
    """
    if not pcap_path.exists():
        return {"status": "failed", "error": "no pcap to summarise"}
    counts: dict[str, Any] = {}
    try:
        for field, expression in _WIRE_FILTERS.items():
            proc = subprocess.run(
                ["tcpdump", "-r", str(pcap_path), "-nn", expression],
                capture_output=True, text=True, timeout=timeout,
            )
            if proc.returncode != 0:
                return {"status": "failed",
                        "error": f"tcpdump -r for {field}: {proc.stderr.strip()[:200]}"}
            counts[field] = sum(1 for line in proc.stdout.splitlines() if line.strip())
        by_source: dict[str, collections.Counter] = {
            "arp_replies_by_sender": collections.Counter(),
            "tcp_rst_by_source": collections.Counter(),
            "tcp_synack_by_source": collections.Counter(),
            "icmp_echo_replies_by_source": collections.Counter(),
        }
        for field, pattern, key in (
            ("arp_replies", _ARP_REPLY_LINE, "arp_replies_by_sender"),
            ("tcp_rst", _IP_SOURCE_LINE, "tcp_rst_by_source"),
            ("tcp_synack", _IP_SOURCE_LINE, "tcp_synack_by_source"),
            ("icmp_echo_replies", _IP_SOURCE_LINE, "icmp_echo_replies_by_source"),
        ):
            proc = subprocess.run(
                ["tcpdump", "-r", str(pcap_path), "-nn", _WIRE_FILTERS[field]],
                capture_output=True, text=True, timeout=timeout,
            )
            for line in proc.stdout.splitlines():
                match = pattern.search(line)
                if match:
                    by_source[key][match.group(1)] += 1
    except (OSError, subprocess.TimeoutExpired) as error:
        return {"status": "failed", "error": f"summarising pcap: {error}"}
    counts.update({k: dict(sorted(v.items())) for k, v in by_source.items()})
    counts["status"] = "ok"
    counts["error"] = None
    return counts


class Capture:
    """One `tcpdump` for the life of one run.

    Started before the tool and stopped after it, with a settle window on each side:
    `tcpdump` takes a moment to attach to the BPF device and a run whose first probes
    went out before the capture was listening has a hole in exactly the oracle that
    decides recall.
    """

    #: Seconds to wait for tcpdump to be attached before releasing the run, and to let
    #: late replies land before tearing it down. Both are conservative; the cost is
    #: seconds per run against a seven-day window, and the alternative is a silently
    #: incomplete oracle.
    ATTACH_SETTLE = 1.0
    DRAIN_SETTLE = 1.0

    def __init__(self, *, interface: str, pcap_path: Path, filter_expr: str,
                 sudo: bool = True, stub: bool = False):
        self.interface = interface
        self.pcap_path = Path(pcap_path)
        self.filter_expr = filter_expr
        self.sudo = sudo
        self.stub = stub
        self._proc: subprocess.Popen | None = None
        self._stderr_path = self.pcap_path.with_suffix(".tcpdump.err")
        self.status = "disabled"
        self.error: str | None = None
        self.wire: dict[str, Any] | None = None

    @property
    def argv(self) -> list[str]:
        base = ["tcpdump", "-i", self.interface, "-n", "-U", "-s", "0",
                "-w", str(self.pcap_path), self.filter_expr]
        return (["sudo", "-n"] + base) if self.sudo else base

    def start(self) -> None:
        self.pcap_path.parent.mkdir(parents=True, exist_ok=True)
        if self.stub:
            # A dry run must not fabricate a pcap, because a downstream reader would
            # not be able to tell it from a real one. It records that no capture was
            # taken, under its own status.
            self.status = "stubbed"
            return
        self._stderr_handle = open(self._stderr_path, "w", encoding="utf-8")
        try:
            self._proc = subprocess.Popen(
                self.argv, stdout=subprocess.DEVNULL, stderr=self._stderr_handle
            )
        except OSError as error:
            self.status, self.error = "failed", f"cannot start tcpdump: {error}"
            raise CaptureFailed(self.error) from error
        time.sleep(self.ATTACH_SETTLE)
        if self._proc.poll() is not None:
            stderr = self._stderr_path.read_text(errors="replace").strip()
            self.status, self.error = "failed", (
                f"tcpdump exited {self._proc.returncode} before the run started: {stderr}"
            )
            raise CaptureFailed(self.error)
        self.status = "ok"

    def stop(self) -> dict[str, Any]:
        if self.stub or self._proc is None:
            return self.record()
        time.sleep(self.DRAIN_SETTLE)
        # SIGTERM rather than SIGKILL: tcpdump flushes its buffer on termination, and a
        # killed capture loses whatever had not reached the file.
        try:
            self._proc.send_signal(signal.SIGTERM)
            self._proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            self._proc.kill()
            self._proc.wait(timeout=5)
            self.status, self.error = "failed", "tcpdump did not exit on SIGTERM"
        except OSError as error:
            self.status, self.error = "failed", f"cannot stop tcpdump: {error}"
        finally:
            try:
                self._stderr_handle.close()
            except Exception:
                pass
        if self.status == "ok" and not self.pcap_path.exists():
            self.status, self.error = "failed", "tcpdump wrote no pcap"
        if self.status == "ok" and self.pcap_path.stat().st_size == 0:
            self.status, self.error = "failed", "tcpdump wrote an empty pcap"
        if self.status == "ok":
            self.wire = summarise_pcap(self.pcap_path)
        return self.record()

    def record(self) -> dict[str, Any]:
        size = self.pcap_path.stat().st_size if self.pcap_path.exists() else None
        return {
            "status": self.status,
            "path": str(self.pcap_path) if self.status == "ok" else None,
            "bytes": size,
            "interface": self.interface,
            "filter": self.filter_expr,
            "argv": self.argv,
            "error": self.error,
            "wire": self.wire,
        }

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *exc):
        self.stop()
        return False


# ── Wi-Fi covariates ──────────────────────────────────────────────────────────────

_FIELDS = {
    "Channel": "channel",
    "PHY Mode": "phy_mode",
    "Signal / Noise": "signal_noise",
    "Transmit Rate": "transmit_rate",
    "Security": "security",
}


def wifi_covariates(interface: str, timeout: float = 30.0) -> dict[str, Any]:
    """Channel, band, PHY mode and signal/noise for a Wi-Fi interface.

    Returns `not_applicable` for anything that is not a radio — the programmable segment
    runs over a vmnet bridge, and reporting the Mac's Wi-Fi state alongside a run that
    never touched the radio would be a covariate about the wrong link.
    """
    if not interface.startswith("en"):
        return {"status": "not_applicable",
                "reason": f"{interface} is not a Wi-Fi interface",
                "airtime_utilisation": None}
    try:
        proc = subprocess.run(
            ["system_profiler", "-detailLevel", "basic", "SPAirPortDataType"],
            capture_output=True, text=True, timeout=timeout,
        )
    except (OSError, subprocess.SubprocessError) as error:
        return {"status": "unavailable", "reason": str(error),
                "airtime_utilisation": None}
    if proc.returncode != 0:
        return {"status": "unavailable", "reason": proc.stderr.strip()[:200],
                "airtime_utilisation": None}

    # Only the block for the interface we scanned from, and only its current network.
    section, capturing = [], False
    for line in proc.stdout.splitlines():
        stripped = line.strip()
        if re.match(rf"^{re.escape(interface)}:$", stripped):
            capturing = True
            continue
        if capturing and re.match(r"^[a-z]+\d+:$", stripped):
            break
        if capturing:
            section.append(stripped)

    out: dict[str, Any] = {"status": "ok" if section else "unavailable",
                           "interface": interface}
    for line in section:
        key, _, value = line.partition(":")
        if key.strip() in _FIELDS and value.strip():
            out[_FIELDS[key.strip()]] = value.strip()
    if "channel" in out:
        band = re.search(r"\((\d+)GHz", out["channel"])
        width = re.search(r"(\d+)MHz", out["channel"])
        out["band_ghz"] = int(band.group(1)) if band else None
        out["channel_width_mhz"] = int(width.group(1)) if width else None
    # Named for what it is not, so that a reader cannot mistake the covariates above
    # for the utilisation the protocol asked for.
    out["airtime_utilisation"] = None
    out["airtime_utilisation_note"] = (
        "not readable on macOS 26 without root: `airport` was removed and `wdutil info` "
        "is root-only and redacts. The fields above are link covariates, not utilisation."
    )
    return out


def flush_neighbour_table(sudo: bool = True, stub: bool = False) -> dict[str, Any]:
    """Start every block cold. Cache state is a condition, not an accident.

    `arp -a -d` needs root on macOS, so this shares the block's root arrangement with
    `tcpdump` and the privileged conditions.
    """
    if stub:
        return {"flushed": False, "status": "stubbed", "entries_before": None}
    before = subprocess.run(["arp", "-an"], capture_output=True, text=True)
    argv = (["sudo", "-n"] if sudo else []) + ["arp", "-a", "-d"]
    proc = subprocess.run(argv, capture_output=True, text=True)
    return {
        "flushed": proc.returncode == 0,
        "status": "ok" if proc.returncode == 0 else "failed",
        "argv": argv,
        "entries_before": len(before.stdout.splitlines()),
        "error": proc.stderr.strip()[:300] or None,
    }
