# Study 2 — ledger

Append-only. Format in `BRIEF.md`. Times are the mini's local time, with its UTC offset.

## 2026-11-02 · setup · plan written
What: run contract (`RUN.md`), brief (`BRIEF.md`), mini setup (`mini/SETUP.md`), review-PR layout (`REVIEW-PR.md`),
agent wrapper and permissions (`agent/`). Decided with JC 2026-10-31 and 2026-11-02; every decision is in `RUN.md`.

## 2026-11-06 · setup · the repository starts itself
What: `START.md` replaces `mini/SETUP.md`. One prompt on a fresh mini clones this repository and follows it; the
frozen binary comes from the release `study2-binary` by checksum; no SSH and no copying by hand. The agent and the
collection run as LaunchDaemons under `zhenstudy`, so nobody has to be logged in. Decided with JC; `RUN.md` dated.

## 2026-11-06 · setup · build from source, 0.8.1
What: the binary is built on the mini from zhen-core 0.8.1 (`b6636fa63d5e906a727139a2547490a30fbf0bda`) by `START.md`, not carried over from the
MacBook. Decision (JC): a hand-carried build can't be traced to its source; a public commit, a recorded recipe and
a checksum taken before phase 1 can. 0.8.1 over 0.8.0: the published release, same scan behaviour, carries the
compiler fix the mini's newer Swift may need. G9's flag checks re-run on the testbed in S2.

## 2026-11-18 · setup · the Mac mini's network and clock
What: the home LAN is now `10.10.30.0/24` (renumbered from `10.10.20.0/24`); the mini is `10.10.30.100`, fixed by a
DHCP reservation on the router `10.10.30.1`. The mini's zone is `America/Mexico_City`, which has no daylight-saving
time, so the DST-night skip is gone. `PLAN.md`, `RUN.md`, `BRIEF.md`, `START.md`, the hub rule and
`run_block.py`'s `--cidr` default now say so. Decision (JC): the plans follow the machine. Study 1's records keep
`10.10.20.0/24`, where they were measured.

## 2026-11-19 · setup · Claude off the mini; settings in config.json
What: Claude runs only on the MacBook and reaches the mini over SSH (`Mini/scripts/mini`). The mini runs a plain job
runner (`runner/`, LaunchDaemon `dev.zhen.study2.runner`) with no Claude, no tokens and no GitHub sign-in; data
comes back with `/study-sync`. `config.json` now holds the home network, the window, slot and block counts: the
window is on the mini's own clock, whatever its zone, and daylight-saving nights are skipped by checking the UTC
offset, not by date. `STEPS.md` replaces `BRIEF.md`, `SETUP.md` replaces `START.md`, `agent/` is removed, and the
freeze is a merge, not a comment. Decision (JC): Claude stays on the machine with the Touch ID key; the plans
follow the machine instead of naming it.

## 2026-11-19 · setup · leftovers from the 2026-11-18 run
What: `SETUP.md` now opens with every item the old-design `/study-start` run may have left on the mini, each with
exactly one outcome: keep (`zhenstudy`, its grant, the built binary if its record checks out), move (`build.json`),
or remove (Claude Code, the token folder, the old clone, `gh`, MacTeX, any old daemons). Anything not named is
listed, not acted on. Decision (JC): no ambiguity for the setup to resolve by itself.

## 2026-11-18 · S0 · gate passed
What: `/study-setup` made the mini match `SETUP.md` (20:50–21:00 `-0600`). Every 2026-11-18 leftover has its
outcome in `v2/mini/MACHINE.md`; the old run's binary was kept, its `build.json` checking out. `frozen-binary-v2.json`
is now the record of zhen-core 0.8.1 (`b6636fa`), sha256 `e10ac616…94b1`, equal to the installed file's, and
supersedes the 2026-10-17 record of 0.8.0. Setup grant removed, `sudo -n true` fails; runner `running`, queue
empty.  ·  Evidence: `v2/mini/MACHINE.md`, `v2/frozen-binary-v2.json`, hub `Mini/.run/2026-11-18-2050…2059-*.sh`
·  Decision (JC): Homebrew `zhen` 0.9.0 (tap `zhen-swift/zhen`), which `SETUP.md` does not name, stays on the
mini; the harness calls the frozen binary by its full path.

