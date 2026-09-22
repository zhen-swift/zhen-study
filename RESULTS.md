# Results

Phase 4 of the protocol: the analysis, run exactly as section 7 fixed it in advance,
against `Study/data/runs.ndjson` — 1,580 records, schema 2, 120 complete blocks and two
partial ones, collected between 2026-09-13 18:19 and 2026-09-22 00:14 local time.

Everything here is recomputable by:

```bash
python3 Study/analysis/strata.py --check        # the stratum sidecar
python3 Study/analysis/verify.py                # REPRODUCIBILITY.md, recomputed
python3 Study/analysis/run_analysis.py          # every number below, and the figures
```

The run writes `Study/analysis/out/analysis.txt` and `out/results.json`, and the figures
to `Study/figures/measured/`. It needs `runs.ndjson`, `analysis/strata.json` and the
repository; it does not need this machine, this network, or anything outside the tree.
The one exception is `verify.py`'s artefact-existence check, which needs the raw stdout,
stderr and pcap files that are git-ignored by design and ship as a release bundle;
`--artifact-root` points it at them, and without it that row reports what it could not
find rather than failing the run.

The paper is written against this document, with a person. Nothing below is a draft of
the paper.

---

## Summary, at the level of an abstract

On a programmable /24 of ten responders spanning 1 ms to 500 ms of round-trip time,
netsanity's discovery completes in a median 0.382 s against 4.31 s for the fastest
`nmap -sn` configuration that matches its recall — an eleven-fold difference at the
frontier and larger against every other template. **H1 is not refuted, in either cache
arm.** **H2 is not refuted under the condition frozen in advance, in either arm**, but
the survival of H2 in the cold arm rests entirely on netsanity's *shared-budget*
ablation rather than on the adaptive default the paper contributes, and that is set out
in full below because it is the most contestable result in this analysis.

**Two of the four hypotheses are refuted and the paper must say so.**

**H6 is refuted, in both arms.** H6 predicted that losing root costs `nmap -sn` at least
0.25 more recall than it costs netsanity. Warm, unprivileged nmap at its best template
(`-T2`) reaches a median per-block recall of 0.90 against unprivileged netsanity's 1.00
— a gap of 0.10, less than half the pre-declared threshold. Cold, unprivileged `-T2`
reaches 1.00 against netsanity's 0.80, and the gap is *negative*. The direction of H6
holds and its magnitude does not: the difference is real and overwhelmingly significant
under McNemar (257 discordant host observations to 0, p = 2e-57, Bonferroni alpha
0.0125), and it is far below the size the protocol committed to in advance. The 2026-09-08
amendment predicted a gap near 0.75 on this testbed composition. It measured 0.10.

**H5 is refuted in the cold arm.** H5 predicted that separating the retransmission
budget from the absence-declaration budget reduces sweep time without reducing recall.
Warm it holds: the split budget is 4.4 times faster than the shared budget at identical
recall, with zero discordant host observations in 1,080. Cold it fails its own
refutation condition: the split budget's recall drops to 0.80 (n = 5) against the shared
budget's 1.00 (n = 7), which is exactly the condition the protocol named. The
2026-09-13 cache-state amendment committed the study to reporting a cold-arm refutation
in the abstract rather than in a limitations section, and this is it.

The mechanism behind both cold-arm results is a single measured fact. **netsanity's
split budget declares absence at about 370 ms, and the slowest responder on the segment
answers at 500 ms.** `THEORY.md` section 5 requires the declaration budget to exceed the
high quantile of the segment's round-trip times, and the shipped default does not. Warm,
this is invisible: the sweep attributes the same eight replies it attributes cold, and
reports eleven hosts anyway, because the kernel neighbour table — filled by the previous
run in the block and emptied by the block's flush — supplies the two it did not hear.
The warm arm, which carries 1,458 of the 1,580 runs, therefore measures netsanity's
recall through a cache the protocol's own design fills.

