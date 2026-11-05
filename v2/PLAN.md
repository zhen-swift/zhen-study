# Study 2 — the plan

**Revised 2026-10-14.** The 2026-09-29 version is in git history; it planned one collection at study 1's
shape with dispersion added. This revision follows a change to the system under test and three rulings by JC.
`PROTOCOL-v2.md` comes after phase 1 and is the thing that gets frozen.

**Run decisions, 2026-11-02:** how, where and when the study runs — the Mac mini, the unattended agent, the
home-network window, the stops — are in `RUN.md`. Where they change this plan, the change is, marked *(RUN.md)* below.

**2026-11-05:** netsanity 0.4.0 is dropped as a phase 2 condition. That binary no longer exists and cannot be rebuilt
to the same artifact. See *The bridge* below.

Study 1 is complete and is not revised by anything here.

---

## What changed since 2026-09-29

| | |
|---|---|
| **The scanner is being fixed before it is measured** | zhen-core 0.8.0 (`zhen-agents/briefs/core-0.8.0-reach.md`) replaces the network-wide learned tail with a wait per address, learned from history at the 97th percentile, and watches the neighbour table during the sweep. Study 1's mechanism stays reachable as `--reach learned --no-neighbor-watch` |
| **Root, for the window** | JC ruled: one `NOPASSWD` line naming the frozen zhen binary's exact path, added before the phase 2 pilot, removed when phase 3 ends. JC adds and removes it |
| **A home-network arm** | JC ruled: phase 3, on `10.10.20.0/24` |
| **One paper** | JC ruled: paper 1 is held and the two studies are one paper. The supervisor is told, not asked after the fact |
| **Time is not a constraint** | three phases, run in sequence, each gated on the last |

---

## The three phases

```
phase 1  calibrate   testbed     exploratory    → sets the default, frozen into the binary
   │
   ▼  freeze binary, write PROTOCOL-v2.md
phase 2  confirm     testbed     pre-registered → the result against nmap
   │
   ▼
phase 3  replicate   home LAN    pre-registered → does it hold on real devices
```

Phase 1 is a calibration set and phase 2 a test set. **The default is tuned on phase 1's data and judged on phase
2's**, which is the methodological reason for splitting them, not the schedule.

### Phase 1 — calibrate (testbed, exploratory)

Question: how recall and time depend on the wait, the dispersion, and whether history exists.

