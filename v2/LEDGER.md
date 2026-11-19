# Study 2 — ledger

Append-only. Format in `BRIEF.md`. Times are `America/Los_Angeles` until 2026-11-18, `America/Mexico_City` after.

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
