# 0.6 — The pilot

`PHASE0.md` 0.6: three real blocks against the programmable segment, through the
collection driver rather than by hand, to measure the variance, set the cooldown from
it, and confirm the exclusion machinery by breaking a run on purpose. The first live
blocks the study has ever run, on 2026-09-12, the day unattended root arrived.

It took two attempts. The first found five apparatus defects no dry run could have
shown and then lost a block to the host going to sleep under the driver's own
assertion; that attempt is kept as `pilot-attempt-1.ndjson`. The second attempt, after
the fixes, is the gate, and its numbers come from `pilot.ndjson`. Both are read by
`analysis/pilot.py`, which is standard-library python and prints nearly everything this
document cites — the exceptions are named in "What is not recomputable from the NDJSON"
and are the reason the gate is not met.

**Both files live in the collection worktree, not in this checkout.** Collection runs
from a worktree checked out detached at the apparatus commit, the pilot ran from it, and
`data/.gitignore` ignores `pilot*.ndjson` for the same reason it ignores `runs.ndjson` —
the harness appends to it while `provenance.py` requires a clean tree. They are
published as a release artifact alongside the pcaps.

```
C=~/Dev/InfinityCastle-collection/Study/data
python3 Study/analysis/pilot.py $C/pilot.ndjson
python3 Study/analysis/pilot.py $C/pilot-attempt-1.ndjson
```

Nothing here is evidence for a hypothesis. Three blocks is a diagnostic of the
apparatus, and the two places below where a hypothesis's refutation condition is
visibly live are written down so that collection is read with them in view, not so
that anything is concluded from them.

**Gate status: not met.** `PHASE0.md` 0.6 asks for three things. Exclusion is 1 of 39,
2.56%, and the one exclusion is the fault this pilot injected on purpose — met.
Variance is stable enough for every test the protocol names, with unprivileged `-T2`
named below as the one condition whose median no block count in this design pins —
met, with that stated rather than smoothed. The third is that every number in the pilot
is recomputable from the NDJSON alone, and it is not: three quantities this document
cites come from the raw artifacts and the packet captures, which are git-ignored and
shipped as a release artifact. They are named in "What is not recomputable from the
NDJSON" below, with the schema fix each one needs.

The blocks do not have to run again to fix it — the timing, recall and exclusion
numbers are all in the records already. What has to run again is a pilot under the
repaired schema, because a gate that says "every number" is not met by "every number
that turned out to matter". **The repair is in, at apparatus commit `f9e2d6c`
(2026-09-13), and the pilot that would meet the gate is built and not yet run** — see
"The third attempt, ready and not run" at the end. It is also the pilot that prices the
cache-state options below with measurements rather than one inferred number, which is
why it is designed to run both block shapes rather than the old one.

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
does nothing about kernel neighbour-table state, which is not traffic, outlives it by
minutes, and turns out to order unprivileged `-T2`'s wall clock across the whole pilot —
see "The second attempt". No cooldown short enough to run 120 blocks in a week would
clear that, which is why it is a design question for the cache-state ruling and not a
number to raise here.

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

A block is about 43 minutes: unprivileged `-T2` at up to 32 of them, privileged `-T2`
at eight, everything else under half a minute, plus thirteen cooldowns and 65 s of
capture and oracle overhead per block. `conditions.estimated_block_seconds(10)` says
2504 s from the pilot's numbers, using the largest observed `-T2` rather than the
median, because that estimate is what the driver uses to decide whether a block can
still start before a stratum's window closes. The gate attempt's measured block *spans*
were 2559, 2599 and 1226 s, so 2559 s is the median a schedule should budget — the
estimate and the span differ by the overhead, and both are right about different things.

Five blocks per stratum per day — the cap the driver derives as `ceil(30/7) + 1` — is
3.6 hours of each six-hour window and 14.2 hours of each 24. 120 blocks is about 85
hours of machine time in a 168-hour window. It fits, with the slack halved from what
the twelve-minute estimate implied: a stratum whose fifth block cannot start in time
takes four that day and the
window stretches to eight days, which the floor allows. If unprivileged `-T2` turns out
to sit at the slow end more often than not, that is what will happen, and the census
will show it as a stratum filling at four a day rather than five.

