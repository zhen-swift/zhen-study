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

## 2026-11-19 · S2 · root reads the neighbour table; unprivileged zhen is measured as macOS 27 leaves it
What: JC ran `llinfo.c` (zhen's exact read) on the mini, as `jc-mini` and with `sudo`: unprivileged, a 0-byte dump;
as root, 716 bytes, 5 entries, all 5 with a hardware address, equal to `arp`'s 5. So on macOS 27 the link-layer
table is withheld from a non-Apple binary unless it runs as root. zhen's root conditions (phase 2's H3 root run,
phase 3's zhen root) keep their neighbour evidence; every unprivileged zhen condition loses it, whatever zhen does.
·  Evidence: `v2/harness/diag/2026-11-19-llinfo-as-root.txt`, `v2/harness/diag/llinfo.c`
·  Decision (Claude, as announced to JC before the test, JC to overrule): (1) The unprivileged conditions are measured
as they behave on macOS 27, not worked around; the withheld table is a finding of the study, stated wherever an
unprivileged result appears. (2) G9 row 5 (`neighbor_resolved`) cannot pass unprivileged on this OS. S2's gate takes
rows 1–4, 6 and 8 on the testbed, and records row 5's unprivileged failure with this cause; row 5 is re-run **as
root** with the frozen binary once JC adds the root line (S5), and must pass before the pilot (S6). The gate is
moved, not dropped. (3) Carried to the freeze (S5), because the protocol is not frozen yet: H7 (the default reaches
recall 1.00 cold) and phase 1's recall ceiling were written for a zhen that sees the table. Without it, the
tcp-only and silent responders (r06, r08) were not found in the contract run, so the unprivileged default's
ceiling on the testbed is 8 of 10. Phase 1 measures that ceiling; `PROTOCOL-v2.md` restates H7 against it or as a
root-run hypothesis, and says why, before the freeze.

## 2026-11-19 · S2 · the harness, and phase 1's block count
What: the harness port in `v2/harness/` (`conditions.py`, `zhen.py`, `record.py`, `run_block.py`, `generate.py`,
`check.py`; decisions in `v2/harness/README.md`), 22 tests passing under `/usr/bin/python3` 3.9 against three
artifacts the frozen binary wrote (`fixtures/`). `config.json` gains `phase1.blocks_per_cell: 20` (it had none;
the generator needs it): 80 phase 1 blocks, ~18 conditions each. `contract.py` now leaves row 5 out of `passed`
with the reason recorded in every contract file (decision of the entry above). Dry-run jobs generated with seed
20261119 (`v2/jobs/dryrun-20261119/`): one phase 1 block, two phase 2 blocks (flush per run with -T2, flush per
block), every condition once, zhen as root stubbed.  ·  Evidence: this commit
·  Decision (Claude, JC to overrule before the freeze): 20 blocks per phase 1 cell, because phase 1 never enters a
hypothesis test and 20 blocks × 10 responders gives 200 host trials per condition and dispersion, enough to tell
P97 from P99 near recall 1 at ~6 h of machine time. pcaps stay on the mini outside `data/`.

## 2026-11-19 · S2 · dry run, first pass: one false warning, fixed; dry run re-generated
What: the first dry-run blocks on `73dc547` ran end to end on the mini (phase 2 d50 flush per block, 11 runs; phase 1
d500, 18 runs): testbed applied, five priming scans, flushes, a capture per run, nmap as root and as user, zhen as
root stubbed. One warning, from the harness's own check, not from zhen: it expected an empty store to give
`first_scan: true` under every reach policy, and 0.8.1 reports it only under `history` (learned and fixed runs
report false). Fixed in `run_block.run_checks`, with tests. These blocks do not count for the gate, which needs a
dry run with no warning on the code that will collect; `v2/jobs/dryrun-2026111902/` re-runs all three (dry-run
block ids now carry the seed).  ·  Evidence: the mini's `data/dryrun/`, jobs `dryrun-0001…`, `dryrun-0002…`

## 2026-11-19 · sync · S2's dry runs and contract runs
What: `/study-sync` copied the runner's `data/` (both dry-run passes: phase 1 1 + 1 blocks, phase 2 2 + 2 blocks, 18 + 24
runs per pass, with raw zhen artifacts, nmap XML and stderr; the two contract runs `g9-20261119-131949` and
`g9-20261119-164343`; testbed `applied.json` and one status) and `logs/runner.ndjson` (102 lines), with every `done/`
and `failed/` job record and log, to `v2/data/` and `v2/runs/`. No failed job in S2. Privacy check: the rsync first
overwrote the committed, hashed testbed copies with the mini's raw VM addresses; the write-once ones were restored
from git and `applied.json` rewritten. The VMs' lima addresses in nmap's root XML (the phase 2 raw folders) and the
testbed files were rewritten as `vm-` hashes, and the mini's bridge address in `status-20261119-131312.json` as
`redacted-host-mac`. Rescan of every synced and every tracked file under `v2/data/` and `v2/runs/`: no hardware
address, no address in the home network. The rewritten raw copies differ from the mini's bytes; no record hashes
them (records hash pcaps, stores and manifests only).

