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