## What the variance says about the block count

Every figure in this section is from `pilot.ndjson`, the second attempt, which is the
gate, except where it names the first. The first attempt's spread is not usable here:
four of its runs spanned host sleep and their wall clocks are the sleep, not the scan.
An earlier draft of this section reported the first attempt's numbers as the pilot's,
which overstated the spread on nine of the thirteen conditions and understated it on
three.

Three blocks pin sigma to a factor of ten, which is what three samples buy; the point
of running them was to find out which conditions are tight and which are not, and the
answer is clean. The netsanity conditions have coefficients of variation of 0.00 to
0.02, so n = 30 per stratum gives intervals on all four of their medians of 1.1% or
better — `ns.budget.shared`, the loosest of them in the first attempt at 0.18, comes in
at 0.00 once no run is measuring a sleeping laptop. Privileged nmap sits at 0.01 to
0.12, the 0.12 being `-T2` and worth watching rather than worrying about at three
samples. Unprivileged nmap `-T3` to `-T5` sits at 0.13 to 0.27, which at n = 30 is ±6%
to ±12% on the median and, pooled across strata, about half that. Unprivileged `-T2` is
the outlier at 0.58, and no block count in this design gives a tight interval on its
median: its sigma's own 95% interval reaches 5138 s, and pinning the median to ±25%
against a sigma at that end would take 779 blocks. Its result will be reported as a
distribution with two modes, if that is what 120 samples show, rather than as a median
with an interval — and the two modes are visible already, at 462 s against 1809 and
1938 s, with a mechanism attached rather than a shrug. See the cache-state section
below, because the mechanism and the ruling that section asks for are the same thing.

For the hypothesis tests none of this is close. H1 and H2 are rank comparisons and the
distributions do not overlap: every netsanity discovery run in the pilot finished
inside 0.38 s and every nmap run took at least 4.2 s. H5 compares `ns.budget.shared` at
1.67 s against `ns.disc.unpriv` at 0.37 s, a factor of four and a half with no overlap.
H6 is a recall comparison, McNemar on paired per-host outcomes, and its resolution is
set by the number of hosts times blocks rather than by timing variance.

Section 7's n ≥ 30 per stratum is adequate for every test the protocol names **in the
warm arm**, which is where 110.8 of the 120 blocks' runs per condition land. Where it is
thin on timing is the interval around unprivileged nmap's median at the faster
templates, and there it is thin in the way `FINDINGS-0.5-harness.md` already said it
would be. Where it is thin on recall is the cold arm, at 2.3 runs per condition per
stratum, and that is not a variance problem with a bigger n as its answer — it is the
design question the cache-state section puts to JC.

## Two things to carry into collection, written plainly

**The gate 0.3 defeat is a cold-cache observation, and the pilot has not exercised it
on the adaptive default.** Gate 0.3 found netsanity missing both 500 ms responders with
a discovery stage shorter than their round trip. The pilot reproduced it exactly once,
in the first attempt: `ns.fixed.timeout`, first in block 0, recall 0.8, missed exactly
`192.168.64.12` and `.13`, the two 500 ms responders. Every other netsanity run in
either attempt started warm and every one of them reported all ten — with seven to nine
echo replies seen against eleven hosts found, the rest read from the neighbour table
that the run before had provoked into holding the 500 ms hosts' ARP replies. The
artifact's `replies_seen` against `hosts_found` shows it per run, and that pair of
numbers is one of the three this document cites and the NDJSON does not hold.

**Once, across 78 runs.** That is the finding, and it is about the design rather than
about netsanity. A block flushes once and then runs thirteen conditions, so one run per
block is cold and twelve are warm. Six of the pilot's 78 runs were cold, they landed on
six different conditions, and seven of the thirteen conditions — including
`ns.disc.unpriv`, `ns.naming.full`, `ns.budget.shared` and unprivileged `-T2` — got no
cold observation at all. The second attempt's three cold slots went to
`nmap.sn.priv.T2`, `nmap.naming.broadcast` and `nmap.sn.unpriv.T5`; not one netsanity
condition ran cold in the attempt that is the gate. The pilot cannot say what cold
costs netsanity's adaptive default because it never once measured it.

