# Study 2 — the steps

Each step says where it happens. **MacBook** steps are Claude sessions JC starts in `~/Dev/InfinityCastle`, which
reach the mini over SSH. **Runner** steps are jobs the mini runs unattended. Each step ends at its gate, and the
gate is recorded in `LEDGER.md`.

| | Step | Where | Gate |
|---|---|---|---|
| **S0** | **Set up the mini** (`SETUP.md`) and write `frozen-binary-v2.json` as a new record from `build.json` (tag 0.8.1, commit, recipe, toolchain, host, sha256), `supersedes` the 2026-10-17 record of 0.8.0. Record the machine in `mini/MACHINE.md` | MacBook · `/study-setup` | freeze record written and its sha256 matches the installed file; setup grant removed; runner idle |
| **S1** | **Testbed.** Port `testbed/` to four manifests, one per dispersion (1×, ~5×, ~50×, ~500×; 500× is study 1's manifest exactly). Pin the Ubuntu image by digest. Each manifest records designed RTT, achieved RTT, and the measured cold first-contact time | MacBook, building and measuring on the mini | four manifests inside 10% of design, re-verified after a full testbed rebuild |
| **S2** | **Harness port** (`PLAN.md` sequence, step 3): `zhen` argv and `ZHEN_HISTORY`; schema 4 parser; history state as a factor; cache flush per run; thermal pause; one block per invocation, so one block is one job; `--ipv6-window 0` on every nmap-matched zhen condition. A job generator that turns a phase's design into job files, shuffled with a recorded seed. Unit tests for `runner/window.py` and the parser | MacBook | dry run of every condition through the runner on the mini, **zero validation warnings**; tests pass; zhen-core's study-contract check (gate G9 rows 1–6 and 8) re-run **on the testbed** against this binary |
| **S3** | **Phase 1 collection** | Runner · `/study-run phase1` | every cell complete; every skipped or failed job accounted for |
| **S4** | **Phase 1 analysis.** Recall against wait per dispersion; time against wait; primed vs empty history. Script in `v2/analysis/`, figures in `v2/figures/phase1/`, report `v2/phase1/REPORT.md` | MacBook, after `/study-sync` | the report regenerates byte-identical from the data |
| **S5** | **The freeze.** Draft `v2/PROTOCOL-v2.md`: every hypothesis with its refutation condition, the analysis plan, phase 2's flags from phase 1, phase 3's rules. Open the freeze PR (`REVIEW-PR.md`) | MacBook | **JC merges the PR** (that is the freeze), tags `study2/protocol-frozen`, adds zhen's root line |
| **S6** | **Pilot.** One block of every phase 2 condition | Runner · `/study-run pilot` | ARP visible **on the wire** for the root zhen condition, read from the capture |
| **S7** | **Phase 2 collection,** `config.json` → `phase2.blocks_per_cell` per cell, shuffled, dispersion randomised across blocks | Runner · `/study-run phase2` | every cell complete, or the shortfall recorded |
| **S8** | **History priming:** zhen default on the home network, a few scans per night inside the window, for `home.priming_nights` nights. Queued alongside S7; the runner keeps them from overlapping | Runner · `/study-run priming` | that many nights of history |
| **S9** | **Phase 3 collection:** `home.blocks` blocks spread across the night slots, conditions per `PLAN.md`, Wi-Fi channel load as a covariate. Raw data stays in the private folder | Runner · `/study-run phase3` | blocks complete; nothing naming a household device in git |
| **S10** | **Analysis.** Exactly `PROTOCOL-v2.md`'s plan, then anything exploratory, labelled as such. `v2/RESULTS.md`, figures in `v2/figures/` | MacBook, after `/study-sync` | regenerates byte-identical |
| **S11** | **The paper,** in `paper/`, for both studies. Study 1's results stay; rewrite the system and method sections; add study 2's results and the home-network arm; extend threats to validity. Figure-led, low word count. Open the final PR (`REVIEW-PR.md`) | MacBook | **JC merges**; removes the grants and the runner (commands in the PR) |

## Rules for every MacBook session

- Read `RUN.md`, this file, `PLAN.md`, `config.json`, and study 1's `PROTOCOL.md`, `HARNESS.md`,
  `REPRODUCIBILITY.md` and `DEFERRED-DEFECTS.md` before changing anything.
- Reach the mini only through `Mini/scripts/mini`, and follow `Mini/AGENTS.md`.
- Ledger entry per gate or decision, in this form:
  ```
  ## 2026-11-19 · S2 · gate passed
  What: …  ·  Evidence: path, commit abc1234  ·  Decision (if any): … because …
  ```
- Commit on the MacBook. Push when JC says so.

## Never

- Change zhen-core, or rebuild or replace the installed binary.
- Edit study 1's evidence (`data/`, `figures/`, `RESULTS.md`, `PROTOCOL.md`) or study 2 evidence once written.
  A wrong record is corrected by a new record that says so.
- Queue a home job by any route but the runner, or scan any network from the MacBook.
- Copy anything from the mini's private folder, or commit anything naming a household device, address or MAC.
- Put a token, password or Claude on the mini.

## Decisions already made — do not reopen

- The default waits per address at the 97th percentile of response times; phase 1 may move the percentile and the
  1.5 s first-scan wait **as flags** for phase 2. Product defaults move in a release after the study.
- No rebuild for a missing field: record a defect in `DEFERRED-DEFECTS.md`.
- Paper 1 is held; one paper covers both studies.
- Phase 3 recall is against the union of every condition's finds plus the capture, labelled pseudo-ground truth.
