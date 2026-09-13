"""How each tool is invoked, and how its output becomes an address set.

One function per tool, both returning the same record, so the analysis never has to
know which tool produced a row in order to read it.

Two rules, and they are the reason this module exists rather than a shell script.

**Wall clock is measured here, around the process, with `time.monotonic()`.**  Never
taken from either tool's own report.  Both tools do report their own timing and both
reports are recorded — under a field name that says what they are — but the measurement
is the one the harness took, because self-reported timing is exactly what a reviewer
will not accept from the authors of one of the two systems.

**Parsing failure is an exclusion, never a silent empty set.**  An empty result and an
unparseable result are different findings.  This is the specific way a benchmark
harness produces confident nonsense: a tool changes its output format, the parser
quietly returns `[]`, and the study reports that the comparator found nothing.

A third rule the 0.3 findings added: **a privileged condition must prove it ran
privileged.**  netsanity states its engine in the artifact (`run.engine.kind`), so a
privileged run that silently fell back to the unprivileged engine is caught here rather
than being averaged into H3.
"""

from __future__ import annotations

import json
import os
import subprocess
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any


class PrivilegeUnavailable(Exception):
    """`sudo -n` refused. A configuration failure, and it stops the block.

    Not a per-run exclusion: if root is not arranged, every privileged run in every
    remaining block will fail the same way, and a study that quietly drops half its
    conditions for seven days is worse than one that halts on the first night.
    """


class Outcome(dict):
    """One tool invocation. A dict so it serialises without ceremony."""


def _write(path: Path, text: str) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return str(path)


def _invoke(argv: list[str], timeout: float) -> tuple[int, str, str, float, float, float]:
    """Run the process and bracket it. The only place wall clock is taken."""
    started_wall = time.time()
    started = time.monotonic()
    try:
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
        code, out, err = proc.returncode, proc.stdout, proc.stderr
    except subprocess.TimeoutExpired as expired:
        # A timeout is data. The run is excluded, but the elapsed time it burned is
        # real and the record says what happened rather than pretending the process
        # never started.
        code = -9
        out = expired.stdout.decode() if isinstance(expired.stdout, bytes) else (expired.stdout or "")
        err = (expired.stderr.decode() if isinstance(expired.stderr, bytes) else (expired.stderr or "")) \
            + f"\nharness: timed out after {timeout}s"
    elapsed = time.monotonic() - started
    return code, out, err, elapsed, started_wall, time.time()


def _sudo_refused(code: int, stderr: str) -> bool:
    return code != 0 and "password is required" in stderr


# ── netsanity ─────────────────────────────────────────────────────────────────────