So H2's refutation condition — a privileged nmap point at recall 1.0 that netsanity
does not match — is live in the cold-cache stratum of the data and not in the warm one,
and the two must be analysed apart, as section 5 says. The harness stamped every run
in a block `cold` until the second pilot attempt; it now labels by position, and the
analysis should read cold as `sequence_index == 0` in any record from before commit
`30584fc`. With randomised order each condition lands cold in about one block in
thirteen, so 120 blocks give roughly nine cold runs per condition. That is enough to
see a miss that happens every time, which is what gate 0.3 and this pilot both saw,
and not enough for much else. Nothing was tuned, and nothing should be.

**H6's refutation condition is not merely live, it fires on the pilot's own three
blocks.** H6 is refuted if the median per-block recall of unprivileged nmap, at its best
timing template, is less than 0.25 below unprivileged netsanity's. Unprivileged `-T3`,
`-T4` and `-T5` sit at 0.4 in every block — the three web hosts and the TCP-only host,
by `syn-ack`. Unprivileged `-T2` is the best template and in the gate attempt it scored
0.9, 1.0 and 0.4: seven `conn-refused` plus three `syn-ack` in the block where it
reached 1.0, against netsanity's 1.0. Median 0.9 against 1.0 is a gap of **0.1**, well
inside 0.25, and in one block of three the gap is zero.

Three blocks decide nothing and this is a diagnostic, not a result. It is written this
plainly because the amendment of 2026-09-08 predicted a gap near 0.75, and the reason it
was wrong is now known and mechanical: a closed port answers a connect probe with a RST
that nmap counts as a host, `-T2`'s pace leaves nmap listening long enough to count
them, and seven of the ten responders have a TCP stack that answers a probe to a closed
port with a RST whether or not they serve anything. The captures show those seven
sending RSTs even in the runs where nmap reported none of them, so the difference
between recall 0.4 and recall
1.0 on the same command is entirely whether nmap was still waiting. Whether the median
gap stays under 0.25 across 120 blocks is collection's question, and nothing in the
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
2559 s is the number the schedule should use, and `conditions.estimated_block_seconds(10)`
says 2504 s, which is the cost and not the span. Privileged `-T2` ran to completion
three times at 466, 376 and 469 s, confirming the first attempt's 471 and 452 and
putting gate 0.3's 510 s extrapolation to rest as pessimistic. Unprivileged `-T2` ran
1809, 1938 and 462 s and is still the largest term in a block by a factor of four over
privileged `-T2`.

**The 1171 s block is the one to read twice.** It is not a faster machine or a quieter
network; it is the block in which unprivileged `-T2` took 462 s instead of 1800-odd, and
that single run is the whole difference. Its capture holds 954 ARP requests against 1777
and 1412 in the two slow runs, and its `conn-refused` count is zero against six and
seven.

What orders those runs is not which condition preceded them but **how long since a
netsanity sweep last ran**. Across the five admissible unprivileged `-T2` runs in the two
attempts, the gap between the end of the last netsanity run in the block and the start of
`-T2` sorts them exactly:

| gap since the last netsanity run | unprivileged `-T2` |
|---|---|
| 15 s | 462 s |
| 35 s | 228 s |
| 76 s | 1735 s |
| 101 s | 1809 s |
| 407 s | 1938 s |

netsanity's sweep drives discovery through the kernel's own neighbour resolution and so
leaves negative-cache state across all 254 addresses behind it; privileged nmap ARPs from
its own raw socket and leaves that state untouched. Unprivileged nmap cannot send a SYN
the kernel has not resolved, so it inherits whatever that state is. Five points with a
threshold somewhere between 35 s and 76 s is a correlation with a plausible mechanism and
not a measured decay curve, and the kernel's 20 s `host_down_time` — the one piece of
carried state the cooldown measurement tested directly — is close to the fast end without
accounting for 35 s.

It is written down because of what it implies rather than what it explains: **"warm" is
not one state.** It is a function of which conditions ran before and how recently, so a
single warm/cold label is describing a continuum with two words. That is the thing the
cache-state ruling below has to settle, and the 10 s cooldown — set from a traffic tail
that is genuinely short — does nothing about it, because the state that matters here
outlives the traffic by minutes.

