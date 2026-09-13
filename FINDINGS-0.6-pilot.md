# 0.6 — The pilot

`PHASE0.md` 0.6: three real blocks against the programmable segment, through the
collection driver rather than by hand, to measure the variance, set the cooldown from
it, and confirm the exclusion machinery by breaking a run on purpose. The first live
blocks the study has ever run, on 2026-09-12, the day unattended root arrived.

It took three attempts. The first found five apparatus defects no dry run could have
shown and then lost a block to the host going to sleep under the driver's own
assertion; it is kept as `pilot-attempt-1.ndjson`. The second, after the fixes, ran
clean and failed the gate on its third condition — three numbers it cited were not in
the record; it is `pilot.ndjson`. The third, on 2026-09-13 under a schema that carries
those numbers, is the gate, and it is `pilot-attempt-3.ndjson`: eight complete blocks,
half of them flushing the neighbour table before every run, so that the cache-state
question this document ends on is answered with measurements. All three are read by
`analysis/pilot.py`, standard-library python, which for the third attempt opens
nothing but the NDJSON.

**Both files live in the collection worktree, not in this checkout.** Collection runs
from a worktree checked out detached at the apparatus commit, the pilot ran from it, and
`data/.gitignore` ignores `pilot*.ndjson` for the same reason it ignores `runs.ndjson` —
the harness appends to it while `provenance.py` requires a clean tree. They are
published as a release artifact alongside the pcaps.

```
C=~/Dev/InfinityCastle-collection/Study/data
python3 Study/analysis/pilot.py $C/pilot-attempt-3.ndjson
python3 Study/analysis/pilot.py $C/pilot.ndjson
python3 Study/analysis/pilot.py $C/pilot-attempt-1.ndjson
```

Nothing here is evidence for a hypothesis. Three blocks is a diagnostic of the
apparatus, and the two places below where a hypothesis's refutation condition is
visibly live are written down so that collection is read with them in view, not so
that anything is concluded from them.

**Gate status: met, on the third attempt.** `PHASE0.md` 0.6 asks for three things.

- **Exclusion under 5%.** 1 of 106 records, 0.94%, and that one is in a partial block
  that never counts: the host went to clamshell sleep 27 s into block 0 and the harness
  excluded the run and stopped. Across the eight complete blocks, 104 runs, there are no
  exclusions at all — the first pilot attempt whose exclusion rate is the apparatus's own
  rather than a fault it injected.
- **Variance stable enough for usable intervals.** Eight blocks per condition. Nine of
  thirteen conditions have a coefficient of variation of 0.13 or less. Two are not noise
  but structure this pilot was built to expose: `ns.budget.shared` at 0.30 because it
  runs at 0.98 s cold and 1.69 s warm, and unprivileged `-T2` at 0.73 because its wall
  clock is the number of ARP requests the kernel emits (r = 0.988 over eight runs) and
  nothing yet identified sets that number. Both are reported as what they are. Every
  test the protocol names is resolvable at n = 30 per stratum in the arm where it is
  measured; the section on cache state says which arm that is.
- **Every number recomputable from the NDJSON alone.** For the third attempt, yes.
  `parse.discovery` and `capture.wire` carry what the second attempt read out of
  git-ignored files, `analysis/pilot.py` opens nothing else for this file, and every
  line it prints from a netsanity artifact says `[record]`. The second attempt's
  deficiency is kept below as the record of why the schema moved.

The apparatus commit is `cb30871` on every record of the eight complete blocks
(`b6b4051` on the two records of the partial one; the difference between them is the
driver waiting for AC power and an ignore rule, and the frozen packages are byte-identical
to `study/binary-2026-09-12b` at both). Binary `b4220600…`, permission `granted`,
cooldown 10.0 s, capture `ok` and oracles `agree` on all 106.

**Collection can start.** The one open design question — cache state — was put to JC
with the per-condition cost of each option measured on this attempt, and ruled on the
same day: one flush per block, as frozen. The amendment recording it, and what the
retained design leaves under-sampled, is in `PROTOCOL.md` section 12.

---

## Stage 0 first: unattended root

`sudo -n` for `/opt/homebrew/bin/nmap`, `/usr/sbin/tcpdump` and `/usr/sbin/arp` all
succeed without a prompt, from JC's installation of `launchd/netsanity-study.sudoers`
at 13:41. Recorded here because the first check after the install reported all three
refused, and that was the check's fault, not the install's: zsh does not word-split an
unquoted variable, so `sudo -n $cmd` asked sudo for a single command literally named
`/usr/sbin/arp -a`, which matches no rule. The three checks before 13:41 were genuine
refusals — the file did not exist yet.

## What the first live block could not do, and what a dry run could not have shown

Every one of these was in code that `--dry-run` had passed end to end, because a dry run
stubs exactly the parts that failed. All five are apparatus; the binary is untouched
and its hash is on every record.

1. **`run_block.py` aborted every live block, saying `oracles.py` did not exist.** It
   had existed since gate 0.4 was met on 2026-09-11. The module was built and never
   wired into the block loop, and the abort was written before it was built. The loop
   now reads the manifest once per block, starts the per-responder capture around
   every run, reads the inventory after it, and records the three-way verdict; a
   disagreement excludes the run as `oracle_disagreement`, which section 3 names.

2. **The first block's own output would have aborted the second.** `runs.ndjson`, the
   driver's log and its status file were not git-ignored, and `provenance.py` aborts a
   block on a dirty tree, modified files included. Dry runs pass `--allow-dirty`, so
   none of them saw it. Everything the harness writes while it runs is now ignored,
   and the NDJSON is force-added when collection ends.