## 2026-11-18 · S0 · runner reads its repo's commit
What: as `zhenstudy`, git refused `repo/` (owned by the admin account: "dubious ownership"), so `runner.sh` would log
`"repo":"none"` and `harness/provenance.py` would fail every job on `git status`. `runner.sh` now exports
`safe.directory` for `repo/` as command-scope git config, which jobs inherit. Tested on the mini against a repo
owned by another user.  ·  Evidence: `v2/runner/runner.sh`  ·  Decision (JC): fix it now, before any job runs;
the mini gets it when `/study-run` pins the repo.

## 2026-11-18 · S1 · the ladder, the image, the code
What: `v2/testbed/` builds study 2's four segments by importing study 1's `testbed/` (unchanged). Ladder per
dispersion d ∈ {1, 5, 50, 500}: study 1's delays scaled in log space, `500 · (s/500)^(ln d / ln 500)`, 0.1 ms;
500× is study 1's exactly, 1× is 500 ms everywhere. Composition is study 1's. Image pinned: Ubuntu 24.04 arm64
`release-20261017`, `sha256:50e24e1f…348e`. The machines are built and measured by runner jobs as `zhenstudy`;
records go to the runner's `data/testbed/`, and `applied.json` names what is on the segment now.  ·  Evidence:
`v2/testbed/README.md`, `v2/testbed/test_ladder.py` (16 pass)  ·  Decision (JC): the slowest host stays at 500 ms
and only the spread changes, so dispersion is not confounded with the slowest round trip; the testbed is built
through the runner.

## 2026-11-19 · S1 · gate failed, twice for the host, not the design
What: calibration put all four manifests inside 2%, but after the rebuild all four verify runs failed (08:09–08:26
`-0600`). (1) Some responders came back late by min(half the netem delay, ~10 ms): +0.48 ms at 1 ms, +4.9 at 10,
+10.1 at 25 and above. It came and went per responder, so calibration had absorbed it and the rebuild moved it. The
runner's plist said `ProcessType Background`; the job and lima's host agents ran at priority 4 (darwinbg), whose
timer wake-ups macOS coalesces late by that rule. (2) The neighbour table read empty: Homebrew's `python3` runs as
`Python.app`, and macOS hides hardware addresses from an app without Local Network permission and from everything
it starts (`arp -an` and `netstat -rnl` from it show none, from a shell all of them).  ·  Evidence:
`v2/testbed/manifests/2026-11-19-attempt-1-background/`, `v2/testbed/README.md` (Attempt 1)  ·  Decision (JC,
"fix what you need"): the runner runs `ProcessType Interactive`, since a study that measures timing must not run its
instruments, or the scanners under test, in background policy. `netbed2.py` refuses to build or measure from
background policy, records `host_conditions` with every result, fails a calibration that corrects more than 1 ms,
and reads the neighbour table as root (`arp` is in `zhenstudy`'s grant). For S2: the harness reads the neighbour
table the same way and needs the same fix. Every `netbed2.py` job also leaves background policy itself at start (`setpriority(PRIO_DARWIN_PROCESS)`, checked, recorded as `host_conditions.at_start`), so the testbed does not wait on the plist being reinstalled, which needs root. Rebuild, recalibrate, re-verify.

## 2026-11-19 · S1 · a job cannot leave launchd's background policy
What: `netbed2.py` now calls `setpriority(PRIO_DARWIN_PROCESS, 0, 0)` at start. It clears `taskpolicy -b`, but under
the runner (plist still `ProcessType Background`) the status job of 11:31 `-0600` stayed at priority 4 (rc 0), with the
five host agents at 4. So the plist must be reinstalled as root before any testbed job; the jobs refuse until then.
Also fixed: `status` lost its `machines` and `bridge100` keys to a misplaced comment, and now compares the
neighbour table as root and from Python over the whole segment.  ·  Evidence: the mini's
`data/testbed/status-20261119-113138.json`  ·  Decision: none new; JC's root step `Mini/.run/2026-11-19-1100-runner-interactive.sh`
in the hub.