## What is not recomputable from the NDJSON, and why that fails the gate

`HARNESS.md` states the rule the whole apparatus is built around: collection produces
raw evidence, analysis produces numbers, and they meet only at an append-only NDJSON
file. `PHASE0.md` 0.6 turns it into a gate condition — every number in the pilot
recomputable from the NDJSON alone. Three quantities this document cites are not, and
all three were found by checking the claim rather than by anything going wrong.

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

It matters beyond tidiness because those three are exactly the numbers carrying the
cache-state mechanism, which is the question the next section puts to JC. The evidence
for the most consequential open decision in the study is the evidence a reviewer cannot
check from the file the protocol says is the record.

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
   `prove_collect.py` still met.

None of this touches `Packages/netsanity-core` or `netsanity-cli`, and none of it is a
reason to rebuild the binary. The frozen packages are byte-identical to
`study/binary-2026-09-12b` at `30584fc` and again at `f9e2d6c`, checked each time the
collection worktree moved, and the binary in it still hashes `b4220600…`.

**What this does not excuse.** Nothing above changes a measured number. Exclusion is
2.56%, the variance is what the table says, and the injected fault was caught unaided
twice. The gate is not met because it asks for something more than that, and the honest
reading is that the third condition was written to prevent exactly the situation this
document was in — citing pcap numbers in a findings document while claiming the NDJSON
held everything.

## Cache state: four numbers, and a decision that is not the agent's to take

`PROTOCOL.md` section 5 says cache state is a condition and not an accident, that each
block begins with a cache flush, and that warm versus cold is recorded and analysed
separately. Section 5 also says n ≥ 30 blocks per stratum. As built, those two sentences
do not hold together, and the pilot is what made it visible: **six cold runs in 78, on
six different conditions, and seven conditions with none at all.**

The arithmetic, with K = 13 live conditions and B = 30 blocks per stratum.

**The design as it stands.** One flush per block, then thirteen conditions in randomised
order, so exactly one run per block is cold. Each condition is cold with probability
1/13.

- Cold: **2.3** per condition per stratum, **9.2** pooled across the four strata.
- Warm: **27.7** per condition per stratum, **110.8** pooled.
- A given condition never lands cold in a 30-block stratum with probability 0.091, so of
  the 52 condition-by-stratum cells, about **4.7 are expected to hold no cold run at
  all**. Pooled over 120 blocks that probability falls to 7e-5, but pooling is what the
  strata exist to prevent.

So the cold arm is not merely small: it is a random 1-in-13 draw that cannot be
stratified, and section 5's "analysed separately" is asking for an analysis the design
cannot supply.

**Flushing before every run in half the blocks.** Fifteen flushed blocks per stratum in
which every run is cold, fifteen unflushed in which one is.

- Cold: **16.2** per condition per stratum, **64.6** pooled.
- Warm: **13.8** per condition per stratum, **55.4** pooled.
- Against n ≥ 30 per stratum, **neither arm reaches it.** Both clear 30 only when pooled
  across strata, which again is the thing stratification exists to prevent.
- Wall clock: the flush itself is nothing — `sudo -n arp -a -d` measured at a median of
  0.040 s, so 0.5 s across a thirteen-condition block, against a block span of 2559 s.
  The cost is in the runs, and the pilot can price only one of them, and that one only
  indirectly. Unprivileged `-T2` loses its fast mode by construction: a flush before
  every run guarantees no netsanity sweep has warmed the neighbour table, and the
  recency table above says that is the condition under which it runs at 1735 s or more.
  Pinning it to the mean of its two slow runs, 1874 s, takes the median block span from
  2559 s to **2623 s, about 64 s or 2.5%**.
- **That 2.5% is the weakest number in this document and should be read as a floor.**
  Of the thirteen conditions, seven have never been observed cold at all — including
  unprivileged `-T2` itself, so even its estimate rests on the recency correlation rather
  than on a cold measurement — and the remaining six have been observed cold exactly once
  each. A design whose cold arm is one run in thirteen cannot price its own alternative,
  which is close to being the argument for changing it. **The third attempt below is
  built to replace this bullet with a measurement**: four blocks flushed before every
  run against four flushed once, so every condition is observed cold four times and the
  per-condition cost of the policy is a number rather than a floor.

