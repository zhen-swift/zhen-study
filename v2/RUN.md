# Study 2 — how it runs

**Decided with JC, 2026-10-31 and 2026-11-02.** This file is the run contract: where, when, as whom, with
what authority, and where it stops. `PLAN.md` says *what* is measured; `BRIEF.md` is the agent's step list.
A change to anything here is a commit to this file, dated, before the run acts on it.

**2026-11-02:** `main` is the only branch. The paper moved into `paper/` on `main`; the agent cuts `study2`
from `main` and the final PR goes into `main`.

**2026-11-05:** netsanity 0.4.0 is dropped from study 2: the binary no longer exists and cannot be rebuilt to the same
artifact (`PLAN.md`, *The bridge*). The repositories on the mini live in `~/Dev/InfinityCastle`, the same layout as the
development hub.

**2026-11-06:** the binary is built from source on the mini at zhen-core 0.8.1, not copied: a hand-carried
build is a link nobody can check. See *Binary*.

**2026-11-06:** the repository starts itself. `START.md` takes a fresh mini to a running study from one
prompt; nothing is copied by hand. The agent
and the collection run as LaunchDaemons under `zhenstudy`, so no one has to be logged in.

```
 JC, once                      the agent, unattended                          JC
 ─────────                     ─────────────────────────────────────────      ──────────
 START.md ─────► one prompt ──► prep ─► phase 1 ─► freeze PR ══ STOP ══►  /freeze + root line
                                                                               │
                     final PR ══ STOP ══◄ paper ◄ analysis ◄ phase 3 ◄ phase 2 ◄┘
                        │
                        ▼
                  JC merges, removes root
```

## Where and as whom

| | |
|---|---|
| Machine | Mac mini, Apple M6 (`Mac18,5`), macOS 27.0.1, dedicated to the study |
| Account | `zhenstudy`, a standard (non-admin) user. Nothing personal on it |
| Agent | Claude Code, headless (`claude -p`), started hourly by the LaunchDaemon `dev.zhen.study2.agent` through `agent/start.sh`, as `zhenstudy`, with nobody logged in |
| Collection | the LaunchDaemon `dev.zhen.study2.collect`, kept alive: runs the harness argv the agent writes to `~/.zhen-study2/collect.args`, idle while the file is absent |
| Scanning link | Ethernet `en0` on the home network. Wi-Fi `en1` is read for channel load only |
| Clean network | no VPN, no network filter or system extension (checked 2026-10-31: none) |
| Disk | 146 GiB free at setup |

## When

| Arm | Window | Clock |
|---|---|---|
| Testbed — phases 1 and 2 | any time | — |
| Home network — phase 3 and the history-priming scans | **00:00–06:00** | `America/Los_Angeles` |

- The harness checks the clock **before every block**: zone name is `America/Los_Angeles`, NTP offset under 1 s
  (`sntp`), and local time inside the window with the block's expected length. Any check failing: the block is
  skipped and logged, never run.
- **Daylight-saving nights are skipped** (14 March 2027, 7 November 2027): one repeats an hour, the other loses one.
- Phase 3 is **night-only**, in three slots per night: 00–02, 02–04, 04–06. The day stratum in `PLAN.md` is
  dropped because the window has no day; this is a threat to validity, stated in the paper.
- One scanner at a time: a single lock is held by any block or priming scan, so testbed and home runs never overlap.

## Authority

The **OS account is the security boundary.** Claude Code's allow-list (`agent/settings.json`) is the no-prompt
contract: in headless mode anything not listed is refused, never asked. A `python3` the agent is allowed to run can
do what `zhenstudy` can do, so the limits that matter are the account's.

| | Allowed | Not allowed |
|---|---|---|
| Files | the zhen-study clone, `~/.zhen-study2/`, `~/zhen-study2-private/` | anything outside; the tokens in `~/.config/zhen/` are read only by `start.sh` |
| Git | commit; push branches `study2` and `study2-*`; tags `study2/*`; open and edit PRs; comment | **merge**, push to `main`, force-push |
| zhen-core | read | any change. The binary is frozen |
| Root | `sudo -n` on `nmap`, `tcpdump`, `arp`, `wdutil` — and the frozen `zhen` **only after the freeze stop** | any other root |
| Network | GitHub, PyPI (the analysis venv), Ubuntu cloud images (the testbed), CTAN via TeX | web search, web fetch |
| Contact JC | only by stopping | messages, issues, mentions |

Binaries the root grant names live in `/usr/local/zhen-study2/`, owned by root, so `zhenstudy` cannot swap one
to get root.

## Stops — the only three

| Stop | When | JC does | The run resumes when |
|---|---|---|---|
| **Freeze** | phase 1 analysed, `PROTOCOL-v2.md` drafted | reviews the PR in the browser; comments `/freeze`; runs the one command in the PR to add zhen's root line | the wrapper sees `/freeze` from `JCTec` **and** `sudo -n -l` lists zhen |
| **Final** | phase 3 analysed, paper rewritten | reviews and merges; runs the removal command in the PR | — the run is done |
| **Blocked** | something the agent cannot fix after three attempts over three hours | reads `STATE` and the last `LEDGER.md` entry | JC edits `STATE` back to `RUNNING` |

A stop is a state in `v2/STATE`, committed and pushed, and the agent exiting. While stopped, the hourly wrapper
checks for its condition in shell and **does not start Claude**, so a stop costs nothing.

PR layout for both review stops: `REVIEW-PR.md`.

## Resilience

| Event | What happens |
|---|---|
| usage limit, crash, agent exits | launchd starts the wrapper every hour; it resumes from `LEDGER.md` |
| power cut | the mini is on a battery; JC wakes it remotely and unlocks FileVault; the daemons start by themselves |
| macOS update | automatic installs are off for the study |
| a block fails | the harness's own retry rules (`HARNESS.md`); failures are recorded, never deleted |

## Binary

**zhen-core 0.8.1** (commit `b6636fa63d5e906a727139a2547490a30fbf0bda`), built from source on the mini by `START.md` with `swift build -c release`,
installed once at `/usr/local/zhen-study2/zhen`, and never rebuilt until the study ends.

| Link | Where it is recorded |
|---|---|
| source | the public commit above |
| how it was built | the build command, toolchain and host, in `frozen-binary-v2.json` |
| which file | its sha256, taken at install, before phase 1 |
| which file ran | `zhen --version` and `run.tool.commit` in every artifact; the harness hashes the binary on every run |

Builds are not reproducible byte for byte, so the sha256 identifies *this* build within the study, and the
commit plus the recipe is how anyone else gets an equivalent one. 0.8.1 differs from the 0.8.0 frozen on
2026-10-17 by the version string and a compiler fix for macOS 15.6 (19 lines, no change to how a scan runs).

## Private data

Phase 3 raw captures and artifacts name household devices. They stay in `~/zhen-study2-private/` on the mini and
are **never pushed**. Committed phase 3 data carries salted hashes of MACs and addresses; the salt lives in the
private folder.
