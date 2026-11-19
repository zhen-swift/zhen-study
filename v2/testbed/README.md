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

## Running it

Each step is one runner job (`arm: testbed`, any time), queued from the MacBook after `repo/` is pinned to the
commit that has this code:

1. Smoke: `up --only netbed1`, then a separate `status`. Answers three unknowns: does a VZ machine start under a
   LaunchDaemon with nobody logged in; does `bridge100` appear; does the machine outlive the job that started it
   (launchd ends a job's process group when its main process exits, unless `AbandonProcessGroup` is set). If not,
   stop: the fix (`AbandonProcessGroup` in the runner's plist) is a root step for JC.
2. `up`, then `configure --dispersion 500`, `50`, `5`, `1`.
3. `/study-sync`; every manifest `within_gate_tolerance: true`.
4. `rebuild`, then for each dispersion `apply --manifest d<D>.json` and `verify --manifest d<D>.json`. Four
   `passed: true` is the gate.