**Keeping both arms at n = 30 per stratum.** Warm needs 32.5 unflushed blocks, cold
needs 27.5 flushed, so **60 blocks per stratum, 240 blocks, with 46% of blocks flushed
per run.** At a 2623 s span that is **175 hours of machine time** against 85 hours for
the design as it stands. The floor moves, and it moves to neither of the numbers the
question offered:

| blocks/day/stratum | days | machine h/day | of each 6 h window | window |
|---|---|---|---|---|
| 5 (the current cap) | **12** | 14.6 h | 3.6 h | 288 h |
| 6 | **10** | 17.5 h | 4.4 h | 240 h |
| 7 | 9 | 20.4 h | 5.1 h | 216 h |
| 8 (the most a 6 h window holds) | 8 | 23.3 h | 5.8 h | 192 h |

At the cap the driver derives today — `ceil(30/7) + 1 = 5` — the seven-day floor becomes
**twelve days**, not ten and not fourteen. Ten days is available at a cap of six a day,
which is a change to `daily_quota` and therefore itself an amendment. Eight days is
arithmetically possible and leaves 0.7 h of slack in a 24-hour day, which is not slack.

**Does any of this make a hypothesis untestable? No — and that is the trap.**

- **H1** and **H5** survive every option. The distributions do not overlap: netsanity
  discovery inside 0.38 s against nmap's 4.2 s minimum, and `ns.budget.shared` at 1.67 s
  against `ns.disc.unpriv` at 0.37 s. Even at n = 13.8 per stratum these are rank
  comparisons that are not close.
- **H2** is testable under every option and *supported* very differently. The central
  figure is a speed/recall Pareto frontier, the cold regime is where netsanity's recall
  is 0.8 rather than 1.0, and that regime rests on 9.2 points per condition as built and
  64.6 under flush-per-run. H2 is the study's central claim, its refutation condition is
  a privileged nmap point netsanity does not match, and privileged nmap is at recall 1.00
  on all eleven admissible runs in the gate attempt. So the frontier's answer turns on
  cold netsanity, which as built is the arm with nine points. And privileged nmap's own
  1.00 may not be cache-independent either: the first attempt's one cold privileged run,
  `nmap.sn.priv.T3`, scored 0.90 and missed `192.168.64.13`, a 500 ms responder. One
  observation is not a finding, but it is the only cold privileged observation the study
  has, and it went the direction nobody assumed.
- **H6** is testable under every option and may well *answer differently* under each.
  Its refutation condition already fires on the gate attempt's warm data at a median gap
  of 0.1. Cold, netsanity scored 0.8 the one time it was measured, and unprivileged
  `-T2` reached 0.9 and 1.0 in two of three blocks. Flushing before every run does not
  make H6 untestable; it makes it *more likely to refute*.

That last point is why this section stops here. Every option that improves the cold
arm's power also makes H1, H2 and H6 harder for netsanity to pass, and the party
choosing between them wrote netsanity. `PROTOCOL.md` section 9 declares that conflict of
interest and says the falsification conditions are what make the declaration mean
something; an amendment chosen by the author, after seeing which way the pilot leaned,
is the amendment a reviewer reads hardest and should.

**So: no design is chosen here, and collection does not start.** The options above go to
JC with their numbers. When he rules, the amendment goes in `PROTOCOL.md` section 12,
dated, saying what prompted it and stating that it was decided before any block was
collected — which is true, and which is the only reason any of this is worth writing
down.

## The third attempt, ready and not run

Built on 2026-09-13 and deliberately left for a person to start. It serves two purposes
at once and the design follows from that:

- **Gate 0.6 under schema 2.** Every record carries `parse.discovery` and
  `capture.wire`, so the three quantities above become recomputable and the gate's third
  condition can be assessed rather than argued about.
- **The cache-state options, priced.** `--flush-policy alternate` gives odd block ids a
  flush before every run and even ones the protocol's single flush. Eight blocks is four
  of each: every one of the thirteen conditions observed cold four times, against the
  four warm blocks of the same day and the three of the second attempt, so the
  per-condition cost of flushing per run — wall clock and recall — is measured for all
  thirteen instead of inferred for one.