3. **`sudo nmap -oX` writes its XML as root, and `runners.run_nmap` then rewrote that
   file as the owner.** `PermissionError` on the first privileged nmap run. The XML is
   now left where nmap put it.

4. **The nmap timeout was 600 s, and the slowest template is not the one gate 0.3
   expected.** Privileged `-T2` was extrapolated at 510 s and ran at 452 and 471 s.
   Unprivileged `-T2` was carried at 60 s, the file's own comment calling it the least
   trustworthy number in it, and ran at 1735 s. A timeout that fires on the
   comparator's slowest template excludes that condition on every block — one in
   thirteen is 7.7%, over the ceiling, in netsanity's favour. It is 3600 s now, and a
   run that reaches it is a finding.

5. **`prove_collect.py` read `complete["morning"]`**, proved the driver on the morning it
   was written, and failed in the afternoon with nothing wrong in the driver. It reads
   the total now, and passes with the oracles wired in.

## The cooldown, from a measurement

`harness/settle.py` runs each condition once exactly as a block does and leaves the
Mac-side capture open thirty seconds after the process returns instead of one, so what
arrives after the tool has gone is on the record. `data/pilot-settle.json` holds every
post-exit frame with its offset from the moment the process returned, per condition.

| condition | wall clock | frames after exit | last scan-attributable frame |
|---|---|---|---|
| `ns.disc.unpriv` | 0.41 s | 32 | +6.09 s |
| `ns.fixed.timeout` | 0.34 s | 26 | +5.96 s |
| `ns.naming.full` | 3.07 s | 20 | +4.55 s |
| `ns.budget.shared` | 0.97 s | 21 | +5.17 s (three mDNS frames at +20.19 s are the Mac's own browsing from its bridge address) |
| `nmap.sn.unpriv.T5` | 16.8 s | 2 | +1.38 s |
| `nmap.sn.unpriv.T3`, `T4`, `nmap.sn.priv.T3`, `T4`, `T5`, `nmap.naming.broadcast` | — | 0 | none |

Every tail belongs to the scanning host's kernel rather than to either tool. A
netsanity sweep sends to all 254 addresses in under half a second; the kernel then
retries ARP for the 244 that do not answer on its fixed schedule (`maxtries: 5`), and
the last retry and the last 500 ms echo reply land about six seconds after the process
has returned. nmap paces its own probes, so its tails are under 1.4 s. The one other
candidate for state carried between runs, the kernel's 20 s `host_down_time` on an
unresolved entry, was tested directly — a ping inside that window emitted an ARP
request like any other — and carries nothing.

**Cooldown: 10 s.** It clears the longest tail with margin on a schedule that is
deterministic, and costs a minute per block less than the 15 s placeholder; 15 would
have been equally defensible and the difference is two hours across collection.

**What the cooldown is for, and what it cannot do.** It exists so one run's *traffic*
cannot reach the next, and 10 s achieves that against a measured 6.1 s worst tail. It
does nothing about kernel neighbour-table state, which is not traffic and which is
what turns netsanity's recall from 0.8 to 1.0 between one run and the next — see "Two
things to carry into collection". No cooldown short enough to run 120 blocks in a week
would clear that, which is why it is a design question for the cache-state ruling and
not a number to raise here.

The first attempt at this measurement is why `settle.py` holds `caffeinate`: it did not,
idle sleep on this machine is one minute, and `time.monotonic()` on macOS is
`mach_absolute_time`, which stops while the host sleeps. It reported 1800 s of
unprivileged `-T2` spread over 63 minutes of wall clock with the Mac asleep for most of
it. That was the first sighting of what took the third block of the first attempt.

## The first attempt: three blocks, and a block lost to sleep

`data/pilot-attempt-1.ndjson`, 39 records, three complete blocks, apparatus commit
`05b0870`, binary `b4220600…` on every record, permission `granted` on every record,
Mac-side capture `ok` on every record, per-responder oracles agreeing on 38 of 39 —
the 39th being the run broken on purpose.

Block spans were 2507 s, 970 s and 8125 s. The third is the one that matters. Its
driver started at 16:10:08; the power log shows `Entering Sleep state due to 'Idle
Sleep'` at 16:10:13. The pilot ran the driver once per block with `--once`, and between
one invocation releasing its `caffeinate -i` assertion and the next taking one, the
idle timer — a minute, long expired — fired. The assertion taken five seconds later
held nothing: an assertion against idle sleep does not cancel a sleep already under
way, and does not turn a maintenance wake into a full one. The host cycled through dark
wakes for two hours and fifteen minutes while the block limped through them. Four of
its runs spanned sleep, visible as the gap between wall time and monotonic time inside
one run: 220 s, 5223 s, 257 s and 7 s. The 5223 s one is unprivileged `-T2`, scored at
1580 s by the monotonic clock while nmap's own wall-clock timers ran the whole time. A
fifth run, `ns.naming.full`, started at 16:14:34 inside a dark wake, got no answer to
mDNS, SSDP or NetBIOS, and exited 69 as netsanity documents for that case.

Counted honestly — the four sleep-spanning runs, that one, and the injected fault — six
of 39 runs are not usable, 15.4%, over the 5% ceiling. The gate's instruction for that
case is to fix the apparatus and pilot again, and that is what happened:

- A run in which the host slept more than a second is recorded, excluded as
  `host_asleep` (added to the schema's apparatus-failure list beside
  `capture_failure`, for the same reason those are there), and **stops the block**. A
  host that slept under the assertion will do it again, and a night of excluded runs is
  the quiet failure the alarm file exists to prevent.
- The driver takes `caffeinate -u` for five seconds before holding `-i`. Declaring a
  user active is the only thing that turns a dark wake into a full one, and it is the
  crash-restart case this protects: launchd restarting the driver five minutes after a
  crash, on a machine that has meanwhile gone to sleep.
- The second attempt ran as one long-lived driver process, which is how collection
  runs, rather than three invocations with a gap between them.

What the first attempt established that stands regardless:

**The injected fault was caught unaided.** `--inject-fault r02:3` took the 1 ms
responder's link down for the fourth run of block 0, which the shuffle made
`nmap.naming.broadcast`. The manifest and the inventory still listed `192.168.64.5` —
the namespace, address and listeners were all still there — and the per-responder
capture saw no frame reach it. `oracles.agree` reported the disagreement, the run was
excluded, and the record says both things: the pre-specified reason `injected_fault`,
and inside it *"Detected unaided as oracle_disagreement: 192.168.64.5 seen by manifest,
inventory"*. Had the run come through with no exclusion the block would have stopped
with `INJECTED FAULT NOT DETECTED`.

**The two attempts are counted the same way.** `analysis/pilot.py` applies the
`host_asleep` rule on read to the first attempt's records, which predate it, so a run
that spanned sleep is excluded in both attempts even though only the second attempt's
harness knew to record it. What the script does *not* do is read only the NDJSON, which
this document claimed until the gate was assessed and which is untrue — see "What is not
recomputable from the NDJSON".

**Privileged `-T2` is measured, and the extrapolation was pessimistic.** 471 and 452 s
to completion in the two awake blocks (368 s in the block that slept, which is not a
measurement). Ten of ten responders and the scanning host itself, every one
`arp-response`.

**Unprivileged `-T2` is the largest term in a block, by a factor of three over
privileged `-T2`, and its spread is the whole schedule's spread.** 1735 s and 228 s in
the two awake blocks. Both captures show SYN frames reaching only the ten real
addresses — the kernel never emits a SYN it cannot resolve — and the difference is in
ARP: 1679 requests against 507, the kernel exhausting five to ten retries per empty
address in the slow run and giving up after one to three in the fast one. That is
scanning-host kernel state left by earlier runs in the block, which is what the
protocol's warm-versus-cold labelling exists to capture, and it also changes what nmap
reports: the slow run recorded five hosts as up by `conn-refused`, a TCP RST from a
closed port — three ICMP-only responders, the "silent" one whose TCP stack answers even
though it drops ICMP, and one ICMP+web host caught on its closed second port — and the
fast run recorded none of them. The captures show seven responders sending RSTs in both
runs, so nothing about the segment changed; what changed is whether nmap was still
listening when they arrived. Recall 0.8 against 0.4, same command, same segment, an hour
apart. (An earlier draft of this paragraph said six, and said all six were ICMP-only.
Both were wrong, and both came from reading the wrong one of the three runs — the six is
the sleep-excluded run's count.)

## What that does to the schedule

A block flushed once is anywhere from 15 to 46 minutes, and the whole of that range is
unprivileged `-T2`: 220 s to 2546 s across the pilot's eleven admissible runs of it,
against privileged `-T2` at a steady eight minutes and everything else under half a
minute, plus thirteen cooldowns and 65 s of capture and oracle overhead per block.
`conditions.estimated_block_seconds(10)` says 2504 s from the second attempt's
numbers, using the largest observed `-T2` rather than the median, because that
estimate is what the driver uses to decide whether a block can still start before a
stratum's window closes — and the third attempt's cold `-T2` at 2546 s says it should
be re-derived from the larger figure before collection. The seven blocks flushed once
across the second and third attempts spanned 916 to 2748 s, mean 1839 s.

Five blocks per stratum per day — the cap the driver derives as `ceil(30/7) + 1` — is
at most 3.8 hours of each six-hour window at the worst block seen. 120 blocks is about
61 hours of machine time at the mean, 92 at the worst, in a 168-hour window. It fits.
What does not fit is a prediction of any one block's length: a stratum whose fifth
block cannot start in time takes four that day and the window stretches to eight days,
which the floor allows, and whether that happens is set by whatever sets `-T2`'s ARP
retry count, which is not yet known.

## What the variance says about the block count

Every figure in this section is from `pilot-attempt-3.ndjson`, eight complete blocks,
except where it names an earlier attempt. Earlier drafts of this section reported the
first attempt's spread as the pilot's, and then the second's; each was superseded by the
next attempt and the numbers below are the third's.

Eight blocks pin sigma to roughly a factor of two, and the point of running them was to
find out which conditions are tight and which are not. The netsanity discovery
conditions — `ns.disc.unpriv`, `ns.fixed.timeout`, `ns.naming.full` — have coefficients
of variation of 0.01 to 0.04, so n = 30 per stratum gives intervals on their medians of
2% or better. `ns.budget.shared` is at 0.30, and that is not noise: it runs at 0.98 s
cold and 1.69 s warm, with each mode tight, and it is reported by cache state rather
than as one median. Privileged nmap sits at 0.03 to 0.13. Unprivileged `-T3` to `-T5`
sit at 0.09 to 0.42, which at n = 30 is ±4% to ±19% on the median and, pooled across
strata, half that.

Unprivileged `-T2` is the outlier at 0.73 — 220 s to 2546 s across eight runs — and no
block count in this design gives a tight interval on its median: 226 blocks for ±25%
against a sigma at the top of its interval. Its result will be reported as a
distribution rather than a median. What this attempt added is that the distribution has
a mechanism and not yet a cause: across all eight runs the wall clock is the count of
ARP requests the scanning host's kernel emitted, r = 0.988, from 512 requests at 220 s
to 2239 at 2546 s. The kernel is resolving the 244 empty addresses, and how many times
it retries each one is what the run costs. What sets the retry count is not the flush
(cold runs took 463 s and 2546 s), not which condition ran before, and not — as the
second attempt's three runs suggested and this attempt's eight refute — how recently a
netsanity sweep ran. It is unknown, it is recorded per run in `capture.wire`, and it is
the first thing collection's data should be asked.

For the hypothesis tests none of the timing is close. H1 and H2 are rank comparisons
and the distributions do not overlap: every netsanity discovery run in the pilot
finished inside 0.42 s and every nmap run took at least 2.0 s. H5 compares
`ns.budget.shared` against `ns.disc.unpriv` — 1.69 s against 0.38 s warm, 0.98 s
against 0.40 s cold — with no overlap in either arm. H6 is a recall comparison, McNemar
on paired per-host outcomes, and its resolution is set by the number of hosts times
blocks rather than by timing variance.

Section 7's n ≥ 30 per stratum is adequate for every test the protocol names **in the
warm arm**, which is where 110.8 of the 120 blocks' runs per condition land as the
design stands. Where it is thin on recall is the cold arm, at 2.3 runs per condition per
stratum, and that is not a variance problem with a bigger n as its answer — it is the
design question the cache-state section puts to JC.

## Two things to carry into collection, written plainly

**The gate 0.3 defeat is a cold-cache result, and it is deterministic.** Gate 0.3 found
netsanity missing both 500 ms responders with a discovery stage shorter than their round
trip. The first two attempts reproduced it once, because one flush per thirteen
conditions gave netsanity's adaptive default no cold run at all. The third attempt
flushed before every run in four of its eight blocks, and the answer is not
statistical: **every cold run of `ns.disc.unpriv`, `ns.fixed.timeout` and
`ns.naming.full` — fourteen of fourteen, one of them the admissible run in the partial
block 0 — reported nine hosts and missed exactly
`192.168.64.12` and `.13`, the two 500 ms responders. Every warm run of the same three
conditions — eleven of eleven — reported all ten.** Recall 0.8 cold, 1.0 warm, on the
same binary, the same segment, minutes apart. The wall clock does not move: 0.40 s cold
against 0.38 s warm. The record shows the mechanism per run: cold, `replies_seen` is 8
or 9 and `hosts_found` is 9; warm, `replies_seen` is still 7 to 9 and `hosts_found` is
11, the rest read from the neighbour table that the run before had provoked into holding
the 500 ms hosts' ARP replies.

`ns.budget.shared` is the exception and it is the one that matters for H5. Cold it ran
at 0.98 s and found all ten in four of five runs (0.90 in the fifth, missing `.13`);
warm it ran at 1.69 s and found all ten. The shared-budget ablation is *faster cold than
warm* and *more complete cold than the split-budget default*.

So **H5's answer depends on which arm it is asked in.** H5 says the split budget reduces
sweep time without reducing recall, relative to the shared budget. Warm: 0.38 s against
1.69 s, recall 1.0 against 1.0 — holds. Cold: 0.40 s against 0.98 s, recall 0.8 against
0.98 — the time reduction is there and the recall is not, which is H5's refutation
condition. Three blocks of each is a diagnostic and not a result, but it is a diagnostic
that says the arm the study analyses decides the answer, and the design as it stands
puts 110.8 of every 120 runs in the arm where H5 holds.

H2's refutation condition — a privileged nmap point at recall 1.0 that netsanity does
not match — is therefore live in the cold arm and not the warm one, and privileged nmap
is at 1.00 on all 32 admissible runs of this attempt, cold and warm alike. The harness
stamped every run in a block `cold` until the second attempt; it now labels by position
and by policy, and the analysis should read cold as `sequence_index == 0` in any record
from before commit `30584fc`. Nothing was tuned, and nothing should be.

**H6's refutation condition fires on this attempt too, and by a wider margin.** H6 is
refuted if the median per-block recall of unprivileged nmap, at its best timing
template, is less than 0.25 below unprivileged netsanity's. Unprivileged `-T3`, `-T4`
and `-T5` sit at 0.4 in every one of 24 runs — the three web hosts and the TCP-only
host, by `syn-ack`. Unprivileged `-T2` is the best template and across eight blocks it
scored 1.0, 0.8, 1.0, 0.4, 0.4, 0.4, 0.8, 1.0: median **0.8**. Against warm netsanity at
1.0 the gap is 0.2; against cold netsanity at 0.8 it is **0.0**. Every run at 0.8 or
above found its extra hosts by `conn-refused` — a closed port answering a connect probe
with a RST that nmap counts — and every run at 0.4 found none that way, though
`capture.wire` shows the same seven responders sending RSTs in all eight runs. The
difference between 0.4 and 1.0 on the same command is whether nmap was still listening
when the RSTs arrived, and that tracks the same ARP-request count that sets its wall
clock. The amendment of 2026-09-08 predicted a gap near 0.75. Whether the median gap
stays under 0.25 across 120 blocks is collection's question, and nothing in the
apparatus should be touched to change the answer.

## The second attempt

`data/pilot.ndjson`, 39 records, three complete blocks and no partial one, apparatus
commit `30584fc`, binary `b4220600…` on every record, permission `granted` on every
record, Mac-side capture `ok` on all 39, cooldown 10.0 s on all 39, cache states `cold`
and `warm` both present for the first time. It ran on 2026-09-12 from 18:33 to 20:20,
as one long-lived driver process rather than three invocations, which is how collection
runs and which is the fix for what took the first attempt's third block.

**Exclusion: 1 of 39, 2.56%.** The one exclusion is the fault injected on purpose. No
run was excluded for a reason the apparatus did not choose — no `host_asleep`, no
`capture_failure`, no `nonzero_exit`, no unbidden `oracle_disagreement`. Against the
first attempt's 6 of 39 at 15.38%, every one of the four apparatus-caused exclusions is
gone, and the two fixes that did it are the ones the first attempt named: the host may
not sleep under the assertion, and a run that sleeps anyway stops the block.

**The injected fault was caught unaided again, on a different condition.**
`--inject-fault r02:3` took the 1 ms responder's link down for the fourth run of block
0, which this block's shuffle made `nmap.sn.priv.T3` rather than the first attempt's
`nmap.naming.broadcast`. The manifest and the inventory still listed `192.168.64.5`;
the per-responder capture saw no frame reach it; `oracles.agree` reported the
disagreement; the run was excluded carrying both the pre-specified reason
`injected_fault` and the unaided detection, *"Detected unaided as oracle_disagreement"*.
The first attempt had already proved this and it was not re-run to prove it again — it
is in the second attempt because the driver injects the fault on block 0 regardless, and
it is worth recording that the detection did not depend on which condition drew the
broken run.

**The schedule, measured.** Block cost — tool wall clock plus cooldowns — was 2503,
2544 and 1171 s; block span, which adds the capture and oracle overhead a block actually
pays, was 2559, 2599 and 1226 s, so that overhead is 65 s a block. The median span of
2559 s was, until the third attempt, the number the schedule used;
`conditions.estimated_block_seconds(10)` says 2504 s, which is the cost and not the
span. Privileged `-T2` ran to completion
three times at 466, 376 and 469 s, confirming the first attempt's 471 and 452 and
putting gate 0.3's 510 s extrapolation to rest as pessimistic. Unprivileged `-T2` ran
1809, 1938 and 462 s and is still the largest term in a block by a factor of four over
privileged `-T2`.

**The 1171 s block is the one to read twice.** It is not a faster machine or a quieter
network; it is the block in which unprivileged `-T2` took 462 s instead of 1800-odd, and
that single run is the whole difference. Its capture holds 954 ARP requests against 1777
and 1412 in the two slow runs, and its `conn-refused` count is zero against six and
seven.

What seemed to order those runs, on the five admissible unprivileged `-T2` runs the
first two attempts had, was **how long since a netsanity sweep last ran**. The gap
between the end of the last netsanity run in the block and the start of `-T2` sorted
them exactly:

| gap since the last netsanity run | unprivileged `-T2` |
|---|---|
| 15 s | 462 s |
| 35 s | 228 s |
| 76 s | 1735 s |
| 101 s | 1809 s |
| 407 s | 1938 s |

**The third attempt refuted it.** Its eight `-T2` runs include a 220 s run 663 s after
the last netsanity sweep, a 463 s run with no netsanity sweep before it in the block at
all, and a 2007 s run 58 s after one. The table above is five points that happened to
sort, and it is left in place as the record of an inference this document made and the
next attempt took away. What survives is narrower and better supported: the wall clock
*is* the ARP request count, r = 0.988 across the third attempt's eight runs, and what
sets that count is not identified. See "What the variance says".

What is still true, and is why the cache-state ruling below exists: **"warm" is not one
state.** Whatever sets the kernel's retry behaviour, it is not reset by the block's
flush and it is not the 10 s cooldown's business — the cooldown was set from a traffic
tail that is genuinely short, and the state that matters here is not traffic.

## What the second attempt could not recompute from the NDJSON, and why that failed the gate

`HARNESS.md` states the rule the whole apparatus is built around: collection produces
raw evidence, analysis produces numbers, and they meet only at an append-only NDJSON
file. `PHASE0.md` 0.6 turns it into a gate condition — every number in the pilot
recomputable from the NDJSON alone. Three quantities this document cited from the
second attempt were not, and all three were found by checking the claim rather than by
anything going wrong. The third attempt's records carry all three; this section is kept
as the reason the schema moved.

| what | where it actually comes from | what it is cited for |
|---|---|---|
| `replies_seen` and `hosts_found` per netsanity run | the netsanity artifact at `stdout_path`, opened by `analysis/pilot.py` itself | the neighbour-table mechanism — that warm netsanity reports ten while hearing seven to nine |
| ARP requests per run (1679 against 507; 1777, 1412, 954) | `tcpdump -r` over the per-run pcap, by hand | why unprivileged `-T2` has two modes |
| RSTs per responder per run | `tcpdump -r` over the per-run pcap, by hand | that nmap's recall difference is listening time, not the segment |

The pcaps and the raw artifacts are git-ignored by design — a capture is of a network
that no longer exists in that state — and ship as a release artifact. So a reviewer who
has the NDJSON and the analysis can recompute every timing, recall, exclusion and
schedule number in this document, and cannot recompute the three above. That is the gate
condition, not a technicality about it.

It mattered beyond tidiness because those three are exactly the numbers carrying the
cache-state mechanism, which is the question the next section puts to JC. The evidence
for the most consequential open decision in the study was the evidence a reviewer could
not check from the file the protocol says is the record.

**What fixes it, done on 2026-09-13 at `f9e2d6c` — schema 2:**

1. **The discovery stage's reply count is in the record.** `runners.py` copies
   `replies_seen`, `hosts_found`, `probes_sent` and `elapsed_millis` from the artifact's
   discovery stage into `parse.discovery`, and the engine's capability list into
   `parse.engine_capabilities`, beside the `engine_kind` it already copied.
2. **The Mac-side capture counts what the pilot counted by hand.** `capture.py` runs
   the same `tcpdump -r` over the finished pcap — seven filters, about 25 ms on the
   largest capture the pilot produced — and writes ARP request and reply counts, ICMP
   echo counts, TCP SYN, SYN-ACK and RST counts, and per-source tallies of the replies
   into `capture.wire`. Checked against the by-hand numbers: the 462 s run's pcap
   summarises to 954 ARP requests and RSTs from exactly the seven responders read off
   it by hand.
3. **The validator reads version 1 as version 1.** Both pilot attempts stay readable and
   a file still may not mix versions. `analysis/pilot.py` uses `parse.discovery` when a
   record carries it and opens the artifact when it does not, and every line it prints
   from an artifact says so.
4. **Then pilot again under the repaired schema**, because the gate is about the pilot
   and a repaired apparatus that has not been piloted is what 0.5 was. Proven dry first:
   26 schema-2 records across both flush policies with zero validation problems, and
   `prove_collect.py` still met. Then run: the third attempt, below.

None of this touches `Packages/netsanity-core` or `netsanity-cli`, and none of it is a
reason to rebuild the binary. The frozen packages are byte-identical to
`study/binary-2026-09-12b` at `30584fc` and again at `f9e2d6c`, checked each time the
collection worktree moved, and the binary in it still hashes `b4220600…`.

**What this did not excuse.** Nothing above changed a measured number in the second
attempt. Its exclusion was 2.56%, its variance is what its table says, and the injected
fault was caught unaided twice. That attempt did not meet the gate because the gate asks
for something more than that, and the honest reading is that the third condition was
written to prevent exactly the situation this document was in — citing pcap numbers in a
findings document while claiming the NDJSON held everything.

## Cache state: four numbers, measured, and a decision that is not the agent's to take

`PROTOCOL.md` section 5 says cache state is a condition and not an accident, that each
block begins with a cache flush, and that warm versus cold is recorded and analysed
separately. Section 5 also says n ≥ 30 blocks per stratum. As built, those two sentences
do not hold together, and the first two attempts made it visible: six cold runs in 78,
on six conditions, seven conditions never observed cold. The third attempt was designed
so this section could be written from measurements. Its four flush-per-run blocks give
every condition four or five cold runs against three or four warm ones from the same
day, and every number below that is a cost or a recall is from
`pilot-attempt-3.ndjson`.

**What cold costs, per condition, measured.** Wall clock is the median; recall is the
mean against the oracle-agreed set.

| condition | cold n | cold s | cold recall | warm n | warm s | warm recall | cold / warm |
|---|---|---|---|---|---|---|---|
| `nmap.sn.priv.T2` | 4 | 467.3 | 1.00 | 4 | 474.3 | 1.00 | 0.99x |
| `nmap.sn.priv.T3` | 4 | 7.76 | 1.00 | 4 | 7.63 | 1.00 | 1.02x |
| `nmap.sn.priv.T4` | 5 | 7.67 | 1.00 | 3 | 7.69 | 1.00 | 1.00x |
| `nmap.sn.priv.T5` | 4 | 4.23 | 1.00 | 4 | 4.14 | 1.00 | 1.02x |
| `nmap.naming.broadcast` | 4 | 30.2 | 0.40 | 4 | 29.8 | 0.40 | 1.01x |
| `nmap.sn.unpriv.T3` | 4 | 22.8 | 0.40 | 4 | 18.6 | 0.40 | 1.23x |
| `nmap.sn.unpriv.T4` | 5 | 22.8 | 0.40 | 3 | 19.4 | 0.40 | 1.18x |
| `nmap.sn.unpriv.T5` | 4 | 16.3 | 0.40 | 4 | 10.4 | 0.40 | 1.57x |
| `nmap.sn.unpriv.T2` | 4 | 1985 | 0.80 | 4 | 651 | 0.65 | 3.05x |
| `ns.disc.unpriv` | 5 | 0.399 | **0.80** | 4 | 0.377 | 1.00 | 1.06x |
| `ns.fixed.timeout` | 5 | 0.352 | **0.80** | 3 | 0.323 | 1.00 | 1.09x |
| `ns.naming.full` | 4 | 3.08 | **0.80** | 4 | 3.06 | 1.00 | 1.01x |
| `ns.budget.shared` | 5 | **0.976** | 0.98 | 3 | 1.687 | 1.00 | **0.58x** |

Three things in that table, in the order they matter:

1. **Privileged nmap does not care.** Four conditions, 1.00 recall in both arms, wall
   clock within 2%. ARP does not care about round-trip time and the neighbour table does
   not enter into it.
2. **netsanity's adaptive default and its fixed-timeout ablation lose exactly the two
   500 ms hosts, every cold run, and gain nothing warm but the table.** Recall 0.8 cold
   against 1.0 warm on every one of the three discovery-bearing conditions, timing
   unchanged. The shared-budget ablation goes the other way: faster cold and nearly
   complete cold.
3. **Unprivileged nmap is the only tool whose wall clock moves with cache state, and the
   flush is not what moves it.** `-T3` to `-T5` run 1.2 to 1.6 times slower cold. `-T2`
   is 3x slower on the median, but its cold runs were 463, 1505, 2465 and 2546 s and its
   warm ones 220, 244, 1058 and 2007 s, so the policy shifts the distribution without
   deciding it.

**The four numbers, with K = 13 live conditions and B = 30 blocks per stratum.**

*The design as it stands.* One flush per block, so one cold run in thirteen.

- Cold: **2.3** per condition per stratum, **9.2** pooled across the four strata.
- Warm: **27.7** per condition per stratum, **110.8** pooled.
- A given condition never lands cold in a 30-block stratum with probability 0.091, so of
  the 52 condition-by-stratum cells about **4.7 hold no cold run at all**.
- Block span: the seven blocks run this way across the second and third attempts span
  916 to 2748 s, mean 1839 s. 120 blocks is **61 machine hours** at the mean, 92 at the
  worst block seen, inside the 168-hour window; five a day is 3.8 hours of a six-hour
  window at the worst block seen.

*Flushing before every run in half the blocks, still 120 blocks.*

- Cold: **16.2** per condition per stratum, **64.6** pooled.
- Warm: **13.8** per condition per stratum, **55.4** pooled.
- Against n ≥ 30 per stratum, **neither arm reaches it.** Both clear 30 only pooled
  across strata, which is what stratification exists to prevent.
- Cost: the flush itself is 0.040 s. The four flush-per-run blocks spanned 1247 to
  3230 s, mean **2494 s** — **655 s a block more than the mean of a flushed-once block,
  36%**, almost all of it unprivileged `-T2`. Sixty blocks each way is **72 machine
  hours**, eleven more than the design as it stands, and the seven-day floor holds: five
  flush-per-run blocks a day at the worst span seen is 4.5 hours of a six-hour window.
  The 2.5% this document carried before the third attempt, from one inferred number, was
  wrong by an order of magnitude and is withdrawn.

*Keeping both arms at n = 30 per stratum.* Warm needs 32.5 unflushed blocks, cold needs
27.5 flushed: **60 blocks per stratum, 240 blocks, 46% flushed per run.**

- **143 machine hours** at the measured means (110 flush-per-run blocks at 2494 s plus
  130 flushed-once at 1839 s), against 61 as it stands.
- The floor moves, and to neither of the numbers the question offered:

| blocks/day/stratum | days | worst window use (cap × 3230 s) | machine h/day at means |
|---|---|---|---|
| 5 (the current cap) | **12** | 4.5 h of 6 | 11.9 |
| 6 | **10** | 5.4 h of 6 | 14.3 |
| 7 | 9 | 6.3 h of 6 — does not fit | 16.6 |

  At the cap the driver derives today, `ceil(30/7) + 1 = 5`, the seven-day floor
  becomes **twelve days**. Ten days is available at six a day, which is a change to
  `daily_quota` and itself an amendment. Nine is not available: seven flush-per-run
  blocks at the worst span seen overrun a six-hour window.

*Does any option make H1, H2, H5 or H6 untestable?* **No — and each of them answers
differently by arm, which is the trap.**

- **H1** survives every option. netsanity discovery inside 0.42 s against nmap's 2.0 s
  minimum, in both arms.
- **H2** is testable under every option and *decided* differently. Its refutation is a
  privileged nmap point at recall 1.0 that netsanity does not match. Privileged nmap is
  at 1.00 in both arms; netsanity's default is at 1.0 warm and 0.8 cold. As built, the
  cold arm carries 9.2 points per condition; under flush-per-run, 64.6.
- **H5** — the split budget reduces sweep time without reducing recall — **holds warm
  and fails cold on this attempt's data.** Warm: 0.38 s against 1.69 s at 1.0 against
  1.0. Cold: 0.40 s against 0.98 s at 0.80 against 0.98. Its refutation condition is
  live in the arm the design as it stands samples 2.3 times per stratum.
- **H6** is testable under every option and its refutation condition fires in both arms
  here: unprivileged `-T2`'s median per-block recall is 0.8, against warm netsanity at
  1.0 (gap 0.2) and cold netsanity at 0.8 (gap 0.0), both inside 0.25.

Every option that strengthens the cold arm makes H2, H5 and H6 harder for netsanity to
pass, and the party choosing between them wrote netsanity. `PROTOCOL.md` section 9
declares that conflict of interest and says the falsification conditions are what make
the declaration mean something; an amendment chosen by the author, after seeing which
way the pilot leaned — and it leaned, in every arm this attempt measured — is the
amendment a reviewer reads hardest and should.

**No design is chosen here.** The options above went to JC with their measured costs
on 2026-09-13, after the third attempt, and **he ruled: one flush per block, the design
as it stands.** The amendment is in `PROTOCOL.md` section 12 under that date. It says
what prompted the choice, that the cheapest and least refutable option was the one
taken and by whom, and — so a reviewer can hold the paper to it — that the cold arm is
analysed pooled across strata at about nine runs per condition, that H2's and H5's
refutation conditions live there, and that a refutation at that resolution is reported
in the abstract. It was decided before any collection block was run; the only blocks
that exist are this pilot's.

Two things follow for the apparatus and were done the same day.
`conditions.estimated_block_seconds` is re-derived from the largest run this attempt
saw, 2546 s, so the driver refuses a start that cannot finish inside its window; at a
10 s cooldown the estimate is 3352 s, and five blocks a day is 4.7 hours of a six-hour
window. And `--flush-policy` stays at `block`, which the driver logs as the design and
anything else as not.

## The third attempt

Run on 2026-09-13, 10:27 to 15:42, from the collection worktree, through the driver,
under schema 2. `pilot-attempt-3.ndjson`, 106 records: eight complete blocks (ids 1 to
8) and one partial (id 0). Two purposes, one design: gate 0.6 under the repaired
schema, and the cache-state options priced with `--flush-policy alternate`, which gave
odd block ids a flush before every run and even ones the protocol's single flush — four
of each.

Not repeated: the injected fault. Attempts one and two both caught it unaided, on two
different conditions, and a third would be manufacturing an exclusion to admire. This
attempt's exclusion rate is therefore the apparatus's own, and across the eight complete
blocks it is zero.

**Block 0 was lost to the lid.** It started at 10:27:01 on battery at 28%; the power
log shows `Entering Sleep state due to 'Clamshell Sleep'` at 10:27:28. `caffeinate -i`
cannot hold a closed MacBook awake on battery — no assertion can — and the host slept
521 s inside the second run. The harness excluded that run as `host_asleep`, stopped the
block and wrote the alarm, exactly as `30584fc` built it to. The two records stay in the
file, one admissible and one excluded, under apparatus commit `b6b4051`; the block is
partial and no census counts it.

Two apparatus changes went in before the restart, both at `cb30871`, which every record
of blocks 1 to 8 carries:

- **The driver waits for AC.** Section 6 lists the plugged-in state as a control that is
  *fixed*; `provenance.py` recorded `on_ac_power: false` on both of block 0's records,
  which is recording a violation rather than preventing one. The driver now waits, and
  logs why, until the host is on AC — waits rather than halts, because a cable that fell
  out at 03:00 is fixed by plugging it in.
- **`data/.gitignore` covers what a named attempt writes.** `run_block.py` names the raw,
  capture and store directories after the output file's stem, so this attempt wrote to
  `pilot-attempt-3-raw/` and siblings, which nothing ignored. Block 0 ran because they
  did not exist at its provenance check; block 1 would have aborted on the tree they
  dirtied. The first attempt's second defect, one name over.

The frozen packages are byte-identical to `study/binary-2026-09-12b` at both commits and
the binary hashes `b4220600…` on all 106 records.

**What was done before it ran, in order, each checked:**

| step | result |
|---|---|
| testbed, after the host lost power | all five machines restarted; `netbed.py configure` re-shaped and re-calibrated the ten responders at the same addresses and roles; worst achieved error 1.22% against 10% |
| the three oracles | three consecutive rounds, manifest 10, inventory 10, capture 10, agreed; `testbed/gate-0.4.json` rewritten |
| schema 2 | `f9e2d6c`; 26 dry-run records across both policies, zero validation problems; `prove_collect.py` met |
| the freeze | frozen-package diff against the tag empty at `f9e2d6c`, `b6b4051`, `cb30871`; binary `b4220600…` |
| unattended root | `sudo -n -l` succeeds for `nmap`, `tcpdump` and `arp` from this account |

**The eight complete blocks.** Block spans by policy — flushed once: 1830, 993, 916,
2748 s; flushed per run: 3219, 3230, 1247, 2279 s. Per-run capture `ok` on all 106,
oracles `agree` on all 106, permission `granted`, cooldown 10.0 s. Privileged `-T2` ran
to completion eight times at 371 to 482 s. Unprivileged `-T2` ran eight times at 220 to
2546 s and `capture.wire` explains every one of them by its ARP request count and none
of them by anything else yet identified. Cold netsanity missed the two 500 ms responders
fourteen times out of fourteen; warm netsanity found them eleven times out of eleven.
The per-condition table is in the cache-state section, because that is what it is for.

The invocation, for the record:

```
W=/Users/jc/Dev/InfinityCastle-collection
/usr/bin/python3 $W/Study/harness/collect.py \
  --out $W/Study/data/pilot-attempt-3.ndjson \
  --log $W/Study/data/pilot-attempt-3.log \
  --status $W/Study/data/pilot-attempt-3-status.json \
  --alarm $W/Study/data/PILOT-STOPPED.txt \
  --cidr 192.168.64.0/24 --iface bridge100 \
  --netsanity $W/Packages/netsanity-cli/.build/release/netsanity \
  --cooldown 10.0 --control-host 192.168.64.4 --control-host 192.168.64.6 \
  --blocks-per-stratum 8 --minimum-days 1 --daily-quota 7 \
  --flush-policy alternate
```

Started once at 10:26:55 with `--daily-quota 6`, halted by the lid at 10:36:28; started
again at 10:39:06 with the quota at 7 so the afternoon window could hold the remaining
seven blocks; stopped with `SIGTERM` at 15:43:01 once the eighth block was in, the
driver logging `stopped on request` and releasing its assertion.

## What is recorded and where

| | |
|---|---|
| `data/pilot.ndjson` | the second attempt; every timing, recall, exclusion and schedule number cited from it is recomputable with `analysis/pilot.py`, and the three named above were not |
| `data/pilot-attempt-1.ndjson` | the first attempt, kept because its failures are the record of what the apparatus could not do before this date |
| `data/pilot-attempt-3.ndjson` | **the gate**: the third attempt, schema 2, eight complete blocks across both flush policies; every number in the cache-state section is recomputable from it with `analysis/pilot.py` |
| `data/pilot-settle.json` | every post-exit frame per condition, the cooldown's evidence |
| `data/pilot-raw/`, `pilot-captures/`, `pilot-stores/`, and `pilot-attempt-3-*/` | raw tool output, Mac-side pcaps, and history stores, by run id; git-ignored like collection's |
| `harness/settle.py` | the cooldown measurement, re-runnable |
| `analysis/pilot.py` | the report, standard library only |

The apparatus commits: `91f7e31` (testbed rebuilt), `a0ab4f3` (the five defects, the
injected fault, the sleep covariate), `05b0870` (the cooldown), `30584fc` (host sleep
stops the block; the cache label), `f9e2d6c` (schema 2; flush per run runnable; testbed
rebuilt after the power loss), `7ebad19` (the driver waits for AC), `cb30871` (a named
attempt's output ignored). The frozen packages are byte-identical to
`study/binary-2026-09-12b` at every one of them, checked each time the worktree moved.