| Factor | Levels |
|---|---|
| RTT dispersion | 1×, ~5×, ~50×, ~500× (500× is study 1's manifest exactly) |
| Reach | `learned`, `fixed` 0.5 / 1 / 1.5 / 2 / 3 s, `history` at 0.90 / 0.97 / 0.99 |
| History | empty · primed (five prior scans of the same manifest) |
| Cache | flushed before **every** run |

zhen only, unprivileged. No nmap. Flush per run removes study 1's warm-arm problem — that it measured the cache —
and gives every condition a cold observation.

**Outputs, and nothing else:** the recall-against-wait curve per dispersion; whether P97 is the right percentile;
whether the 1.5 s first-scan wait should move. They become **the flags phase 2 passes**, recorded in
`PROTOCOL-v2.md`, never a rebuild. Phase 1's data never enters a hypothesis test.

### Phase 2 — confirm (testbed, pre-registered)

Conditions, all in every block, shuffled:

```
zhen        default · first scan (empty history) · root (H3) · --reach learned --no-neighbor-watch (study 1's mechanism)
nmap root   -T3 · -T4 · -T5      (+ -T2, one block in four)
nmap user   -T3 · -T4 · -T5      (+ -T2, one block in four)
```

**Matched comparison:** `nmap -sn` on an IPv4 /24 sends nothing over IPv6, so every zhen condition compared against
nmap runs with `--ipv6-window 0`. The product default (with IPv6) runs as one extra condition, reported as the
product's wall clock, not as part of the nmap comparison.

Factors: dispersion (4, randomised across blocks, never batched) × cache (flush per run, flush per block). 30 blocks
per cell.

Hypotheses, written properly with refutation conditions in `PROTOCOL-v2.md`:

| | In outline |
|---|---|
| **H1** | zhen's default is faster than every nmap template that matches its recall, cold and warm |
| **H2** | as a curve: the advantage over nmap's frontier grows with dispersion |
| **H3** | revived: zhen as root against zhen unprivileged, same block. The root run must show ARP on the wire, read from the capture, not the artifact |
| **H7** *(new)* | the default reaches recall 1.00 cold at every dispersion — the claim 0.8.0 exists to make |
| **H8** *(new)* | primed history is faster than empty history at equal recall |

H5 (split against shared budget) is retired: 0.8.0 replaces the budget split as the mechanism, and
`--reach learned --no-neighbor-watch` carries the comparison H5 was for. H6 is answered by study 1 and nmap stays a comparator, not a hypothesis.

**The bridge** *(rewritten 2026-11-05)*. The 2026-09-29 plan asked to *prove* the unprivileged path unchanged between
the two binaries. It has changed — the neighbour table re-read after the sweep, the late-reply counter,
`discovered_via` — so that gate is replaced by measurement. The 0.4.0 binary no longer exists and cannot be rebuilt to
the same artifact, so study 1's mechanism runs inside the frozen 0.8.0 as `--reach learned --no-neighbor-watch`. At
500× it runs on study 1's exact manifest, and that is where study 1 and study 2 meet. Its difference from study 1's
results covers the binary and the machine together, and the paper says so.

### Phase 3 — replicate (home LAN, pre-registered)

Question: does phase 2's ordering hold on real devices — sleeping phones, Wi-Fi power save, history built by use.

| | |
|---|---|
| Network | `10.10.20.0/24` only — the hub rule |
| Conditions | zhen default (history primed by a week of scans inside the window *(RUN.md)*), zhen root, nmap root `-T5`, nmap user `-T4` |
| Schedule | ~30 blocks, **night-only**: 00:00–06:00 `America/Los_Angeles`, three slots per night (00–02, 02–04, 04–06). The day stratum is dropped because the household window has no day; stated as a threat to validity *(RUN.md)* |
| Ground truth | no manifest exists: recall is against the **union of every condition's finds in the block plus the capture**, declared in advance as a pseudo-ground truth and labelled as one everywhere |
| Covariates | Wi-Fi channel utilisation, which study 1 collected as `not_applicable` on every run |

**Privacy, decided:** the repository is public. Committed phase 3 data carries salted hashes of MACs and addresses,
no names. Raw captures and artifacts stay in the release bundle's private counterpart and are never pushed.

---

## Zero core changes once the study starts

The binary is frozen **before phase 1** and does not change until phase 3 ends.

| Rule | Why |
|---|---|
| Phase 1 varies every constant **by flag**, never by rebuild | the brief's study contract (change 9, gate G9) makes each one a flag echoed into the artifact |
| Phase 2 runs the calibrated values **as explicit flags**; the product's defaults are not touched | a default changed mid-study would be a second binary, and "the default" would mean two things in one dataset |
| Defaults move in a release **after** the study, citing phase 1 | the product gets the calibration; the study keeps one binary |
| A field missing after the freeze is a recorded defect, not a rebuild | study 1's rule, kept: a rebuild costs every block already taken |

So the only core work left before collection is the 0.8.0 brief, ending at G9.

## Sequence

| | Work | Gate |
|---|---|---|
| 1 | zhen-core 0.8.0, tagged, **then frozen** — `frozen-binary-v2.json` written here, before phase 1 | the brief's G0–G9 |
| 2 | Testbed manifests per dispersion, each calibrated, with designed **and** achieved RTT, and the measured **cold first-contact** time (about 2× RTT, because netem delays ARP too) | four manifests inside the 10% tolerance |
| 3 | Harness port: `zhen` argv and `ZHEN_HISTORY`, schema 4 parser, history state as a factor, flush per run, thermal pause | dry run, zero validation warnings |
| 4 | **Phase 1** | curves reported; constants moved or confirmed |
| 5 | Write and freeze `PROTOCOL-v2.md`, with phase 1's values as the flags phase 2 passes | dated, before any phase 2 block |
| 6 | sudoers line (JC), pilot | ARP visible on the wire for the root condition |
| 7 | **Phase 2** | |
| 8 | **Phase 3** | |
| 9 | sudoers line removed (JC); analysis; the one paper | |

## Still open, and JC's

Nothing. Phase 3's window was chosen by JC on 2026-10-31 *(RUN.md)*.