def parse_netsanity(stdout: str, *, expect_mode: str | None,
                    expect_engine: str | None) -> dict[str, Any]:
    """The artifact on stdout to an address set, or an explained failure."""
    try:
        artifact = json.loads(stdout)
    except (json.JSONDecodeError, TypeError) as error:
        return {"ok": False, "error": f"stdout is not JSON: {error}", "addresses": []}
    if not isinstance(artifact, dict):
        return {"ok": False, "error": "artifact is not an object", "addresses": []}

    run = artifact.get("run") or {}
    mode = run.get("mode", "full")          # absent means 'full' by the 0.2 decoder rule
    engine = (run.get("engine") or {}).get("kind")
    outcome = run.get("outcome")

    devices = artifact.get("devices")
    if not isinstance(devices, list):
        return {"ok": False, "error": "artifact carries no devices array", "addresses": []}
    addresses = [d.get("ip") for d in devices if isinstance(d, dict) and d.get("ip")]
    if any(not isinstance(a, str) for a in addresses):
        return {"ok": False, "error": "a device carries a non-string ip", "addresses": []}

    if expect_mode and mode != expect_mode:
        return {"ok": False,
                "error": f"artifact reports mode {mode!r}, condition expects {expect_mode!r}",
                "addresses": []}
    if expect_engine and engine != expect_engine:
        # The check the 0.3 findings motivated. A privileged condition that ran the
        # unprivileged engine would produce a perfectly valid artifact and a completely
        # meaningless H3.
        return {"ok": False,
                "error": f"artifact reports engine {engine!r}, condition expects "
                         f"{expect_engine!r} — a privileged run that fell back to the "
                         f"unprivileged engine is not the condition it claims to be",
                "addresses": []}

    timing = run.get("timing") or {}
    stage_list = [s for s in timing.get("stages", []) if isinstance(s, dict)]
    stages = [s.get("stage") for s in stage_list]
    # The discovery stage's own accounting, copied into the record rather than left in
    # the artifact.  The 0.6 pilot cited `replies_seen` against `hosts_found` as the
    # evidence that a warm run reports neighbour-table entries it never heard from —
    # and cited it out of the raw artifact, which is git-ignored, so the one number
    # carrying the cache-state mechanism was the one a reviewer could not recompute
    # from the NDJSON.  Schema 2.  Recorded, never analysed by the harness.
    discovery = None
    for s in stage_list:
        if s.get("stage") == "discovery":
            discovery = {
                "replies_seen": s.get("replies_seen"),
                "hosts_found": s.get("hosts_found"),
                "probes_sent": s.get("probes_sent"),
                "elapsed_millis": s.get("elapsed_millis"),
                "budget_policy": s.get("budget_policy"),
            }
            break
    engine_capabilities = (run.get("engine") or {}).get("capabilities")
    started, finished = run.get("started_at"), run.get("finished_at")
    self_reported = None
    if isinstance(started, (int, float)) and isinstance(finished, (int, float)):
        # Recorded, never analysed. See the module docstring.
        self_reported = (finished - started) / 1000.0 if finished > 1e11 else float(finished - started)
    return {
        "ok": True,
        "error": None,
        "addresses": addresses,
        "artifact_mode": mode,
        "engine_kind": engine,
        "engine_capabilities": engine_capabilities,
        "outcome": outcome,
        "stages": stages,
        "discovery": discovery,
        "schema": artifact.get("schema"),
        "degradations": artifact.get("degradations", []),
        "tool_self_reported_seconds": self_reported,
    }


def run_netsanity(argv: list[str], *, raw_dir: Path, run_id: str,
                  expect_mode: str | None = "discovery_only",
                  expect_engine: str | None = None,
                  timeout: float = 180.0) -> Outcome:
    code, out, err, elapsed, started, finished = _invoke(argv, timeout)
    if _sudo_refused(code, err):
        raise PrivilegeUnavailable(
            f"`sudo -n` refused for {argv[:4]}: {err.strip().splitlines()[:1]}"
        )
    parsed = parse_netsanity(out, expect_mode=expect_mode, expect_engine=expect_engine)
    return Outcome(
        argv=argv, exit_status=code,
        stdout_path=_write(raw_dir / f"{run_id}.netsanity.json", out),
        stderr_path=_write(raw_dir / f"{run_id}.netsanity.err", err),
        wall_clock_seconds=elapsed,
        started_at_unix=started, finished_at_unix=finished,
        parsed=parsed,
    )


# ── nmap ──────────────────────────────────────────────────────────────────────────

