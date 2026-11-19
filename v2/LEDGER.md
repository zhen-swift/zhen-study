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

## 2026-11-19 · S1 · background was not the cause; the sleeping CPU is
What: with the runner `Interactive` (JC reinstalled the plist, 11:4x `-0600`) and every job and host agent at priority
31, all four calibrations (s1b-03…06, 11:44–12:12) still met the extra delay, now on more responders, and the 1 ms guard
failed all four. The cleaner law: the delivered delay is netem's plus min(half of netem's, ~10 ms), following netem
down through calibration (16.18 ms set gives +8.1). The virtualization processes had been at 31 in attempt 1 too, so
background policy was never the mechanism; the 2026-11-19 entries above that say so are wrong about the cause. What
fits: each machine has two virtual CPUs and study 1's spinner keeps one busy; the other sleeps, and a sleeping VZ
virtual CPU is woken by a host timer that fires late by that rule. Responders whose packets land on it are late. The
neighbour-table fix is confirmed (as root: hardware addresses; from Python: none).  ·  Evidence: the mini's
`failed/s1b-03…06-configure-*.log`, `data/testbed/status-20261119-114409.json`  ·  Decision ("fix what you need"):
one virtual CPU per machine (`lima-responder.yaml` `cpus: 1`), and study 1's spinner at `SCHED_IDLE` so the CPU never
sleeps and the spinner yields to all real work; same host cost (one busy core per machine). `Interactive` stays: a
timing study should not run its scanners in background policy either. Rebuild, recalibrate, re-verify.

## 2026-11-19 · S1 · gate passed
What: one virtual CPU per machine (`a18772b`). Rebuild, then calibration of all four ladders (s1c, 12:15–12:39 `-0600`):
every responder within 0.4% of design, the largest correction 0.135 ms (the 1 ms guard never tripped), cold first
contact 2.00× the round trip. Then a second full rebuild and apply + verify of each (s1d, 12:39–12:55): **all four
passed**, worst error 0.6% (500×), 0.19% (50×), 0.014% (5×), 0.007% (1×), against 10%; 10/10 hardware addresses in
the host's neighbour table (read as root), distinct, agreeing with the guests; every job at priority 31, machines
`cpus: 1`, spinner `SCHED_IDLE`.  ·  Evidence: `v2/data/testbed/d{1,5,50,500}.json`,
`v2/data/testbed/verify-d*-20261119-12*.json`, `v2/runs/s1c-*`, `v2/runs/s1d-*`  ·  Decision: none new. S1 → S2.

## 2026-11-19 · sync · S1's records
What: `/study-sync` copied the runner's `data/` (26 testbed records: 9 current, 11 of attempt 1, 6 of attempt 2) and
`logs/runner.ndjson`, 28 done and 14 failed job records with logs, to `v2/data/` and `v2/runs/`. Failures: attempt 1's
four verifies (08:09–08:26, extra delay); attempt 2's status (11:31, a `status` bug since fixed) and five jobs refused as
background policy (11:32–11:34, the guard working); attempt 2's four calibrations (11:50–12:12, the 1 ms guard). Privacy
check: the first scan found the MacBook's LAN address (attempt 1's `who`) and the mini's bridge hardware address in
attempt 2's status; both redacted in the copies, the VMs' lima addresses rewritten as hashes; rescan clean. Also: the
mini's bridge address had been used as a fixture in `test_ladder.py` (`173a7ab`, pushed); replaced, though it stays in
history. `v2/testbed/manifests/2026-11-19-attempt-1-background/` (committed in `173a7ab`, VM addresses unhashed) stays as
written; from here `v2/data/testbed/` is where testbed records live.

## 2026-11-19 · S2 · jobs run under Apple's python3; zhen cannot read the neighbour table on macOS 27
What: (1) `runner.sh` now starts jobs with `/usr/bin/python3` (3.9.6; all study code parses and its tests pass under
3.9): under it, a job reads the full neighbour table without root (s2-00-status, 13:13 `-0600`: 11 entries, equal to
root's). (2) The study-contract job (`v2/harness/contract.py`, a port of zhen-core 0.8.1's `verify-reach-testbed.sh
g9`, s2-01-contract, 13:19) found zhen blind to it anyway: every device `mac: null`, the neighbour watch's dump 0 bytes
(`largest_dump_bytes: 0`, 44 polls, `resolved: 0`), every host `probe_reply` only, r06 (tcp-only) and r08 (silent)
not found. Row 5 (`neighbor_resolved`) fails. (3) Isolated with `v2/harness/diag/llinfo.c`, zhen's exact read
(`sysctl NET_RT_FLAGS/RTF_LLINFO`) and nothing else, built with `cc` (ad hoc signed, like zhen): **a 0-byte dump on
macOS 27.2.1 in every context tried** (mini over SSH, mini under Apple's python3, MacBook from Claude's shell), while
Apple's `/usr/sbin/arp -an` beside it lists 14 (mini) and 4 (MacBook) entries with hardware addresses. macOS 27
appears to withhold the link-layer table from non-Apple binaries. zhen-core's own comment
(`NeighborTable.swift`) says the cache "is readable even when the Local Network permission has been denied"; on this
macOS it is not. Not changed since 0.8.1 on zhen-core `main` (0.9.0 included). Untested: whether root, or a process
with Local Network permission, gets the table.  ·  Evidence: the mini's `data/contract/g9-20261119-131949/`,
`data/testbed/status-20261119-131312.json`, `v2/harness/diag/llinfo.c`  ·  Decision: none. Changing zhen-core or the
frozen binary is outside this step (`STEPS.md`, *Never*); the study's options go to JC.

## 2026-11-19 · S2 · the core fix JC chose does not work; nothing a non-Apple binary starts sees the table
What: JC chose "fix core, re-freeze". The fix (zhen-core branch `fix/arp-tool-fallback`, `2145e8c`, on
`release/0.8.x` cut at 0.8.1; pushed, no PR, not released): when the sysctl comes back empty, read the table through
`/usr/sbin/arp -an`. Built on the mini and run once on the testbed as `jc-mini` (14:30 `-0600`, outside the study):
the fallback ran (`table_source: arp_tool`) and `arp`, started by zhen, printed **0 bytes**; every device still had
no MAC. On the MacBook, `arp` spawned by zhen's test binary also printed 0 bytes while `arp` from the shell listed 4.
Further: a Developer ID–signed build of `llinfo.c` also gets a 0-byte dump (signing is not the key); from Homebrew's
python, `arp` behind one or two Apple shells (`sh -c '…; true'`, forced fork) still prints nothing. What fits every
observation: on macOS 27 a non-Apple executable is the responsible process for itself and everything it starts, and
the link-layer table is withheld unless that process holds Local Network permission, which a command-line tool in a
launchd job cannot be granted. Apple binaries under Apple parents (a shell, `/usr/bin/python3`, the runner) see it.
Untested: root.  ·  Evidence: `Mini/.run/2026-11-19-1430-zhen-0.8.2-precheck.sh` (hub), zhen-core `2145e8c`
·  Decision: none; back to JC. No zhen-core release is made from this branch.
