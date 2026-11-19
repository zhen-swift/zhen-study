"""Study 2, S2: zhen-core's study contract (gate G9, rows 1–6 and 8) on the testbed, against the frozen binary.

    python3 v2/harness/contract.py            (a runner job, arm testbed)

A port of the `g9` function of zhen-core's `Scripts/verify-reach-testbed.sh` at tag 0.8.1: the same scans, with the
same flags, in the same order. Ported rather than run because the script needs `jq`, which the mini does not have
(nothing is installed for this), and because it prints rows without judging them; this judges each one. The
function's text at the tag is saved beside the results, with its blob hash, so the port can be checked against it.

Row 7 (zhen as root) is excluded: zhen's root line is added at the freeze (S5). Row 8: this build reports no commit
(`frozen-binary-v2.json` → `version_note`), so its commit half is judged against the freeze record, and the
binary's sha256 against the frozen one is what identifies the file.

Writes `$ZHEN_STUDY2_DATA/contract/g9-<stamp>/`: every artifact, `g9-function.sh`, and `contract.json` with
`passed`. Exit 1 if any judged row fails.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
V2 = HERE.parent
CONFIG = json.loads((V2 / "config.json").read_text())
FROZEN = json.loads((V2 / "frozen-binary-v2.json").read_text())
ZHEN = FROZEN["path"]
CORE = Path(os.environ.get("ZHEN_CORE_CLONE", "/Users/zhenstudy/Dev/InfinityCastle/zhen-core"))
TAG = FROZEN["tag"]
SCRIPT = "Scripts/verify-reach-testbed.sh"
CIDR, IFACE = CONFIG["testbed"]["cidr"], CONFIG["testbed"]["interface"]
DATA = Path(os.environ.get("ZHEN_STUDY2_DATA", "/Users/Shared/zhen-study2/data"))

#: Row 1's flags, exactly as the script passes them, and the reach echo each must produce.
ROW1_FLAGS = ["--reach-percentile", "0.9", "--first-scan-wait", "1200ms", "--reach-cap", "4s",
              "--reach-min-samples", "10", "--reach-device-min-samples", "3", "--reach-margin", "1.5",
              "--reach-miss-backoff", "3", "--expected-attempts-step", "400ms", "--expected-attempts-cap", "7"]
ROW1_ECHO = {"percentile": 0.9, "first_scan_wait_millis": 1200, "cap_millis": 4000, "min_samples": 10,
             "device_min_samples": 3, "device_margin": 1.5, "miss_backoff": 3, "attempts_step_millis": 400,
             "attempts_cap": 7}


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def git(*args):
    return subprocess.run(["git", "-C", str(CORE), *args], capture_output=True, text=True, check=True).stdout


def g9_function(script_text):
    """The `g9() { … }` function's text, up to the next top-level closing brace."""
    m = re.search(r"^g9\(\) \{\n.*?^\}\n", script_text, re.S | re.M)
    return m.group(0) if m else None


def same(a, b):
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return abs(float(a) - float(b)) < 1e-9
    return a == b


def check(what, expected, got):
    return {"what": what, "expected": expected, "got": got, "ok": same(expected, got)}


def present(what, got):
    return {"what": what, "expected": "present", "got": got, "ok": got is not None}


def judge(a, version_text, store_unchanged):
    """Pure: the judged rows from the artifacts `a` (name → parsed JSON). Each row is {row, checks, passed}."""
    rows = []

    def row(name, checks, note=None):
        r = {"row": name, "checks": checks, "passed": all(c["ok"] for c in checks)}
        if note:
            r["note"] = note
        rows.append(r)

    reach = a["1"]["run"]["reach"]
    row("1", [check(f"run.reach.{k}", v, reach.get(k)) for k, v in ROW1_ECHO.items()])
    row("1w", [check("run.reach.expected_window_millis", 1, a["1w"]["run"]["reach"].get("expected_window_millis"))])
    row("1u", [check("run.reach.unexpected_cold", "first-scan", a["1u"]["run"]["reach"].get("unexpected_cold"))])
    row("1i", [check("run.ipv6_window.millis (2s)", 2000, a["1i"]["run"]["ipv6_window"].get("millis")),
               check("run.ipv6_window.millis (0)", 0, a["1i0"]["run"]["ipv6_window"].get("millis"))])
    row("2", [check("run.reach.policy", "learned", a["2"]["run"]["reach"].get("policy")),
              check("run.neighbor_watch.enabled", False, a["2"]["run"]["neighbor_watch"].get("enabled"))])
    r3 = a["3"]["run"]["reach"]
    row("3", [check("run.reach.first_scan", True, r3.get("first_scan")),
              check("run.reach.history_samples", 0, r3.get("history_samples")),
              check("run.reach.history_read", False, r3.get("history_read")),
              check("history store unchanged by --no-history", True, store_unchanged)])
    hosts = [d for d in a["4"]["devices"] if "local_interface" not in (d.get("discovered_via") or [])]
    stage = next((s for s in a["4"]["run"]["timing"]["stages"] if s.get("stage") == "discovery"), {})
    row("4", [check("hosts found on the cold run", True, len(hosts) > 0)] +
        [present(f"{(d.get('addresses') or ['?'])[0]} found_after_millis", d.get("found_after_millis")) for d in hosts])
    vias = sorted({v for d in hosts for v in (d.get("discovered_via") or [])})
    row("5", [check("every host has discovered_via", True, all(d.get("discovered_via") for d in hosts)),
              check("neighbor_resolved among them (the silent host)", True, "neighbor_resolved" in vias)],
        note=f"discovered_via seen: {vias}")
    row("6", [present(f"discovery stage {k}", stage.get(k))
              for k in ("attempts", "concurrency", "retransmit_budget_millis", "tail_budget_millis")])
    tool = a["1"]["run"]["tool"]
    row("8", [check("zhen --version names the tag", True, version_text.startswith(TAG)),
              check("run.tool.version", TAG, tool.get("version")),
              check("run.tool.commit, as the freeze record says this build reports", None, tool.get("commit"))],
        note="this build embeds no commit (frozen-binary-v2.json version_note); the file is identified by sha256")
    return rows