Not repeated: the injected fault. Attempts one and two both caught it unaided, on two
different conditions, and a third would be manufacturing an exclusion to admire. This
attempt's exclusion rate is therefore the apparatus's own.

What was done before it could run, in order, each checked:

| step | result |
|---|---|
| testbed, after the host lost power | all five machines restarted; `netbed.py configure` re-shaped and re-calibrated the ten responders at the same addresses and roles; worst achieved error 1.22% against 10% |
| the three oracles | three consecutive rounds, manifest 10, inventory 10, capture 10, agreed; `testbed/gate-0.4.json` rewritten |
| schema 2 | `f9e2d6c`; 26 dry-run records across both policies, zero validation problems; `prove_collect.py` met |
| the freeze | `git diff --stat study/binary-2026-09-12b f9e2d6c -- Packages/netsanity-core Packages/netsanity-cli` empty; binary `b4220600…` |
| the collection worktree | moved to `f9e2d6c`, clean, standing `sudo -n` grant confirmed for all three binaries |
| unattended root | `sudo -n -l` succeeds for `nmap`, `tcpdump` and `arp` from this account |

The invocation, from the collection worktree, writing to files `data/.gitignore` already
covers:

```
W=/Users/jc/Dev/InfinityCastle-collection
nohup /usr/bin/python3 $W/Study/harness/collect.py \
  --out $W/Study/data/pilot-attempt-3.ndjson \
  --log $W/Study/data/pilot-attempt-3.log \
  --status $W/Study/data/pilot-attempt-3-status.json \
  --alarm $W/Study/data/PILOT-STOPPED.txt \
  --cidr 192.168.64.0/24 --iface bridge100 \
  --netsanity $W/Packages/netsanity-cli/.build/release/netsanity \
  --cooldown 10.0 --control-host 192.168.64.4 --control-host 192.168.64.6 \
  --blocks-per-stratum 8 --minimum-days 1 --daily-quota 6 \
  --flush-policy alternate \
  > $W/Study/data/pilot-attempt-3.driver.out 2>&1 &
```

Eight blocks at about 43 to 45 minutes each is six hours of machine time. With a daily
quota of six the driver takes what fits in the current stratum's window, waits at the
boundary for the next, and after eight it goes to `waiting`, at which point it is
stopped with `SIGTERM` as the second attempt was. Then:

```
python3 Study/analysis/pilot.py $W/Study/data/pilot-attempt-3.ndjson
```

prints the cold-against-warm table per condition, the block span under each policy,
and the wire counts for unprivileged `-T2`, and this document's cache-state section is
rewritten against them before the options go to JC a second time.

Why it was not started by the agent: the driver takes root through the standing grant
to scan the segment and flush the host's neighbour table, and the session's policy
classed launching it as modifying a shared resource. That is a reasonable line for a
policy to draw and it was not argued with. The command above is the whole of what was
going to run.

## What is recorded and where

| | |
|---|---|
| `data/pilot.ndjson` | the pilot that is the gate; every timing, recall, exclusion and schedule number above is recomputable from it with `analysis/pilot.py`, and the three named above are not |
| `data/pilot-attempt-1.ndjson` | the first attempt, kept because its failures are the record of what the apparatus could not do before this date |
| `data/pilot-attempt-3.ndjson` | the third attempt, schema 2, both flush policies; the gate candidate once it has run |
| `data/pilot-settle.json` | every post-exit frame per condition, the cooldown's evidence |
| `data/pilot-raw/`, `pilot-captures/`, `pilot-stores/` | raw tool output, Mac-side pcaps, and history stores for both attempts, by run id; git-ignored like collection's |
| `harness/settle.py` | the cooldown measurement, re-runnable |
| `analysis/pilot.py` | the report, standard library only |

The apparatus commits: `91f7e31` (testbed rebuilt), `a0ab4f3` (the five defects, the
injected fault, the sleep covariate), `05b0870` (the cooldown), `30584fc` (host sleep
stops the block; the cache label), `f9e2d6c` (schema 2; flush per run runnable; testbed
rebuilt after the power loss). The frozen packages are byte-identical to
`study/binary-2026-09-12b` at every one of them, checked each time the worktree moved.