def parse_nmap_xml(text: str) -> dict[str, Any]:
    """nmap's XML to an address set.

    The XML rather than stdout: stdout is a human report and its wording has changed
    between releases, while `-oX` is the interface nmap documents for programs.  The
    discovery `reason` is kept per host because it is how the privileged and
    unprivileged conditions are told apart from the evidence rather than from the argv
    — `arp-response` where the segment is local and root was held, `syn-ack` where it
    was not.
    """
    try:
        root = ET.fromstring(text)
    except ET.ParseError as error:
        return {"ok": False, "error": f"nmap XML did not parse: {error}", "addresses": []}
    if root.tag != "nmaprun":
        return {"ok": False, "error": f"root element is {root.tag!r}, not 'nmaprun'",
                "addresses": []}

    addresses, reasons = [], {}
    for host in root.findall("host"):
        status = host.find("status")
        if status is None or status.get("state") != "up":
            continue
        for address in host.findall("address"):
            if address.get("addrtype") == "ipv4" and address.get("addr"):
                addresses.append(address.get("addr"))
                reasons[address.get("addr")] = status.get("reason")

    runstats = root.find("runstats")
    finished = runstats.find("finished") if runstats is not None else None
    elapsed = finished.get("elapsed") if finished is not None else None
    exit_state = finished.get("exit") if finished is not None else None
    if exit_state is not None and exit_state != "success":
        return {"ok": False,
                "error": f"nmap reports exit={exit_state!r}: "
                         f"{finished.get('errormsg')!r}",
                "addresses": []}
    if finished is None:
        # A truncated XML file parses if the closing tag happens to be there but
        # <finished> is how nmap says it got to the end. Without it the run was cut
        # short and the address set is a partial one.
        return {"ok": False, "error": "nmap XML has no <runstats><finished>: the run did "
                                      "not complete and its address set is partial",
                "addresses": []}
    return {
        "ok": True,
        "error": None,
        "addresses": addresses,
        "reasons": reasons,
        "nmap_version": root.get("version"),
        "nmap_args": root.get("args"),
        "tool_self_reported_seconds": float(elapsed) if elapsed else None,
    }


# 3600 s, not 600. A timeout that fires on the comparator's slowest template excludes
# that condition on every block it fires — one in thirteen is 7.7%, over section 7's 5%
# ceiling — and does so in the direction that flatters netsanity. The slowest template
# is not the one gate 0.3 expected: privileged `-T2` was extrapolated at about 510 s,
# but UNPRIVILEGED `-T2` serialises its connect probes and pays the kernel's ARP
# resolution timeout for every empty address, and the 0.6 settle measurement saw it
# reach 217 of 254 addresses in 1800 s. A ceiling of an hour leaves that run room to
# finish; a run that reaches it is a finding, recorded as a timeout, and not a run the
# apparatus quietly cut short.
NMAP_TIMEOUT_SECONDS = 3600.0


def run_nmap(argv: list[str], *, raw_dir: Path, run_id: str, xml_path: Path,
             timeout: float = NMAP_TIMEOUT_SECONDS) -> Outcome:
    code, out, err, elapsed, started, finished = _invoke(argv, timeout)
    if _sudo_refused(code, err):
        raise PrivilegeUnavailable(
            f"`sudo -n` refused for {argv[:4]}: {err.strip().splitlines()[:1]}"
        )
    try:
        xml_text = xml_path.read_text(encoding="utf-8")
    except OSError as error:
        parsed = {"ok": False, "error": f"no XML at {xml_path}: {error}", "addresses": []}
        xml_text = None
    else:
        parsed = parse_nmap_xml(xml_text)
    # The XML is left exactly where nmap wrote it and is not copied or rewritten. After
    # a privileged run the file is root's, and the first version of this function
    # rewrote it in place as the owner — a PermissionError on the first `sudo nmap` of
    # the first live block, which no dry run could have shown because the stubs never
    # run nmap. If nmap wrote nothing there is nothing to keep, and `parsed` says so.
    return Outcome(
        argv=argv, exit_status=code,
        stdout_path=_write(raw_dir / f"{run_id}.nmap.out", out),
        stderr_path=_write(raw_dir / f"{run_id}.nmap.err", err),
        xml_path=str(xml_path) if xml_text is not None else None,
        wall_clock_seconds=elapsed,
        started_at_unix=started, finished_at_unix=finished,
        parsed=parsed,
    )


# ── stubs, for --dry-run ──────────────────────────────────────────────────────────
#
# The stubs emit real output in each tool's real format and hand it to the real parser.
# A dry run that bypassed the parsers would prove only that the loop iterates; the point
# of it is to prove that a record can be assembled, validated, written and read back,
# and the parsers are on that path.

_STUB_ADDRESSES = ["10.10.20.1", "10.10.20.3", "10.10.20.50", "10.10.20.57"]


