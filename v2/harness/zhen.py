"""Running zhen 0.8.1 and reading its artifact (schema 4).

`parse()` turns the JSON zhen prints into the record's `parsed` field and a list of `warnings`: every way the
artifact differs from what this study relies on. A warning is not an exclusion by itself, but the S2 gate is a
dry run with none, so a key that moves or a type that changes is seen before collection, not in the analysis.
An artifact that does not parse at all is `ok: False`, never an empty address set.

Wall clock is taken here, around the process, with `time.monotonic()`: never the tool's own report.
"""

from __future__ import annotations

import json
import subprocess
import time

SCHEMA = 4
TOOL_VERSION = "0.8.1"
SUDO_REFUSED = ("a password is required", "sudo: a terminal is required")

#: The keys every run object carries at schema 4 on this build, with their types. Anything missing or of another
#: type is a warning.
RUN_KEYS = {"engine": dict, "id": str, "interface": str, "mode": str, "outcome": str, "started_at": int,
            "finished_at": int, "target": str, "timing": dict, "tool": dict, "reach": dict,
            "neighbor_watch": dict, "ipv6_window": dict}
REACH_KEYS = {"policy": str, "first_scan": bool, "history_read": bool, "history_samples": int,
              "first_scan_wait_millis": (int, float), "cap_millis": (int, float), "known_network": bool,
              "unexpected_cold": str, "expected_count": int, "paths": dict}
WATCH_KEYS = {"enabled": bool, "mechanism": str, "poll_interval_millis": (int, float), "polls": int,
              "largest_dump_bytes": int, "resolved": int}
IPV6_KEYS = {"policy": str, "millis": (int, float)}
STAGE_KEYS = {"stage": str, "elapsed_millis": (int, float), "attempts": int, "concurrency": int,
              "probes_sent": int, "replies_seen": int, "hosts_found": int, "late_replies": int,
              "retransmit_budget_millis": (int, float), "tail_budget_millis": (int, float)}
DEVICE_KEYS = {"addresses": list, "discovered_via": list, "found_after_millis": (int, float),
               "first_contact_millis": (int, float), "first_contact_cold": bool}
#: `DiscoverySource` at 0.8.1, every case.
DISCOVERED_VIA = {"probe_reply", "arp_reply", "neighbor_resolved", "neighbor_table", "local_interface"}
ENGINES = {"user": "unprivileged", "root": None}   # root: whatever 0.8.1 names it, recorded, not presumed


def _typed(where, obj, keys, warnings, *, optional=()):
    for key, kind in keys.items():
        if key not in obj:
            if key not in optional:
                warnings.append(f"{where}.{key} missing")
        elif obj[key] is not None and not isinstance(obj[key], kind):
            warnings.append(f"{where}.{key} is {type(obj[key]).__name__}")
        elif isinstance(obj[key], bool) and kind in (int, (int, float)):
            warnings.append(f"{where}.{key} is bool")


def parse(stdout, *, privilege="user", flags=()):
    """The artifact as the record keeps it: addresses found, how, and the settings zhen echoed. Pure."""
    try:
        a = json.loads(stdout)
    except ValueError as error:
        return {"ok": False, "error": f"zhen's output is not JSON: {error}", "addresses": []}, []
    if not isinstance(a, dict) or not isinstance(a.get("run"), dict) or not isinstance(a.get("devices"), list):
        return {"ok": False, "error": "no run object or no devices list", "addresses": []}, []

    warnings = []
    if a.get("schema") != SCHEMA:
        warnings.append(f"schema is {a.get('schema')!r}, not {SCHEMA}")
    run = a["run"]
    _typed("run", run, RUN_KEYS, warnings)
    reach, watch, v6 = run.get("reach") or {}, run.get("neighbor_watch") or {}, run.get("ipv6_window") or {}
    # `paths` counts how a history plan placed each address; a learned or fixed run builds no such plan.
    _typed("run.reach", reach, REACH_KEYS, warnings, optional=() if reach.get("policy") == "history" else ("paths",))
    _typed("run.neighbor_watch", watch, WATCH_KEYS, warnings,
           optional=() if watch.get("enabled") else ("mechanism", "poll_interval_millis", "polls",
                                                    "largest_dump_bytes", "resolved"))
    _typed("run.ipv6_window", v6, IPV6_KEYS, warnings)
    stages = (run.get("timing") or {}).get("stages") or []
    discovery = next((s for s in stages if s.get("stage") == "discovery"), None)
    if discovery is None:
        warnings.append("run.timing.stages has no discovery stage")
    else:
        _typed("discovery stage", discovery, STAGE_KEYS, warnings)
    if run.get("mode") != "discovery_only":
        warnings.append(f"run.mode is {run.get('mode')!r}")
    if (run.get("tool") or {}).get("version") != TOOL_VERSION:
        warnings.append(f"run.tool.version is {(run.get('tool') or {}).get('version')!r}")
    engine = (run.get("engine") or {}).get("kind")
    if ENGINES.get(privilege) and engine != ENGINES[privilege]:
        warnings.append(f"engine kind is {engine!r} for a {privilege} run")
    if privilege == "root" and engine == "unprivileged":
        warnings.append("a root run reports the unprivileged engine")

    # The flags the run was given must be the settings it reports.
    if "--ipv6-window" in flags:
        want = flags[flags.index("--ipv6-window") + 1]
        if want == "0" and (v6.get("policy") != "off" or v6.get("millis") not in (0, 0.0)):
            warnings.append(f"--ipv6-window 0 but the window is {v6.get('policy')!r} {v6.get('millis')!r}")
    if "--reach" in flags:
        want = flags[flags.index("--reach") + 1]
        got = reach.get("policy")
        if want in ("learned", "history") and got != want:
            warnings.append(f"--reach {want} but run.reach.policy is {got!r}")
        if want not in ("learned", "history") and got != "fixed":
            warnings.append(f"--reach {want} but run.reach.policy is {got!r}")
    if "--reach-percentile" in flags:
        want = float(flags[flags.index("--reach-percentile") + 1])
        if abs(float(reach.get("percentile") or -1) - want) > 1e-9:
            warnings.append(f"--reach-percentile {want} but run.reach.percentile is {reach.get('percentile')!r}")
    if "--no-neighbor-watch" in flags and watch.get("enabled") is not False:
        warnings.append("--no-neighbor-watch but the watch is enabled")

    hosts, local = [], []
    for i, d in enumerate(a["devices"]):
        _typed(f"devices[{i}]", d, DEVICE_KEYS, warnings,
               optional=("found_after_millis", "first_contact_millis", "first_contact_cold"))
        unknown = set(d.get("discovered_via") or []) - DISCOVERED_VIA
        if unknown:
            warnings.append(f"devices[{i}].discovered_via has {sorted(unknown)}")
        v4 = [x for x in d.get("addresses") or [] if ":" not in x]
        entry = {"addresses": v4, "discovered_via": sorted(d.get("discovered_via") or []),
                 "mac_present": bool(d.get("mac")), "found_after_millis": d.get("found_after_millis"),
                 "first_contact_millis": d.get("first_contact_millis"),
                 "first_contact_cold": d.get("first_contact_cold")}
        (local if "local_interface" in entry["discovered_via"] else hosts).append(entry)

    parsed = {
        "ok": True, "error": None, "schema": a.get("schema"),
        "addresses": sorted({x for h in hosts for x in h["addresses"]}, key=_ip_key),
        "hosts": hosts, "local": [x for h in local for x in h["addresses"]],
        "outcome": run.get("outcome"), "mode": run.get("mode"), "engine": run.get("engine"),
        "tool": run.get("tool"), "run_id": run.get("id"),
        "tool_self_reported_millis": (run.get("finished_at") - run.get("started_at"))
        if isinstance(run.get("finished_at"), int) and isinstance(run.get("started_at"), int) else None,
        "reach": reach, "neighbor_watch": watch, "ipv6_window": v6, "discovery": discovery,
        "degradations": a.get("degradations"),
    }
    return parsed, warnings