def main():
    out = DATA / "contract" / f"g9-{time.strftime('%Y%m%d-%H%M%S')}"
    out.mkdir(parents=True, exist_ok=True)
    store = out / "history.ndjson"
    env = dict(os.environ, ZHEN_HISTORY=str(store))

    binary_sha = sha256(ZHEN)
    script_text = git("show", f"{TAG}:{SCRIPT}")
    function = g9_function(script_text)
    (out / "g9-function.sh").write_text(function or "")
    record = {"schema_version": 1, "what": "zhen-core study contract, G9 rows 1-6 and 8, on the testbed",
              "binary": ZHEN, "binary_sha256": binary_sha, "frozen_sha256": FROZEN["sha256"],
              "port_of": {"repo": "zhen-swift/zhen-core", "tag": TAG, "path": SCRIPT,
                          "blob": git("rev-parse", f"{TAG}:{SCRIPT}").strip(), "function": "g9"},
              "cidr": CIDR, "interface": IFACE, "started_at": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
    if binary_sha != FROZEN["sha256"]:
        raise SystemExit(f"{ZHEN} is not the frozen binary ({binary_sha})")
    if not function:
        raise SystemExit(f"no g9() in {SCRIPT} at {TAG}")

    # The segment the contract runs on: study 1's manifest, which 500x is exactly.
    subprocess.run([sys.executable, str(V2 / "testbed" / "netbed2.py"), "apply", "--manifest", "d500.json"],
                   check=True)

    def scan(name, *flags):
        argv = [ZHEN, "scan", "--cidr", CIDR, "--iface", IFACE, "--discovery-only", "--json", "--quiet", *flags]
        p = subprocess.run(argv, capture_output=True, text=True, env=env, timeout=300)
        (out / f"g9-{name}.json").write_text(p.stdout)
        if p.returncode != 0:
            raise SystemExit(f"scan {name} exited {p.returncode}: {p.stderr.strip()[:300]}")
        print(f"  scan {name}: {' '.join(flags) or '(defaults)'}", flush=True)
        return json.loads(p.stdout)

    def cold():
        subprocess.run(["sudo", "-n", "/usr/sbin/arp", "-a", "-d"], capture_output=True, check=True)

    # The script's order (g9 at the tag). Its row 7 (root) is not run.
    if store.exists():
        store.unlink()
    version_text = subprocess.run([ZHEN, "--version"], capture_output=True, text=True).stdout.strip()
    a = {"1": scan("1", *ROW1_FLAGS),
         "1w": scan("1w", "--expected-window", "1ms"),
         "1u": scan("1u", "--unexpected-cold", "first-scan"),
         "1i": scan("1i", "--ipv6-window", "2s"),
         "1i0": scan("1i0", "--ipv6-window", "0"),
         "2": scan("2", "--reach", "learned", "--no-neighbor-watch")}
    before = sha256(store) if store.exists() else None
    a["3"] = scan("3", "--no-history")
    store_unchanged = before == (sha256(store) if store.exists() else None)
    cold()
    a["4"] = scan("4")

    rows = judge(a, version_text, store_unchanged)
    record.update({"version_text": version_text, "rows": rows, "excluded": {"7": "zhen as root: its line comes at S5"},
                   "finished_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                   "passed": all(r["passed"] for r in rows)})
    (out / "contract.json").write_text(json.dumps(record, indent=1) + "\n")
    for r in rows:
        bad = [c for c in r["checks"] if not c["ok"]]
        print(f"row {r['row']:<3} {'ok' if r['passed'] else 'FAILED'}" +
              "".join(f"\n      {c['what']}: expected {c['expected']!r}, got {c['got']!r}" for c in bad) +
              (f"\n      {r['note']}" if r.get("note") else ""), flush=True)
    print(f"wrote {out}/contract.json; G9 rows 1-6 and 8 {'met' if record['passed'] else 'NOT MET'}", flush=True)
    return 0 if record["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