def _stub_netsanity_artifact(mode: str, engine: str, addresses: list[str]) -> str:
    now = int(time.time() * 1000)
    return json.dumps({
        "schema": 1,
        "degradations": [],
        "devices": [
            {"ip": address, "mac": None, "names": [], "ports": [],
             "first_seen": now, "last_seen": now, "ttl": 64,
             "identification": "unidentified", "identity_stability": "stable",
             "identification_evidence": {},
             "rtt": {"millis": 1.0, "samples": 1, "smoothed_millis": 1.0,
                     "variance_millis": 0.0}}
            for address in addresses
        ],
        "run": {
            "id": "stub", "target": "10.10.20.0/24", "interface": "en0",
            "mode": mode, "outcome": "complete",
            "started_at": now, "finished_at": now + 420,
            "engine": {"kind": engine, "name": f"{engine}-icmp",
                       "capabilities": ["icmp_sweep"]},
            "timing": {"probes_sent": 254, "replies_seen": len(addresses),
                       "peak_concurrency": 64, "effective_probes_per_second": 600.0,
                       "stages": [{"stage": "discovery", "elapsed_millis": 420.0,
                                   "hosts_found": len(addresses),
                                   "probes_sent": 254, "replies_seen": len(addresses)}]},
        },
    })


def _stub_nmap_xml(addresses: list[str], reason: str, args: str) -> str:
    hosts = "".join(
        f'<host><status state="up" reason="{reason}"/>'
        f'<address addr="{a}" addrtype="ipv4"/></host>'
        for a in addresses
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?><nmaprun scanner="nmap" '
        f'version="7.991" args="{args}">{hosts}'
        '<runstats><finished time="0" elapsed="4.20" exit="success"/>'
        f'<hosts up="{len(addresses)}" down="0" total="{len(addresses)}"/>'
        '</runstats></nmaprun>'
    )


def run_stub(condition, argv: list[str], *, raw_dir: Path, run_id: str,
             xml_path: Path) -> Outcome:
    """Execute the structure with the tool replaced, and nothing else replaced.

    The stubbed timing is a short real sleep rather than a fabricated number, so that
    `wall_clock_seconds` in a dry run is still something the harness measured. A dry-run
    record with a hand-written duration would make the schema's timing checks vacuous at
    exactly the moment they are being tested.
    """
    started_wall = time.time()
    started = time.monotonic()
    time.sleep(0.01)
    if condition.tool == "netsanity":
        mode = "discovery_only" if "--discovery-only" in argv else "full"
        engine = "privileged" if condition.privilege == "root" else "unprivileged"
        text = _stub_netsanity_artifact(mode, engine, _STUB_ADDRESSES)
        elapsed = time.monotonic() - started
        parsed = parse_netsanity(
            text, expect_mode=mode,
            expect_engine=engine if condition.privilege == "root" else None,
        )
        return Outcome(
            argv=argv, exit_status=0,
            stdout_path=_write(raw_dir / f"{run_id}.netsanity.json", text),
            stderr_path=_write(raw_dir / f"{run_id}.netsanity.err", ""),
            wall_clock_seconds=elapsed, started_at_unix=started_wall,
            finished_at_unix=time.time(), parsed=parsed, stubbed=True,
        )

    # nmap. Unprivileged nmap on this build reaches hosts only over TCP 80/443, which
    # 0.3 measured; the stub reproduces that asymmetry so a dry run exercises the
    # analysis's handling of two very different address-set sizes rather than a tidy
    # symmetric one.
    if condition.privilege == "root":
        addresses, reason = _STUB_ADDRESSES, "arp-response"
    else:
        addresses, reason = _STUB_ADDRESSES[:1], "syn-ack"
    text = _stub_nmap_xml(addresses, reason, " ".join(argv))
    elapsed = time.monotonic() - started
    parsed = parse_nmap_xml(text)
    return Outcome(
        argv=argv, exit_status=0,
        stdout_path=_write(raw_dir / f"{run_id}.nmap.out", "stubbed"),
        stderr_path=_write(raw_dir / f"{run_id}.nmap.err", ""),
        xml_path=_write(raw_dir / f"{run_id}.nmap.xml", text),
        wall_clock_seconds=elapsed, started_at_unix=started_wall,
        finished_at_unix=time.time(), parsed=parsed, stubbed=True,
    )
