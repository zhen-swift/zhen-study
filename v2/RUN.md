# Study 2 — how it runs

**The run contract,** decided with JC (2026-10-31 to 2026-11-19). `PLAN.md` says *what* is measured, `STEPS.md`
says in what order, and `config.json` holds every value that depends on the network or the clock. A change to any
of them is a dated commit, recorded in `LEDGER.md`, before the next job runs.

```
 MacBook — Claude, with JC                         Mac mini — no Claude, no secrets
 ──────────────────────────────                    ───────────────────────────────────
 /study-setup  ─── SSH (Touch ID) ──────────────►  account, grants, zhen build, runner
 code, testbed, analysis, paper                    
 /study-run    ─── SSH: pin the repo, queue jobs ─►  runner (launchd, unattended)
 /study-status ◄── SSH: read-only snapshot ───────   runs one job at a time, day or night,
 /study-sync   ◄── SSH: copy data/ back ──────────   inside the window for the home network
 commit, push to GitHub (from the MacBook only)
```

## Who does what

| | |
|---|---|
| **Claude** | runs only on JC's MacBook, in sessions JC starts: the harness port, the testbed, the analysis, the paper. It reaches the mini only through `Mini/scripts/mini` (SSH, Secure Enclave key, Touch ID) |
| **The mini** | runs jobs, nothing else. The LaunchDaemon `dev.zhen.study2.runner`, as the standard user `zhenstudy`, with nobody logged in. No Claude, no tokens, no GitHub sign-in: it only ever clones public repositories |
| **GitHub** | written only from the MacBook. The mini never pushes |
| **Data back** | `/study-sync` copies the runner's `data/` and logs to the MacBook over SSH. Phase 3's raw captures never leave the mini |

## The runner

Everything lives in `/Users/Shared/zhen-study2/` (`runner/runner.sh` documents the layout):

- `repo/` is the zhen-study clone the jobs run from. `/study-run` checks out the exact commit before queuing, and
  every job records that commit.
- `queue/` holds one JSON file per job. A job is **one block** (or one priming scan), so a skipped or failed job
  costs one block, never a night.
- The runner takes the first job that may run now: testbed jobs any time, home jobs only inside the window. A job
  that dies mid-run goes to `failed/` and is never re-run silently.
- `PAUSE` stops new jobs. `/study-run stop` writes it.

## When

| Arm | When | Clock |
|---|---|---|
| Testbed — phases 1 and 2 | any time | — |
| Home network — phase 3 and history priming | `config.json` → `home.window` (now 00:00–06:00) | **the mini's own local zone, whatever it is set to** |

No zone is written into the plan. Before every home job, `runner/window.py` checks, from `config.json`:

- the job fits inside the window, with its expected length (windows that cross midnight work)
- the UTC offset does not change while it runs. That skips daylight-saving nights automatically, in any zone
- NTP is within `clock.max_ntp_offset_seconds`
- the scanning interface's address is inside `home.cidr`. If the network is renumbered, home jobs are refused
  until `config.json` is updated

Every job's log line records the zone name and UTC offset it actually ran in. Phase 3's night slots are the window
split into `home.slots_per_night` equal parts. The day stratum is dropped (there is no daytime window), which is a
threat to validity the paper states.

## Authority on the mini

| | Allowed | Not allowed |
|---|---|---|
| The admin account, over SSH | clone, pin the repo, queue jobs, read logs and data | `sudo`, except under the temporary setup grant during `/study-setup` |
| `zhenstudy` (the runner) | write `queue/ running/ done/ failed/ data/ logs/ history/`, its private folder; `sudo -n` on `nmap`, `tcpdump`, `arp`, `wdutil`, and on `zhen` **after the freeze** | change `repo/`, any other root |
| Network | GitHub (public clones), Ubuntu cloud images (the testbed) | everything else |

The binaries the root grant names live in `/usr/local/zhen-study2/`, owned by root, so `zhenstudy` cannot swap
one to get root.

## Where JC decides

| When | JC does |
|---|---|
| `/study-setup` | adds the temporary sudo line on the mini, once |
| **The freeze** | reviews the freeze PR (`REVIEW-PR.md`) and **merges it**. That merge is the freeze. Then adds zhen's root line (one `ssh -t mini` command in the PR) |
| Each phase | runs `/study-run <phase>`. Nothing starts a phase by itself |
| **The end** | reviews the final PR and merges it; removes the grants and the runner (commands in the PR) |

## Resilience

| Event | What happens |
|---|---|
| power cut or reboot | JC unlocks FileVault remotely; the runner starts by itself; an interrupted job is in `failed/` |
| a job fails | it moves to `failed/` with its log; the harness's own rules apply inside it (`HARNESS.md`) |
| the network or zone changes | home jobs are refused or skipped and logged, never run wrongly; `config.json` gets a dated commit |
| macOS update | automatic installs are off for the study |

## Binary

**zhen-core 0.8.1** (commit `b6636fa63d5e906a727139a2547490a30fbf0bda`), built from source on the mini by
`/study-setup` with `swift build -c release`, installed once at `/usr/local/zhen-study2/zhen`, never rebuilt until
the study ends.

| Link | Where it is recorded |
|---|---|
| source | the public commit above |
| how it was built | build command, toolchain and host, in `frozen-binary-v2.json` |
| which file | its sha256, taken at install, before phase 1 |
| which file ran | `zhen --version` and `run.tool.commit` in every artifact; the harness hashes the binary on every run |

Builds are not reproducible byte for byte, so the sha256 identifies *this* build within the study, and the commit
plus the recipe is how anyone else gets an equivalent one. 0.8.1 differs from the 0.8.0 frozen on 2026-10-17 by the
version string and a compiler fix for macOS 15.6 (19 lines, no change to how a scan runs).

## Private data

Phase 3 raw captures and artifacts name household devices. They stay in `/Users/zhenstudy/zhen-study2-private/`
(mode 700) on the mini and are **never copied or pushed**. Committed phase 3 data carries salted hashes of MACs and
addresses; the salt stays in the private folder.
