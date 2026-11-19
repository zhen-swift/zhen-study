# Study 2's testbed (S1)

Four calibrated segments, one per RTT dispersion, built on the Mac mini by the runner. Study 1's `testbed/` is
study 1's instrument and is **not edited**: `netbed2.py` imports its mechanics (`netbed.py`, `verify_gate.py`,
`plan.py`) and adds what study 2 needs.

| File | |
|---|---|
| `ladder.py` | the four ladders, as data |
| `lima-responder.yaml` | study 1's machine, with the image pinned by digest |
| `netbed2.py` | `up`, `status`, `rebuild`, `configure`, `apply`, `verify` |
| `test_ladder.py` | `python3 -m unittest v2/testbed/test_ladder.py` |
| `manifests/` | the records, brought back by `/study-sync` and committed: `d1.json d5.json d50.json d500.json`, the `verify-*.json` gate evidence and the smoke `status-*.json` |

## Decisions

| | Decided | Why |
|---|---|---|
| The ladder | Study 1's delays `s` (1, 5, 25, 100, 500 ms), scaled in log space with the **slowest fixed at 500 ms**: `rtt = 500 · (s/500)^(ln d / ln 500)`, rounded to 0.1 ms. **JC, 2026-11-18** | Only the spread changes. The wait a network-wide timeout must cover is the same in every manifest, so a result about dispersion (H2) is not also one about the slowest round trip. 500× is study 1's exactly; 1× is 500 ms everywhere |
| Composition | Study 1's ten responders, roles, ports and loss, unchanged; two per machine, `netbed1`–`netbed5` | Only the delays are the factor |
| Image | Ubuntu 24.04 arm64 cloud image, dated build `release-20261017` (newest on 2026-11-18), `sha256:50e24e1f…348e` | Pinned by digest; lima refuses a mismatching download. The digest is Ubuntu's `SHA256SUMS` over HTTPS; its GPG signature was not checked. Study 1 used the moving `release/` link |
| Who runs it | The runner, as `zhenstudy`, one job per step | Phase 2 reshapes the segment per block from inside jobs, so the machines must belong to the user the jobs run as. No root, no new grant |
| Where records go | `$ZHEN_STUDY2_DATA/testbed/` (`/Users/Shared/zhen-study2/data/testbed/`) | The repo is read-only to the runner |
| What is on the segment now | `applied.json`, rewritten by `configure` and `apply`, removed by `rebuild` | A rebuild gives the machines new hardware addresses and vmnet's DHCP may give new IP addresses, so the harness reads addresses here, not from a manifest |
| Cold first contact | 5 trials per responder: `sudo -n /usr/sbin/arp -d` (inside `zhenstudy`'s grant), then one ping (or one TCP connect for r06); trials, losses, median and ratio to designed. r08 answers nothing and is unmeasurable | PLAN.md asks for it (about 2× RTT, because netem delays the ARP reply too). Recorded, not gated |
| The gate | Every measured responder within **10% of designed** p50 on 3 runs × 30 probes (study 1's method), distinct agreeing hardware addresses, study 1's composition, the right ladder. Calibration itself stops at 2% (study 1's rule) | STEPS.md S1 |
| A rebuild | `limactl delete -f` every machine, then `up` from the same pinned image (lima's image cache is kept; the digest is checked again) | "Re-verified after a full testbed rebuild" |
| Scheduling | The runner's plist says `ProcessType Interactive`; `up`, `configure`, `apply` and `verify` refuse to run from a background-policy process (`ps` priority ≤ 4) or on machines one started, and every record carries `host_conditions`. **2026-11-19, after attempt 1** | Attempt 1 ran under `ProcessType Background`: some responders came back late by min(half the delay, ~10 ms), which is macOS timer coalescing of a background process's wake-ups, inherited by the VMs. Calibration absorbed it, a rebuild moved it. The scanners under test would inherit it too |
| Calibration guard | `configure` fails if netem ends more than 1 ms below the designed round trip (`large_corrections`) | The path itself costs 0.1–0.3 ms. Attempt 1 calibrated ~10 ms of host artefact into all four manifests and passed its own check |
| Neighbour table | Read as root, `sudo -n /usr/sbin/arp -an` (inside `zhenstudy`'s grant); the source is recorded | Homebrew's `python3` runs as `Python.app`, and macOS hides hardware addresses from an app without Local Network permission and from everything it starts: `arp -an` from it prints nothing. **The harness (S2) reads the neighbour table the same way and needs the same treatment** |

## Attempt 1 (2026-11-19): failed, kept

`manifests/2026-11-19-attempt-1-background/`: the four manifests and four verify records made under
`ProcessType Background`. All four calibrations were inside 2%; after the rebuild every verify failed. Extra delay
per responder, attempt 1's verify:

| Designed | Extra when present |
|---|---|
| 1 ms | +0.48 ms |
| 10 ms | +4.9 ms |
| ≥ 25 ms | +10.1 ms |

It came and went per responder, not per machine. In the 1× manifest it had been calibrated in, then was absent at
verify (r05 and r07 −2%). The neighbour table read empty for the Python reason above. Both are fixed by the
decisions above; nothing in `ladder.py` or the design changed.
