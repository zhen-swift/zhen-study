# Brief — study 2, unattended

| | |
|---|---|
| Runs in | `zhen-swift/zhen-study`, branch `study2` (cut from `main` at the start), on the study Mac mini as `zhenstudy` |
| Ledger | `v2/LEDGER.md` — append-only, one entry per gate and per decision |
| State | `v2/STATE` — first line is the state, the rest is why |
| Read first, whole | `v2/PLAN.md`, `v2/RUN.md`, `v2/REVIEW-PR.md`, `PROTOCOL.md`, `HARNESS.md`, `REPRODUCIBILITY.md`, `DEFERRED-DEFECTS.md` |
| Precedence | `RUN.md` for how and when; `PLAN.md` for what; study 1's documents for anything neither covers |

You are running study 2 end to end with nobody watching. JC sees your work at two review stops and in what you
push. Make every call you can make; record each in the ledger with its reason. Stop only where `RUN.md` says.

## Never

- Change zhen-core, or build, rebuild or replace a frozen binary.
- Edit study 1's evidence (`data/`, `figures/`, `RESULTS.md`, `PROTOCOL.md`), or any study 2 evidence once written.
  A wrong record is corrected by a new record that says so.
- Scan `10.10.20.0/24` outside 00:00–06:00 `America/Los_Angeles`, or on a skipped night.
- Run two scanners at once.
- Push phase 3 raw data, or anything naming a household device, address or MAC.
- Merge, push to `main`, or force-push.
- Contact JC except by stopping. Ask nothing mid-run: decide, and log the decision.
- Supply, read or work around a password. Anything needing root that the grant does not cover is a **Blocked** stop.

## Ledger entry format

```
## 2026-11-03 02:14 PST · S2 · gate passed
What: …  ·  Evidence: path/to/file, commit abc1234  ·  Decision (if any): … because …
```

Commit after every entry. Push at least every six hours and at every state change.

## Steps

Each step ends at its gate. A gate that fails is retried after the fix; three failures over three hours is
**Blocked**.

| | Step | Gate |
|---|---|---|
| **S0** | **Machine check.** Record in `mini/MACHINE.md`: macOS, model, toolchain, `sudo -n -l` output, zone, `sntp` offset, interfaces, VPN and system-extension lists, disk. Verify both binaries' sha256 against `RUN.md`; rewrite `frozen-binary-v2.json` as a new record with the mini path and host, same checksum, `supersedes` pointing at the 2026-10-17 record. Test whether a Lima `vz` VM starts from launchd with `zhenstudy` logged out; record the answer in `RUN.md` | checksums match; base root grant present; zone and NTP pass |
| **S1** | **Testbed.** Port `testbed/` to four manifests, one per dispersion (1×, ~5×, ~50×, ~500×; 500× is study 1's manifest exactly). Pin the Ubuntu image by digest. Each manifest records designed RTT, achieved RTT, and the measured cold first-contact time | four manifests inside 10% of design, re-verified after a full testbed rebuild |
| **S2** | **Harness port** (`PLAN.md` sequence, step 3): `zhen` argv and `ZHEN_HISTORY`; schema 4 parser; history state as a factor; cache flush per run; thermal pause; the clock-and-window guard from `RUN.md`; the single-scanner lock; the 0.4.0 bridge runner; `--ipv6-window 0` on every nmap-matched zhen condition. Unit tests for the guard and the parser | dry run across every condition, **zero validation warnings**; tests pass |
| **S3** | **Phase 1 collection**, under its own LaunchAgent, design from `PLAN.md` | the design's cells complete; every skipped block accounted for |
| **S4** | **Phase 1 analysis.** Recall-against-wait per dispersion; time-against-wait; primed vs empty history. Script in `v2/analysis/`, figures in `v2/figures/phase1/` (PNG and PDF), report `v2/phase1/REPORT.md` | the report regenerates byte-identical from the data |
| **S5** | **Draft `v2/PROTOCOL-v2.md`**: every hypothesis with its refutation condition, the analysis plan, phase 2's flags from phase 1, phase 3's rules (pseudo-ground truth, night slots, privacy). Open the **freeze PR** per `REVIEW-PR.md` | PR open → `STATE` = `WAITING_FREEZE` + PR number. **Stop.** |
| **S6** | On `/freeze`: stamp the freeze date in `PROTOCOL-v2.md`, commit, tag `study2/protocol-frozen`, push. `STATE` = `WAITING_ROOT` | tag pushed. **Exit**; the wrapper resumes when the grant is present |
| **S7** | **Pilot.** One block of every phase 2 condition | ARP visible **on the wire** for the root zhen condition, read from the capture |
| **S8** | **Phase 2 collection.** 30 blocks per cell, shuffled, dispersion randomised across blocks | every cell at 30, or the shortfall recorded |
| **S9** | **History priming**, overlapping the last seven nights of S8 under the lock: zhen default on the home network, a few scans per night inside the window, history kept | seven nights of history in `ZHEN_HISTORY` |
| **S10** | **Phase 3 collection.** ~30 blocks spread across the three night slots, conditions per `PLAN.md`, Wi-Fi channel load as a covariate. Raw to `~/zhen-study2-private/`; hashed data to `v2/data/` | blocks complete; no raw data in git (check `git log -p` for addresses) |
| **S11** | **Analysis.** Exactly `PROTOCOL-v2.md`'s plan, then anything exploratory, labelled as such. `v2/RESULTS.md`, figures in `v2/figures/` | regenerates byte-identical |
| **S12** | **The paper.** Branch `study2-paper` off `study2`: one paper, in `paper/`, for both studies. Study 1's results stay; rewrite the system and method sections; add study 2's results and the home-network arm; extend threats to validity. Figure-led, low word count. Build the PDF. Open the **final PR** into `main` per `REVIEW-PR.md`, with the root-removal command | PDF builds; PR open → `STATE` = `DONE`. **Stop.** |

## Decisions already made — do not reopen

- The default waits per address at the 97th percentile of response times; phase 1 may move the percentile and the
  1.5 s first-scan wait **as flags** for phase 2. Product defaults move in a release after the study.
- No rebuild for a missing field: record a defect in `DEFERRED-DEFECTS.md`.
- Paper 1 is held; one paper covers both studies.
- Phase 3 recall is against the union of every condition's finds plus the capture, labelled pseudo-ground truth.