## 2026-11-19 · S2 · gate passed
What: the S2 gate. (1) The dry run `v2/jobs/dryrun-2026111902/` on `a7202ea`, every condition through the runner on the
mini: phase 1 d500 flush per run (18 conditions), phase 2 d50 flush per block (11) and d500 flush per run with -T2
(13), 31 conditions, 42 runs, all three jobs in `done/`. `check.py --blocks dry2026111902` on the synced records: 0
problems and warnings, 0 exclusions. (2) `test_harness.py`: 25 tests pass under `/usr/bin/python3` 3.9. (3) zhen-core's
study contract on the testbed against the frozen binary (`data/contract/g9-20261119-164343/`): rows 1, 1w, 1u, 1i, 2,
3, 4, 6 and 8 met; row 5 fails and is deferred to the root run after S5, before S6 (entry "root reads the table").
Seen in the dry run, single runs and not results: unprivileged nmap at -T2 took 1,538 s and 2,275 s for 10 of 10
hosts, and nmap root at -T2 447 s; a phase 2 block with -T2 therefore runs about 50 min, without it about 3 min.
·  Evidence: `v2/data/dryrun/`, `v2/runs/dryrun-000{1,2,3}-*-dry2026111902.*`, `v2/data/contract/`
·  Next: S3, phase 1 collection (`/study-run phase1`).

## 2026-11-19 · S3 · phase 1 queued
What: phase 1's 80 jobs (20 blocks per dispersion × 4, flush per run, 18 conditions each), generated by
`v2/harness/generate.py phase1 --seed 348798216` (seed drawn with `secrets`), committed in `v2/jobs/phase1-348798216/`
with `design.json`, and queued on the mini from `repo/` pinned to `17f9320` (hub script `Mini/.run/2026-11-19-1900-s3-phase1.sh`,
output in the mini's `~/admin-runs/`). Testbed jobs, so they start now; the generator's estimate is ~9.3 h. The first
job (`phase1-0001-p1-d1-run-014`) was running 20 s after queuing, zone CST, offset -0600.  ·  Evidence: `v2/jobs/phase1-348798216/`, commit 17f9320

## 2026-11-20 · sync · phase 1
What: `/study-sync` copied the runner's `data/` (new: `data/phase1/`, 1,520 rows in `runs.ndjson` = 80 block and
1,440 run records; 1,440 raw zhen artifacts with stderr; the history store each run used, 87 MB uncompressed, ~7 MB
gzipped) and `logs/runner.ndjson` (+160 lines), with the 80 phase 1 job records and logs, to `v2/data/` and
`v2/runs/`. No failed job. Privacy check: the rsync again overwrote the committed, hashed copies of earlier records
(testbed and the dry runs' nmap XML) with the mini's raw ones; restored from git, and `testbed/applied.json`'s VM
addresses hashed. Phase 1's files hold no hardware address (unprivileged zhen sees none on macOS 27). Rescan of every
synced and every tracked file under `v2/data/` and `v2/runs/`: no hardware address, no address in the home network.
·  Evidence: `v2/data/phase1/`, `v2/runs/phase1-*`

## 2026-11-20 · S3 · gate passed
What: phase 1 complete. 80 jobs from `v2/jobs/phase1-348798216/`, all in `done/`, none failed or skipped, run
2026-11-19 17:46–22:18 (mini's clock, -0600; ~4.5 h against the generator's 9.3 h estimate). 72 cells (4 dispersions ×
18 conditions), 20 runs each. `check.py v2/data/phase1/runs.ndjson`: 0 problems and warnings, 0 exclusions. Every
block at repo `17f9320`, clean, binary matching the freeze; no dry or stubbed run; every run cold (flush per run).
·  Evidence: `v2/data/phase1/runs.ndjson`  ·  Next: S4, phase 1 analysis.
