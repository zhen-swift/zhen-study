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

import os
import re
import signal
import subprocess
import time
from pathlib import Path
from typing import Any


class CaptureFailed(Exception):
    """A run without its oracle is not evidence."""


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