def _ip_key(text):
    try:
        return tuple(int(p) for p in text.split("."))
    except ValueError:
        return (999, text)


def run(argv, *, env, timeout=600.0):
    """Runs one scan. Returns (exit, stdout, stderr, wall seconds, started unix, finished unix)."""
    started_wall, started = time.time(), time.monotonic()
    try:
        p = subprocess.run(argv, capture_output=True, text=True, env=env, timeout=timeout)
        code, out, err = p.returncode, p.stdout, p.stderr
    except subprocess.TimeoutExpired as expired:
        code = -9
        out = expired.stdout.decode() if isinstance(expired.stdout, bytes) else (expired.stdout or "")
        err = (expired.stderr.decode() if isinstance(expired.stderr, bytes) else (expired.stderr or "")) \
            + f"\nharness: timed out after {timeout}s"
    return code, out, err, time.monotonic() - started, started_wall, time.time()


def sudo_refused(code, stderr):
    return code != 0 and any(s in stderr for s in SUDO_REFUSED)


def stub_artifact(addresses, *, privilege, flags):
    """A schema-4 artifact for a dry run of a condition that cannot run yet (zhen as root before S5).

    Built from the real contract artifact's shape so it goes through the real parser; every record made from
    it is `stubbed: true` and can never be read as evidence.
    """
    window_off = "--ipv6-window" in flags and flags[flags.index("--ipv6-window") + 1] == "0"
    policy = flags[flags.index("--reach") + 1] if "--reach" in flags else "history"
    stage = {"stage": "discovery", "elapsed_millis": 1.0, "attempts": 3, "concurrency": 512, "probes_sent": 1,
             "replies_seen": 1, "hosts_found": len(addresses), "late_replies": 0,
             "retransmit_budget_millis": 25, "tail_budget_millis": 250}
    return json.dumps({
        "schema": SCHEMA, "degradations": [],
        "run": {"engine": {"kind": "stub", "name": "stub", "capabilities": []}, "id": "stub", "interface": "stub",
                "mode": "discovery_only", "outcome": "complete", "started_at": 0, "finished_at": 1,
                "target": "stub", "timing": {"stages": [stage]}, "tool": {"name": "zhen", "version": TOOL_VERSION},
                "reach": {"policy": policy if policy in ("learned", "history") else "fixed", "first_scan": False,
                          "history_read": True, "history_samples": 1, "first_scan_wait_millis": 1500,
                          "cap_millis": 5000, "known_network": True, "unexpected_cold": "learned",
                          "expected_count": len(addresses), "paths": {}, "percentile": 0.97},
                "neighbor_watch": {"enabled": "--no-neighbor-watch" not in flags, "mechanism": "poll",
                                   "poll_interval_millis": 25, "polls": 1, "largest_dump_bytes": 0, "resolved": 0},
                "ipv6_window": {"policy": "off" if window_off else "sweep", "millis": 0 if window_off else 1.0}},
        "devices": [{"addresses": [x], "discovered_via": ["probe_reply"], "found_after_millis": 1.0,
                     "first_contact_millis": 1.0, "first_contact_cold": True} for x in addresses],
    })