Two further results the study did not set out to produce. **Adaptation costs time and
buys nothing here**: netsanity's own fixed-50 ms-retransmit ablation finishes in 0.331 s
against the adaptive default's 0.382 s, with complete separation between the two samples
(Cliff's delta −1.00, p = 1.4e-38) and no detectable recall difference. And **nmap's
timing sweep collapses to one point**: of the eight `-sn` configurations, exactly one —
privileged `-T5` — is non-dominated in either arm, so the fairness that sweeping `-T2`
through `-T5` was meant to buy is not, on this testbed, doing any work.

Scope, and the abstract must carry it: one hardware model, one macOS version, one /24,
one RTT dispersion, a programmable segment with no Wi-Fi and no correlated loss, and a
cold arm of 122 runs in which no two conditions ever share a block.

---

## 1. What was measured, and whether the record holds

`analysis/verify.py` recomputes every claim in `REPRODUCIBILITY.md`'s closing table from
the NDJSON. **All twenty-six reconcile.** Nothing in the collection record failed to
reconcile with the data. On a machine that does not hold the release bundle, the
artefact-existence row reports SKIP and the other twenty-five still run.

| claim | recomputed |
|---|---|
| 1,580 records, all schema 2 | 1,580, `{2: 1580}` |
| 2 exclusions, both `host_asleep` | 2, `{host_asleep: 2}` |
| exclusion rate 0.13% against a 5% ceiling | 0.1266% (2 of 1,580) |
| partial blocks 19 and 68 | 19 and 68, the only blocks under 13 runs |
| 120 complete blocks, 30 per stratum, 10 distinct days | 120; 30 in each of four strata; 2026-09-13 to 2026-09-22 |
| 13 conditions at 120 to 122 runs | 13, range 120 to 122 |
| 1,458 warm, 122 cold | 1,458 and 122; 9.4 cold per condition, range 5 to 15 |
| one netsanity sha256 across the window | `b4220600…`, 1 distinct value |
| one nmap sha256 across the window | `b522bd2f…`, 1 distinct value |
| `git_dirty` false throughout | false on all 1,580 |
| oracles `agree`, captures `ok` | both on all 1,580; the wire summariser also `ok` on all 1,580 |
| every referenced artefact exists | 4,740 of 4,740 stdout, stderr and capture paths present |
| runs per apparatus commit | exactly the seven counts the record gives |

Two rows worth reading twice. `on_ac_power` is `true` on every one of the 1,580 records,
**including all thirty-nine runs of the three blocks that ran on battery.**
`REPRODUCIBILITY.md` already says why — `provenance.py` samples power once per block and
copies the document onto every run — and the recomputation confirms that the record
cannot show the violation and that no field in it does. The evidence is the
reproducibility document and `pmset -g log`, neither of which is a study artefact. And
`host_asleep_seconds` is above zero on 148 runs; 146 of those are between 1 ms and 75 ms,
which is clock skew between the wall and monotonic clocks rather than sleep, and the two
that exceed the harness's one-second threshold are the two exclusions.

### The stratum hole, and how it was closed

**No record stores its stratum, and no record carries a timezone or a UTC offset.**
`collect.py` assigned strata by bucketing `datetime.fromtimestamp(...).hour` with a naive
`datetime.now()` on the collection Mac. The four strata are six-hour windows, so a
six-hour shift permutes them cleanly: a reader in another timezone re-derives identical
per-stratum counts — thirty in each — with every block relabelled, overnight becoming
morning, and nothing anywhere fires. The module comment in `collect.py` says "the driver
records the offset so a reader can reconstruct the boundaries after a daylight-saving
change." It does not. Nothing written by the harness carries it.

The offset was established from artefacts, not assumed:

- `collect.log` stamps every line with a naive local `isoformat()`. Its 120 "block
  finished" lines each follow the last record of the block they close. Read as if UTC and
  subtracted from those records' `finished_at_unix`, all 120 anchors give **−21,600 s**
  with a write lag of 1.517 to 2.669 s. The total spread across the ten-day window is
  1.152 s: no drift, and no daylight-saving step inside the window.
- All seven apparatus commits the data references carry a `-0600` committer offset, and
  the collection tag `47113b8` is dated `2026-09-13 17:45:38 -0600` against the driver
  log's `2026-09-13T17:45:39  driver starting` — the same event, one second apart, from
  two artefacts that do not share a writer.

**UTC−06:00, constant for the whole window.** `analysis/strata.py` writes
`analysis/strata.json`: block id to stratum, the offset, the assignment rule, all 120
anchors, and the driver's own stratum labels for all 122 blocks. The derived map
reproduces the driver's labels with zero disagreements and reproduces its census exactly
— thirty complete blocks in each stratum, partials 19 and 68, and the same
per-stratum-per-day table the status file holds. `runs.ndjson` is untouched.

### Which apparatus each block ran under

Seven commits appear in the data, in one contiguous sweep with no interleaving:

| commit | blocks | runs | worst final-round calibration error |
|---|---|---|---|
| `47113b8` | 0–4 | 65 | 1.22% (r03) |
| `1bf4371` | 5–19 | 192 | 1.60% (r02) |
| `d286272` | 20–36 | 221 | 1.50% (r03) |
| `a77783a` | 37–68 | 413 | 1.36% (r04) |
| `5ec05e4` | 69–74 | 78 | 1.50% (r02) |
| `cde9020` | 75–120 | 598 | 1.51% (r05) |
| `6273119` | 121 | 13 | **7.00% (r01)** |

**None of them changed the measurement path.** No diff between consecutive commits
touches `Packages`, `Study/harness` or `Study/analysis`; each changes only
`Study/README.md`, `Study/REPRODUCIBILITY.md`, `Study/testbed/manifest.json` and
`Study/testbed/gate-0.4.json`. The frozen packages diff empty against
`study/binary-2026-09-12b` at all seven.

**The instrument's declared design did not move either.** Comparing the manifests field
by field across all seven rebuilds: the ten responders' addresses, hardware addresses,
roles, target round-trip times, loss percentages and open TCP ports are **identical at
every commit**, as are the composition counts, the declared web fraction and the segment.
Only the achieved column moves. There is therefore no between-block confound in what the
testbed *is*, which is the thing that would have been correlated with time and fatal.

**The rebuild with the materially worse calibration is `6273119`, and it covers block 121
alone — thirteen runs, the last overnight block.** Its worst final-round error is 7.00%
on r01, five times the worst of any other rebuild; its 1 ms pair sits at 0.930 and
0.959 ms and its 500 ms pair at 507.9 and 506.6 ms, the largest drift of the seven.
`REPRODUCIBILITY.md` explains why — the host idle-slept every one to two minutes through
the first two and a half hours of that rebuild because nothing held it awake, and the
calibration that finally converged did so under `caffeinate`.

**Ruling: block 121 stays.** Four reasons, in the order they matter. The error is inside
the 10% tolerance `PHASE0.md` gate 0.1 fixed before any data existed, and gate 0.4 was
met after it. The absolute miss is 70 microseconds on a 1 ms responder and 8 ms on a
500 ms one, and nothing in the measurement path resolves either: the fastest condition in
the study has an interquartile range of 8 ms. Every one of block 121's thirteen runs sits
inside its own condition's distribution — the most extreme is privileged `-T2` at the
94th percentile of its warm peers, and its single cold run is privileged `-T3` at recall
1.00. And removing it would take the overnight stratum from thirty complete blocks to
twenty-nine, below the protocol's own floor, on a ground the protocol does not name.
Dropping a block for a reason invented after seeing it is the move section 7 forbids, and
the tolerance that would justify dropping it was fixed in advance and is not met.

---

## 2. Every distribution, before any median

The full profile for all thirteen conditions in both arms is in
`analysis/out/analysis.txt`; Figure 2 is the picture. Four conditions need prose.

**Unprivileged `-T2` is the one whose median describes nothing.** Warm, n = 109: median
1,446 s, interquartile range 245 to 2,030 s, full range 19.5 to 2,947 s, p90/p10 = 23.5.
The density has two humps, near 250 s and near 1,900 s, but the valley between them is
97% as tall as the lower peak — this is not two clean modes, it is a distribution
continuously filled across two orders of magnitude. **It should be reported as a
distribution and never as a median**, exactly as `FINDINGS-0.6-pilot.md` predicted from
eight runs.

What separates it is in the record and it is not nmap. The wall clock rank-correlates
with `capture.wire.arp_requests` at **+0.972** across 109 warm runs (Figure 5) — the
number of ARP requests the *scanning host's kernel* emitted resolving the 244 empty
addresses, which ranges from 0 to 2,387 for the same binary, the same argv and the same
segment. It is not an apparatus fault: exit status is 0 and the parse succeeded on
every one of them, and the harness's clock agrees with nmap's own self-report to a
median of 13 ms and a worst case of 0.2 s across a run that can last 49 minutes. It is the measurement environment, shared by both tools' unprivileged conditions,
and it is not what the warm/cold label records — the pilot's "warm is not one state",
confirmed at 120 blocks.

It also carries recall with it. Unprivileged `-T2`'s recall rank-correlates with its wall
clock at +0.787 and with its TCP RST count at +0.900: the longer the kernel keeps it
waiting, the more closed-port resets it is still listening for, and the more hosts it
reports. Its 37 warm runs at recall 0.40 have a median wall clock of 217 s; its 52 at recall 1.00, 2,060 s.
**Unprivileged `-T2` does not have a recall; it has a recall as a function of how long the
scanning host's kernel made it wait.** This is the single most important caveat on H6, and
it is treated again there.

**Unprivileged `-T3`, `-T4` and `-T5` each have a small fast mode** — six to twenty runs
between 2.0 and 9.0 s against a main mode at 12 to 23 s — and the same covariate explains
it: those runs emitted 0 to 87 ARP requests instead of 500 to 770. Their recall does not
move with it: 0.40 in 107 of 107 `-T4` runs and 112 of 112 `-T5` runs, warm.

**`nmap.naming.broadcast` is tight with a long tail.** p90/p10 is 1.44 and the maximum is
6.5 times p90: four runs between 41 and 212 s against a median of 28.1 s, again tracking
ARP requests (+0.661).

**Privileged `-T3` and `-T4` are genuinely multimodal at a small scale** — a cluster of
16% of runs near 5.2 s against a main mode near 7.6 to 7.7 s — with a valley 29% to 57%
as tall as the lower peak. The separation is 2.4 s and does not touch any verdict, but
their medians should be reported with the interquartile range beside them and not alone.

Every netsanity condition is tight and single-peaked: coefficients of variation of 0.004
to 0.104, p90/p10 between 1.01 and 1.25. `ns.naming.full` at CV 0.004 is the most
reproducible measurement in the study.

---

## 3. The four hypotheses

Family of four, after the 2026-09-12 withdrawal of H3: **H1, H2, H5, H6.** Alpha 0.05,
Bonferroni-corrected alpha **0.0125**. H4 carries no test. Medians and interquartile
ranges throughout, Mann-Whitney U two-sided with Cliff's delta, bootstrap intervals at
10,000 resamples, McNemar on paired per-host outcomes.

Recall is computed against the testbed manifest's declared responder set — ten addresses,
constant on all 1,580 records — and not against what either tool returned. Every run in
the study also found `192.168.64.1`, the bridge the scanning Mac speaks through. It is a
real host and it is not a declared responder, so it is precision and not recall, and it
puts a ceiling of 10/11 = 0.909 on the precision of every condition that reports it.

**Precision is a primary metric and it inverts, for a reason that is not about
correctness.** Median precision is 0.909 for all four netsanity conditions and all four
privileged nmap templates, and 1.000 for all four unprivileged nmap templates and for
`nmap.naming.broadcast`. Nothing found a false positive in 1,578 runs: every address any
condition reported was either a declared responder or the bridge. The unprivileged
templates score higher only because they find four hosts instead of eleven and never see
the bridge at all. Reported without that sentence beside it, the precision column says
the opposite of what happened.

The two excluded runs are both `nmap.sn.unpriv.T2`, in blocks 19 and 68, both
`host_asleep` — the five-and-a-half-hour clamshell sleep of 2026-09-15 and the
three-second one of 2026-09-17. They are the only two runs this analysis drops.

### H1 — speed at matched recall

> **Claim.** For host discovery alone on a heterogeneous /24, netsanity's median
> time-to-complete is lower than `nmap -sn` at every timing template that achieves equal
> or better recall.
>
> **Refuted if** any nmap timing template matches netsanity's recall at equal or lower
> median time.

**Warm: refutation condition NOT met — not refuted.** netsanity's adaptive default runs
in a median 0.382 s (IQR 0.377–0.386, bootstrap 95% interval on the median
[0.380, 0.383], n = 115) at median recall 1.00. Four templates match that recall, all
privileged: `-T2` at 466.4 s, `-T3` at 7.68 s, `-T4` at 7.59 s and `-T5` at 4.31 s. The
fastest of them is 11.3 times slower. Every pairwise Mann-Whitney U is p ≤ 2.2e-38 with
Cliff's delta −1.000 — complete separation, no netsanity run overlapping any nmap run —
and every bootstrap interval on the median difference excludes zero by orders of
magnitude.

**Cold: refutation condition NOT met — not refuted, n = 5.** netsanity's default runs in
a median 0.422 s at median recall 0.80. Five templates match or beat that recall —
privileged `-T2`, `-T3`, `-T4`, `-T5` and unprivileged `-T2`, all at 1.00 — and the
fastest of them is privileged `-T5` at 4.32 s, ten times slower. Cliff's delta is −1.000
against each; p ranges 3.2e-4 to 7.9e-3, and against the Bonferroni alpha of 0.0125 the
privileged `-T2` comparison at p = 0.0079 is the only one that is not comfortably clear
of it.

H1 survives in both arms, and it survives *because netsanity is fast*, not because it is
complete: in the cold arm it wins on time while losing on recall, which the refutation
condition permits by construction and which a reader should be told plainly.

### H2 — the trade curve

> **Claim.** Per-host adaptive retransmission timing dominates fixed timing templates on
> a network whose round-trip times span orders of magnitude: for any nmap template, there
> exists a netsanity configuration that is both faster and at least as complete.
>
> **Refuted if** the Pareto frontier of nmap's templates contains a point netsanity does
> not match or beat.

The first thing the frontier shows is about nmap, not netsanity. **Of the eight `-sn`
configurations, exactly one is non-dominated, in both arms: privileged `-T5`**, at 4.308 s
and recall 1.00 warm (n = 110) and 4.320 s and recall 1.00 cold (n = 12). Every other
template is slower at the same or lower recall. Sweeping `-T2` through `-T5` was in the
protocol so that comparing against `-T3` alone could not be called dishonest; on this
testbed the sweep produces one competitor and seven dominated points.

**Warm: refutation condition NOT met — not refuted.** All three netsanity discovery
configurations beat privileged `-T5`: fixed-retransmit at 0.331 s, the adaptive default
at 0.382 s and the shared budget at 1.681 s, all at median recall 1.00 against 4.308 s.
The adaptive default alone beats it, so the verdict does not depend on how "a netsanity
configuration" is read. Under `THEORY.md` C5's region of interest (recall ≥ 0.95) the
answer is unchanged: the same single nmap point qualifies and the same three netsanity
points beat it.

**Cold: refutation condition NOT met — and this is the result to argue about.** The
literal condition asks whether *some* netsanity configuration is faster than privileged
`-T5` and at least as complete. One is: the **shared-budget ablation**, at 1.011 s and
recall 1.00 on n = 7, against `-T5` at 4.320 s and 1.00 on n = 12. So the pre-declared
condition is not met and H2 is not refuted as written.

But the 2026-09-13 cache-state amendment names a narrower cold-regime clause and commits
the paper to the abstract if it fires: *"If the cold arm shows a privileged nmap point at
recall 1.0 that netsanity does not match … H2 is reported as refuted in the cold regime
and the paper says so in the abstract."* Evaluated both ways:

| reading of "netsanity" | cold median recall | privileged nmap at 1.0 | clause fires |
|---|---|---|---|
| the adaptive default, `ns.disc.unpriv` | 0.80 (n = 5) | `-T2`, `-T3`, `-T4`, `-T5` | **yes** |
| any configuration in the matrix | 1.00, from the shared budget (n = 7) | as above | no |

**The judgement, stated as a judgement rather than a computation.** H2's headline sentence
attributes the domination to *per-host adaptive retransmission timing*. The configuration
that rescues H2 in the cold arm is the shared budget — the configuration that **does not
use the technique the paper contributes**, and the one H5 exists to argue against. A paper
that reports H2 as surviving the cold arm on the strength of its own null ablation is
making a claim its reader will not accept. The recommendation for the write-up is: report
the pre-declared condition as not met, in those words, and report in the same breath that
the adaptive default is beaten by privileged `-T5` in the cold arm and that the amendment's
clause therefore fires on the claim the paper is actually making. Both numbers, both
readings, and no choosing.

Either way the cold arm's resolution is five observations of the default and seven of the
shared budget, and the reader is owed that beside the verdict.

### H5 — the budget split

> **Claim.** Separating the retransmission budget from the absence-declaration budget
> reduces total sweep time without reducing recall, relative to a single shared budget.
>
> **Refuted if** recall drops, or if the reduction is within run-to-run noise.

**Warm: refutation condition NOT met — not refuted.** Split budget 0.382 s
(IQR 0.377–0.386, n = 115) against shared budget 1.681 s (IQR 1.673–1.690, n = 115): a
4.40-fold reduction, median difference −1.2986 s with a bootstrap 95% interval of
[−1.3022, −1.2966], which excludes zero by three orders of magnitude, so the reduction is
not within run-to-run noise. Recall 1.00 against 1.00, and McNemar over 108 paired blocks
and 1,080 paired host observations finds **zero discordant pairs in either direction**.
Neither disjunct fires.

**Cold: refutation condition MET — refuted, n = 5 and 7.** Split budget 0.422 s against
shared budget 1.011 s — the reduction is still there and still outside noise (median
difference −0.590 s, interval [−1.308, −0.566]) — but **recall drops, from the shared
budget's 1.00 to the split budget's 0.80**. The first disjunct of H5's refutation
condition is exactly "recall drops", and it does. Refuted.

The pre-declared McNemar cannot be run here, and the reason is structural rather than
accidental: section 7 pairs per-host outcomes *within a block*, and one flush per block
makes exactly one run per block cold, so **no two conditions are ever cold in the same
block and the cold arm contains zero within-block pairs for any pair of conditions.** The
2026-09-13 amendment reasoned about the cold arm's n and did not notice that it had also
removed the pairing. The verdict does not depend on it — "recall drops" is read off
recall — but the significance machinery the protocol specified is unavailable in the arm
where the refutation happens, and the paper has to say so. The unpaired bootstrap
interval on the median recall difference is −0.200 [−0.200, −0.200], reported as the
exploratory substitute it is.

Where the recall goes is section 4.

### H6 — the privilege gap is nmap's

> **Claim.** On a local segment, losing root costs `nmap -sn` substantially more recall
> than it costs netsanity.
>
> **Refuted if** the median per-block recall of unprivileged `nmap -sn` — at its best
> timing template — is less than **0.25 below** unprivileged netsanity's on the
> pre-declared testbed composition, or if the difference is not significant under McNemar
> after Bonferroni correction.

**Warm: refutation condition MET — refuted.** The best unprivileged template by median
per-block recall is `-T2` at **0.90** (`-T3`, `-T4` and `-T5` are all at 0.40).
Unprivileged netsanity is at 1.00. **The gap is 0.10 against a pre-declared 0.25**, so
the first disjunct fires and H6 is refuted on it alone. The unpaired bootstrap interval
on the median difference is 0.100 [0.000, 0.200] — its upper end does not reach 0.25
either. The second disjunct does not fire: McNemar over 104 paired blocks and 1,040
paired host observations gives 257 hosts found only by netsanity against 0 found only by
nmap, p = 2.1e-57, far below the Bonferroni alpha of 0.0125.

**Cold: refutation condition MET — refuted, n = 5 and 11.** Unprivileged `-T2` reaches a
median per-block recall of **1.00** against netsanity's 0.80. The gap is **−0.20** and the
first disjunct fires. The second cannot be evaluated: no within-block pairs exist in the
cold arm, for the reason given under H5.

**Why the gap is not what the amendment predicted, and it is not because the mechanism is
wrong.** `-T3`, `-T4` and `-T5` behave exactly as `FINDINGS-0.3-nmap.md` and the
2026-09-08 amendment said unprivileged nmap would: 0.40 recall in 321 of 333 warm runs,
recovering only the three web hosts and the TCP-only host, by `syn-ack`, and nothing else.
The gap against netsanity there is 0.60 and H6's threshold would have been cleared
comfortably. What defeats H6 is `-T2`, which is not a better scanner but a slower one:
the kernel's ARP retry behaviour keeps it running for a median 1,446 s warm and up to
2,947 s, and while it runs it collects TCP RSTs from closed ports on hosts that answer no
probed service, which nmap counts as up by `conn-refused`. Fifty-two of its 109 warm runs
reach recall 1.00 and thirty-seven sit at 0.40, and which one a block gets is set by the
scanning host's kernel rather than by anything about nmap or the segment.

So H6 is refuted, and the honest statement of what refuted it is: **"at its best timing
template" turned out to select a template whose recall is a function of the measurement
environment, and on this testbed that template recovers almost everything given forty
minutes.** The amendment chose 0.25 from a predicted gap near 0.75 and derived it from the
testbed composition; the composition was right and the prediction was not, because nobody
predicted that `-T2` would be allowed to run for three quarters of an hour. That is a
defect in the prediction, not in the threshold, and moving the threshold now is precisely
what the protocol forbids.

### The four verdicts

| | warm arm | cold arm |
|---|---|---|
| **H1** | not refuted (n = 115 vs 107–117) | not refuted (n = 5 vs 5–15) |
| **H2** | not refuted (adaptive default beats the frontier) | not refuted as written; the amendment's cold clause fires for the adaptive default (n = 5) |
| **H5** | not refuted (n = 115 vs 115, 1,080 paired observations) | **refuted** — recall drops 1.00 → 0.80 (n = 7 vs 5) |
| **H6** | **refuted** — gap 0.10 against 0.25 | **refuted** — gap −0.20 against 0.25 |

---

## 4. What the measurements say that the theory does not

`PROTOCOL.md`'s phase 4 gate is "no deviation from the plan, or an amendment is
recorded". Everything in this section is a measurement the plan did not ask for,
reported because the data contains it, and recorded as exploratory in section 7 below.
None of it enters the hypothesis family.

### The declaration budget is shorter than the slowest host

This is the finding the rest of the cold-arm results follow from, and it is entirely
in-record. `parse.discovery.elapsed_millis` on every netsanity run says how long the
discovery stage ran:

| condition | arm | discovery stage | median recall | n |
|---|---|---|---|---|
| fixed 50 ms retransmit | warm | 317 ms | 1.00 | 111 |
| fixed 50 ms retransmit | cold | 340 ms | 0.80 | 10 |
| adaptive, split budget | warm | 367 ms | 1.00 | 115 |
| adaptive, split budget | cold | 406 ms | 0.80 | 5 |
| full pipeline | warm | 368 ms | 1.00 | 112 |
| full pipeline | cold | 393 ms | 0.80 | 10 |
| shared budget | warm | 1,666 ms | 1.00 | 115 |
| shared budget | cold | 987 ms | 1.00 | 7 |

The segment's slowest responders are configured at 500 ms and measured between 497 and
508 ms at every rebuild. `THEORY.md` section 5 sets the requirement: `T_split ≈ ((N−h)·k·q_low)/c + t` with
**`t ≳ q_high`**. The split budget's whole discovery stage is 370 to 410 ms — shorter than
`q_high` alone, before any of the sweep. The shared budget's is 1 to 1.7 s, and it never
misses a host in 122 runs.

Every cold miss in the study is the same two addresses. Across the 25 cold runs of the
three split-budget conditions, `192.168.64.12` and `192.168.64.13` — the two 500 ms
responders — account for **every** missed host; no other address is ever missed by
netsanity in either arm.

### The warm arm measures a cache, not a sweep

`parse.discovery.replies_seen` and `hosts_found` are on every netsanity record, and they
were added to schema 2 precisely so this could be checked from the file. The adaptive
default attributes a median of **8 replies warm and 8 replies cold** — the same number —
and reports **11 hosts warm against 9 cold**. The two extra hosts warm are not something
it heard. The engine's declared capabilities are `["icmp_sweep", "neighbor_table"]`, and
`DEFERRED-DEFECTS.md` entry 5 documents that the second of those is how it reports hosts
it never probed. The block's flush empties that table; the previous run in the block
fills it.

The cleanest single piece of evidence is `ns.naming.full`'s cold runs. Those processes
live for 3.08 s — more than six times the slowest round-trip time — and the per-run
capture records **12 to 13 ICMP echo replies on the wire** during them. The discovery
stage, which closed at 393 ms, attributed 8, and the artifact reported 9 hosts in 7 of the
10 runs and 10 in two more, missing `192.168.64.12`, `.13` or both. **The replies arrived, inside the process,
inside the capture, and were not attributed.**

That contradicts `THEORY.md` section 6 directly. The enabling condition for the whole
technique is stated there as: a reply arriving after its own attempt's window has closed
is still attributed to the probe that caused it, and *"expired probes stay matchable … until
the declaration budget expires, not until its own window does."* On this segment the
declaration budget expires first, and the late replies are lost. **P2 — "recall is
invariant to the budget split, given per-transmission tokens and matchable expired
probes" — is contradicted in the cold arm**, at 0.80 against the shared budget's 1.00.
`THEORY.md` says a recall drop here "means straggler attribution is broken, not that the
technique is wrong". The measurement agrees with the first half and the paper has to carry
it.

The warm arm does not rescue this; it hides it. 1,458 of 1,580 runs are warm, and in all
of them the neighbour table supplies what the sweep missed.

### Adaptation costs time and buys nothing measurable here

The condition matrix contains netsanity's own fixed-50 ms-retransmit ablation, which keeps
the budget split and removes the per-host adaptation. No hypothesis asks for the
comparison; it is the only thing in the study that prices the mechanism the paper
contributes.

| arm | fixed 50 ms | adaptive default | median difference | Cliff's delta | p |
|---|---|---|---|---|---|
| warm | 0.331 s (n = 111) | 0.382 s (n = 115) | −50.9 ms [−52.4, −48.6] | −1.000 | 1.4e-38 |
| cold | 0.354 s (n = 10) | 0.422 s (n = 5) | −67.6 ms [−87.6, −39.1] | −1.000 | 6.7e-4 |

Complete separation: no adaptive run is faster than any fixed-retransmit run, in either
arm. Recall is indistinguishable — 1.00 against 1.00 warm, with McNemar over 105 paired
blocks and 1,050 paired host observations finding 2 host observations recovered only by the adaptive default against 0 recovered
only by the fixed ablation (p = 0.5, exact binomial), and 0.80 against 0.80 cold. **Adaptation costs 13% of the sweep warm and
16% cold, and returns nothing this testbed can measure.**

The obvious objection is the right one: this testbed holds one dispersion and constant
per-responder latency, which is the regime in which a fixed interval tuned to the segment
should do well. That is a limit on the result, and it is also a limit on the study, and
it is in section 5.

### The time-of-day stratification sampled nothing

Ten days of collection, four strata, thirty blocks each. `PROTOCOL.md` section 5 says the
strata exist so that "device sleep cycles and household network load are sampled rather
than avoided", and section 6 lists Wi-Fi contention as a confound controlled by
"time-of-day strata; passive capture records channel utilisation".

`covariates.wifi.status` is **`not_applicable` on all 1,578 admissible runs**, with the
reason `"bridge100 is not a Wi-Fi interface"`. The 2026-09-06 amendment made the
programmable segment primary; that segment is five Lima guests on a virtual bridge on the
scanning Mac. Household load, device sleep and channel utilisation cannot reach it.

The measurements agree. Taking the largest minus the smallest of a condition's four
stratum medians, warm: 1 ms for the fixed-retransmit ablation, 5 ms for the adaptive
default, 9 ms for the shared budget, 8 ms for privileged `-T5`, 38 ms for privileged
`-T4`, 0.23 s for privileged `-T3` on a median of 7.7 s, and 1.5 s for privileged `-T2`
on a median of 466 s. Only one condition shows any signal at all under
Kruskal-Wallis (exploratory; not in the family): the adaptive default at p = 0.0117,
which is a 5.4 ms spread across four medians between 0.379 and 0.385 s. Unprivileged
`-T2`'s stratum medians span 431 to 1,704 s at p = 0.57, which is the ARP covariate
again and not the clock.

**Stratification cost the study its seven-day floor and its ten-day window, and on the
primary testbed it sampled the scanning host's own state.** That is not an argument for
having skipped it — the secondary physical segment is where it would have mattered, and
this collection did not run there — but the paper cannot claim the strata controlled
household contention on this data, and the limitations section is not the right place for
it either.

### nmap's timing sweep collapses to one point

Reported above under H2 and repeated here because it is a result about the comparator
rather than about a hypothesis: one of eight `-sn` configurations is non-dominated in
either arm. On a segment of this shape, `-T3` and `-T4` are indistinguishable from each
other (7.68 and 7.59 s warm, both at recall 1.00) and both are dominated by `-T5`;
privileged `-T2` costs 466 s for nothing; and the three fast unprivileged templates sit
at recall 0.40 with nothing to distinguish them.

---

## 5. What the data will not support

**Anything about RTT dispersion, which is the central mechanism.** `THEORY.md` P1 — the
advantage is proportional to `q_high/q_low`, and vanishes on a homogeneous segment — is
the prediction H2 exists to test, and it is the prediction this collection cannot test.
The testbed holds **one dispersion, 500×**, identical at all seven apparatus commits.
Nothing in 1,580 runs varies it. `PHASE0.md` made the segment programmable precisely so
the dispersion curve could be swept; the collection swept time of day instead. A paper
that claims the advantage scales with dispersion is claiming it from `Study/sim/` and not
from this data, and it must say which.

**Anything about correlated loss.** `THEORY.md` C8 predicts H5 fails under bursty loss and
names it the regime where the technique is paid for. Nine of the ten responders carry
`loss_percent: 0.0` and the tenth carries a flat 15%; no burst process was imposed, and
burstiness was never estimated from the captures. The arm where H5 was predicted to fail
hardest is not sampled.

**The cost model.** `THEORY.md` C7 gives `T_split ≈ (⌈N·k/c⌉ − 1)·r + t` and P7 asks for
a fit. The record carries `probes_sent` (a median of 703 against `N·k` = 762) and carries
neither the concurrency `c` nor the retransmission budget `r` nor the declaration budget
`t`. The form cannot be fitted from the NDJSON.

**Three of the five secondary metrics section 4 names.** Time to first host on screen and
peak in-flight probes are not recorded on any run. Energy per scan is not in the schema,
and could not be collected as specified anyway: section 4 asks for `powermetrics` with the
laptop on battery and the screen off, and the driver refuses to start a block unless the
host is on AC. Probes per host discovered is available for netsanity only (61.7 per host
for the adaptive default, 62.5 for the shared budget, 64.1 for fixed-retransmit) because
nmap does not report it. Run-to-run set stability is computable and is reported: Jaccard
between consecutive blocks is a median 1.000 for every netsanity condition and for
privileged nmap, and **0.700 for unprivileged `-T2`**, the lowest in the study.

**H4, at all, from this file.** H4 is a capability comparison and carries no test, but its
metrics — the fraction of ground-truth hosts given a human-meaningful name, the fraction
given a model, the fraction of randomised-MAC hosts named at all — are **not in the
record.** `parse` for `ns.naming.full` carries `stages: ["discovery", "naming"]` and
`artifact_mode: "full"` and no naming output; the names are in the artifact at
`stdout_path`. Schema 2 was cut to fix exactly this class of gap for the discovery stage
and did not extend it to the naming stage. This is the one place `PROTOCOL.md` section 8's
rule — "no number in the paper may exist that cannot be recomputed from it" — is not met
by the collected file. What *can* be said from the record is a discovery comparison, not a
naming one: `ns.naming.full` finds all ten declared responders in 112 of 112 warm runs at
3.05 s, and `nmap.naming.broadcast` finds four of ten in 92 of 108 at 28.1 s.

**Anything outside one machine and one network.** One hardware model (Mac16,8, M4 Pro),
one OS build (26.6.2 / 25G83), one /24, one programmable segment, no Wi-Fi, no IPv6, no
routed topology. The physical secondary testbed on the home LAN was not used for
collection, so the external-validity arm the 2026-09-06 amendment retained is unexercised.

---

## 6. Sensitivity, resolution and the two arms

**Flagged blocks 36, 74 and 93 change nothing.** Their runs ran on battery under records
that say `on_ac_power: true`. They are admissible under the protocol's exclusion rules and
they are not removed. Running the whole analysis with and without them:

| arm | H1 | H2 | H5 | H6 |
|---|---|---|---|---|
| warm, with (n = 1,456) / without (n = 1,420) | not refuted / not refuted | not refuted / not refuted | not refuted / not refuted | refuted / refuted |
| cold, with (n = 122) / without (n = 119) | not refuted / not refuted | not refuted / not refuted | refuted / refuted | refuted / refuted |

No verdict moves. The medians barely move either: the adaptive default is 0.382 s both
ways, the shared budget 1.681 against 1.680 s, privileged `-T5` 4.308 s both ways. The one
number that moves is unprivileged `-T2`'s warm median, 1,446 s to 1,378 s — which is the
ARP covariate's spread, not the battery.

**The cold arm is small, unbalanced, and unpairable, and every number from it carries its
n.** The 2026-09-13 amendment predicted about 9.2 cold runs per condition. The realised
allocation is 9.4 on average and **5 to 15 per condition**, because the flush happens at
block start and which condition lands first is whatever the block's shuffle put there:

| condition | cold n | | condition | cold n |
|---|---|---|---|---|
| `nmap.sn.priv.T2` | 5 | | `ns.fixed.timeout` | 10 |
| `ns.disc.unpriv` | **5** | | `ns.naming.full` | 10 |
| `nmap.sn.priv.T4` | 6 | | `nmap.sn.unpriv.T2` | 11 |
| `nmap.sn.unpriv.T3` | 7 | | `nmap.sn.priv.T3` | 11 |
| `ns.budget.shared` | **7** | | `nmap.sn.priv.T5` | 12 |
| `nmap.sn.unpriv.T5` | 9 | | `nmap.naming.broadcast` | 14 |
| | | | `nmap.sn.unpriv.T4` | 15 |

The two conditions H5 turns on have the two smallest allocations in the study. Six of the
52 condition-by-stratum cells hold no cold run at all, against the amendment's predicted
4.7. And, as set out under H5, **no two conditions are ever cold in the same block**, so
the cold arm supports no paired test of any kind.

The warm arm meets the protocol's n ≥ 30 per stratum at the block level — thirty complete
blocks in each stratum — but a given condition's *warm* count per stratum is thirty minus
its cold draws plus whatever the two partial blocks contributed, which lands between 24
and 31. That is worth a sentence in the paper, because "n ≥ 30 per stratum" is stated
about blocks and read about observations.

---

## 7. Amendments recorded in this phase

Every one is exploratory, dated 2026-09-22, admitted to no hypothesis family, and reading
no threshold. No threshold was moved, no statistic was chosen after seeing which one
flattered, and no run was reclassified: the two exclusions in the file are the two
exclusions.

1. **Kruskal-Wallis across the four strata**, per condition, warm arm. The design
   stratifies by time of day and the plan names no test for whether the strata differ;
   printing four medians and leaving the reader to compare them by eye is worse than
   running the test and labelling it.
2. **A Gaussian kernel density on log10 wall clock**, to describe each condition's shape
   before its median is reported. Two automated multimodality verdicts were tried first
   and both were worse than reading the histogram — a largest-gap rule called
   unprivileged `-T2` unimodal, and a Silverman-bandwidth mode count found five modes in
   a condition whose whole spread is one second — so the density is reported and the
   shape is stated in prose against Figure 2. It decides nothing.
3. **Unpaired bootstrap intervals on recall differences in the cold arm**, because the
   pre-declared McNemar has nothing to pair there. The pre-declared test is reported
   unrunnable rather than replaced, and the substitute is labelled everywhere it appears.
4. **The adaptive default against its own fixed-retransmit ablation.** In the matrix, in
   no hypothesis, and the only measurement in the study that prices the mechanism the
   paper contributes.
5. **Jaccard set stability between consecutive blocks.** A secondary metric section 4
   names and section 7 attaches no test to; reported without one.

---

## 8. Figures

All regenerated from `data/runs.ndjson` by `analysis/figures_measured.py`, into
`Study/figures/measured/`. **None of the eight figures in `Study/figures/` was reused or
adapted; they are the simulation's and they are not measurements.**

| file | what it shows |
|---|---|
| `fig1_pareto_measured` | **Figure 1.** Speed against completeness, warm and cold, every discovery condition, with bootstrap intervals on the medians, nmap's own frontier, and n on every point. The first time this frontier has been drawn from measurements. |
| `fig2_distributions_measured` | Every distribution behind every median, one dot per run on a log axis. |
| `fig3_recall_by_cache_state` | Recall warm against cold, with the cold arm's n on every bar. |
| `fig4_declaration_budget` | The discovery stage's own elapsed time against the five round-trip times the segment imposes; and what reached the wire, what the sweep attributed, what the artifact reported. |
| `fig5_arp_versus_wall_clock` | Unprivileged nmap's wall clock against the scanning host's ARP retry count. |

---

## 9. The result a reviewer will attack first

**H2's survival in the cold arm.** The pre-declared condition asks whether *some*
netsanity configuration beats every point on nmap's frontier, and one does — the
shared-budget ablation, at 1.011 s and recall 1.00 on **seven observations**, against
privileged `-T5` at 4.320 s and 1.00 on twelve. Three things about that are attackable at
once: it rests on n = 7; it rests on the configuration the paper's own H5 argues against,
so H2 and H5 are being defended by opposite configurations in the same arm; and the
adaptive default that the paper is actually about is at recall 0.80 there and loses to
privileged `-T5` outright. A reviewer who reads H2's headline sentence — "per-host
adaptive retransmission timing dominates fixed timing templates" — and then finds that
the domination in the cold regime comes from turning the technique off will not accept
the verdict, and should not.

Two more that will draw fire, in order. **H6's threshold**: it is refuted by a template
whose recall is a function of how long the scanning host's kernel made it wait, and a
reviewer will ask whether `-T2` at forty minutes is a fair "best template" — but the
answer has to be that the protocol said "at its best timing template" before collection
and the analysis may not narrow it now. And **the warm arm's recall of 1.00**, which
1,458 of 1,580 runs produce and which the record shows is supplied by a kernel cache the
block structure fills: a reviewer who reads Figure 4 will ask what the warm arm measured,
and the answer is that it measured netsanity plus the neighbour table left by the run
before it.
