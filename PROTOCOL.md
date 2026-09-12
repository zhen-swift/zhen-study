# Pre-registered study protocol

**Title:** Retransmit Early, Declare Late: Decoupled Timing Budgets for Fast,
Complete Host Discovery on Heterogeneous Local Networks.

**Status:** protocol frozen before data collection. Any change after the first
measurement run is recorded in the Amendments section with a date and a reason, and
disclosed in the paper. That discipline is what separates a benchmark from an
advertisement.

---

## 1. What is actually being claimed

"Our scanner is faster than nmap" is not a reviewable claim. Compared as shipped,
netsanity performs host discovery *and* three naming protocols while `nmap -sn`
performs host discovery only — different work, so a wall-clock comparison measures
nothing. The claims below are narrower, matched, and falsifiable.

**H1 (speed, matched workload).** For host discovery alone on a heterogeneous /24,
netsanity's median time-to-complete is lower than `nmap -sn` at every timing template
that achieves equal or better recall.
*Refuted if* any nmap timing template matches netsanity's recall at equal or lower
median time.

**H2 (the trade curve).** Per-host adaptive retransmission timing dominates fixed
timing templates on a network whose round-trip times span orders of magnitude: for any
nmap template, there exists a netsanity configuration that is both faster and at least
as complete.
*Refuted if* the Pareto frontier of nmap's templates contains a point netsanity does
not match or beat. **This is the central scientific claim.** H1 is a corollary.

**H3 (privilege).** Unprivileged netsanity achieves recall statistically
indistinguishable from privileged netsanity and from unprivileged `nmap -sn`, using
macOS `SOCK_DGRAM`/`IPPROTO_ICMP` where nmap without root falls back to TCP connect
probes.
*Refuted if* unprivileged recall is significantly below either comparator.

**H4 (identification, capability not speed).** Fusion of mDNS, SSDP, NetBIOS and OUI
data names a larger fraction of hosts than nmap's OS fingerprinting identifies, on a
consumer LAN where a majority of devices use randomised MAC addresses.
*Reported as a capability comparison, not a benchmark* — the two systems attempt
different tasks and no timing claim is attached.

**H5 (budget separation).** Separating the retransmission budget from the
absence-declaration budget reduces total sweep time without reducing recall, relative
to a single shared budget.
*Refuted if* recall drops, or if the reduction is within run-to-run noise. This is an
ablation of our own system and requires no comparator.

### Non-claims, stated explicitly

Not claimed: that netsanity is a general-purpose replacement for nmap; that Swift is
faster than C; that results generalise beyond macOS or beyond /24-scale consumer
networks; anything about port scanning, service detection, or scripting. A reviewer
who finds the paper claiming any of these has found a defect.

---

## 2. Systems under test

| System | Version | Build |
|---|---|---|
| netsanity | commit hash, recorded per run | `swift build -c release` |
| nmap | `nmap --version` verbatim | Homebrew, recorded |
| macOS / hardware | `sw_vers`, `sysctl hw.model` | recorded per run |
| Swift toolchain | `swift --version` | recorded |

### Matched configurations

Each cell is one experimental condition. Every condition runs the same number of times
in the same interleaved sequence.

| Condition | netsanity | nmap |
|---|---|---|
| Discovery, unprivileged | `scan --json` (naming disabled) | `nmap -sn` as user |
| Discovery, privileged | `scan --json` (naming disabled) | `sudo nmap -sn` |
| Timing sweep | default adaptive; plus fixed-timeout ablations | `-T2`, `-T3`, `-T4`, `-T5` |
| Ablation, budget | single shared budget vs split | — |
| Naming | full pipeline | `-sn --script broadcast-*` (documented as approximate) |

**Naming must be disabled in netsanity for H1–H3.** If the CLI has no flag for that,
adding one is a prerequisite of this study, not a finding of it.

---

## 3. Ground truth

Recall is meaningless without knowing what was there. Three independent oracles, used
together:

1. **A controlled testbed.** N hosts on an isolated segment with known addresses and
   deliberately varied response characteristics: wired, 5 GHz Wi-Fi, 2.4 GHz Wi-Fi, a
   host with ICMP filtered, a host answering only on TCP/80, a host that sleeps. Built
   from containers, VMs and a small number of physical devices. Composition recorded.
2. **The switch's client table**, read out of band. An independent view of who is
   present that neither scanner produced.
3. **A long passive capture** on the segment during each run, used post hoc to
   establish which hosts were reachable at that moment — the only oracle that
   distinguishes "the scanner missed it" from "it was asleep".

A run whose oracles disagree is excluded, and the exclusion is reported.

---

## 4. Metrics

**Primary.** Time to complete (wall clock, monotonic, process start to artifact
written). Recall = found ∩ truth / truth. Precision = found ∩ truth / found.

**Secondary.** Time to first host on screen. Probes sent per host discovered. Peak
in-flight probes. Energy per scan (`powermetrics`, laptop on battery, screen off).
Run-to-run set stability (Jaccard between consecutive runs of the same condition).

**H4 only.** Fraction of ground-truth hosts assigned a human-meaningful name; fraction
assigned a model; fraction of randomised-MAC hosts named at all.

**H5 only.** Sweep time and recall, split budget versus shared.

Every metric comes from the artifact or from the harness, never from a human reading a
terminal.

---

## 5. Design

**Interleaved, randomised, blocked.** Conditions run in randomised order within each
block, never all of one tool then all of the other — otherwise network drift and
thermal state confound the comparison. One block = one run of every condition.

**n ≥ 30 blocks per stratum**, and four time-of-day strata (morning, afternoon,
evening, overnight) across **at least seven consecutive days**, so device sleep cycles
and household network load are sampled rather than avoided. That is the "long-running"
part: roughly 1,000 scans, unattended.

**Cache state is a condition, not an accident.** The ARP/neighbour table hugely
advantages any scanner that runs second. Each block begins with a cache flush, and
"warm" versus "cold" is recorded and analysed separately.

**Inter-run cooldown** long enough that one scan's traffic cannot affect the next.
Measured and fixed before collection begins.

---

## 6. Confounds, and how each is controlled

| Confound | Control |
|---|---|
| ARP cache warming | flush per block; warm/cold recorded and analysed apart |
| Ordering and drift | randomised interleaving within blocks |
| Thermal / CPU state | cooldown between runs; `powermetrics` recorded; plugged-in state fixed |
| Wi-Fi contention | time-of-day strata; passive capture records channel utilisation |
| Device sleep | oracle 3 distinguishes absent from asleep; strata sample the cycle |
| Privilege asymmetry | privileged and unprivileged are separate conditions, never mixed |
| macOS Local Network permission | granted and verified before collection; state asserted per run |
| Tuned-versus-default unfairness | nmap swept across `-T2`…`-T5`; comparing to `-T3` alone is not honest |
| Our own defaults being tuned to this network | testbed composition differs from the development network; report both |
| Version drift mid-study | commit hash pinned; a rebuild restarts the block |
| netsanity's own history write | one disposable store per run, named in the argv; see the 2026-09-11 amendment |

---

## 7. Analysis plan, fixed in advance

Report **medians and interquartile ranges**, never means alone — scan-time
distributions are right-skewed and heavy-tailed, and a mean flatters whichever system
has fewer catastrophic runs.

Between-system comparison: **Mann–Whitney U**, two-sided, α = 0.05, with
**Cliff's delta** as effect size. Bonferroni correction across the hypothesis family.
Confidence intervals by bootstrap (10,000 resamples).

Recall differences: **McNemar's test** on paired per-host outcomes within a block,
since the same hosts are observed by both systems.

H2 is answered by plotting the **speed/recall Pareto frontier** for every condition and
testing whether any nmap point is non-dominated. That plot is the paper's central
figure.

**Pre-specified exclusions:** runs where an oracle disagrees, runs where the harness
records an interfering process, runs during a network topology change. Exclusion rate
is reported; if it exceeds 5% the study is re-designed rather than patched.

---

## 8. Harness

`Study/harness/` — one script, no interactive steps, resumable, and it records
provenance for every run: timestamps, versions, git hash, cache state, ambient
conditions, raw stdout of both tools, and the netsanity artifact verbatim.

Output is one NDJSON line per run into `Study/data/`, append-only. Analysis reads only
that file. No number in the paper may exist that cannot be recomputed from it.

The harness must fail loudly and stop rather than silently skipping a condition — a
gap in the data that nobody notices is worse than a study that halts.

---

## 9. Threats to validity

**Internal.** We wrote one of the systems and chose its defaults; the testbed is
sampled, not exhaustive; the passive-capture oracle can itself miss traffic.

**External.** One hardware model, one OS version, one network topology, /24 scale
only. Nothing here supports claims about enterprise networks, IPv6, or Linux — and the
paper must say so in the abstract, not only in a limitations section.

**Construct.** "Reliability" is operationalised as recall, precision and set stability;
a reader may reasonably mean something else by the word, so the paper defines it early
and uses the operational terms thereafter.

**Conflict of interest.** Declared: the authors built netsanity. The protocol,
harness and raw data are published so a reviewer can rerun the analysis, and the
falsification conditions in section 1 are the commitment that makes the declaration
meaningful.

---

## 10. Deliverables

1. This protocol, frozen and dated.
2. `Study/harness/` — the collection scripts.
3. `Study/data/*.ndjson` — every run, raw, including excluded ones with reasons.
4. `Study/analysis/` — the analysis, runnable end to end from the raw data.
5. The paper: 8–12 pages, IEEE or ACM two-column, with the Pareto figure as Figure 1.
6. A reproducibility appendix: exact versions, testbed bill of materials, and the
   commands to rebuild both systems.

---

## 11. Phases

| Phase | Work | Gate before proceeding |
|---|---|---|
| 0 | Add a naming-disable flag to the CLI; confirm nmap install; freeze this protocol | Protocol reviewed and dated |
| 1 | Build the testbed; verify all three oracles agree on a known set | Oracles agree on 3 consecutive checks |
| 2 | Harness; pilot of 3 blocks; measure variance and set cooldown | Pilot data parses; variance stable |
| 3 | Collection: ≥ 7 days, ≥ 30 blocks per stratum, unattended | Exclusion rate < 5% |
| 4 | Analysis exactly as section 7 specifies | No deviation from the plan, or an amendment is recorded |
| 5 | Write the paper against whatever the data says | — |

---

## 12. Amendments

**2026-09-12 — H3 is withdrawn: netsanity has no privileged engine, and never had
one.** H3 asks whether unprivileged netsanity's recall matches privileged netsanity's.
There is no privileged netsanity. `netsanity-core` declares `EngineKind.privilegedBPF`
and `EngineKind.composite`, `SPEC.md` designs a `BPFDiscoveryEngine` and a
`CompositeDiscoveryEngine`, and neither is constructed anywhere in the product;
`ICMPSweepEngine` is the only `HostDiscovery` conformance on Darwin and reports
`kind: .unprivileged` unconditionally. `README.md` has said so throughout: *"Not built
yet: the privileged helper (layer-2 ARP sweep and SYN scanning)."*

Measured before it was read, which is the only reason it is stated this strongly.
`FINDINGS-0.3-nmap.md`, 2026-09-12: the same binary run under `sudo` and as the owner,
each under its own packet capture with the neighbour table flushed first, is
indistinguishable on the wire — 253 ARP requests and 20 ICMP echoes against 253 and 19,
no TCP in either, the same nine hosts. The ARP in both is the kernel resolving next-hop
for the ICMP datagrams rather than either run sweeping layer 2, which is why the counts
match: it is one engine, run twice.

**Why this is a withdrawal and not a restatement.** Both arms of H3 execute identical
code, so their recall is identical by construction and the parity claim is confirmed on
every block regardless of what the network does. That is not a weak result or an
underpowered one — it is a tautology, and reporting it with a p-value beside it would be
worse than reporting nothing. There is no version of the sentence that fixes this,
because the thing it compares against does not exist. The 2026-09-08 amendment split H3
in two precisely to make it testable and, without knowing it, kept the half that cannot
run and relocated the half that can to H6.

**What is removed, and what is not.** The condition `ns.disc.priv` leaves the matrix.
Section 2's matched-configuration table keeps its "Discovery, privileged" row for
`sudo nmap -sn`, which serves H1 and H2 and is unaffected. Nothing else changes: H6
already carries the privilege comparison that has a mechanism behind it, and it carries
it against nmap, where the privileged and unprivileged engines genuinely differ.

**Consequences for section 7.** The Bonferroni family returns from five statistically
tested hypotheses to four — H1, H2, H5 and H6. H4 remains a reported capability
comparison and carries no test. Every p-value in the family is corrected against four
from this date. This is the second change to the family size and both are recorded here
rather than inferred from a count of hypotheses that still appear in section 1.

**Why removing it is not patching an exclusion rate.** `runners.py` already refuses a
privileged netsanity artifact that reports the unprivileged engine, and would have
refused every one of them — one condition in fourteen excluded on every block, which is
7.1% against section 7's 5% ceiling, before any of the excluded-for-cause runs that
ceiling exists to bound. Section 7 says a study above 5% is re-designed rather than
patched, and this is the re-design: the condition is removed because it does not measure
anything, and the exclusion rate goes to zero as a consequence rather than as a goal. A
reviewer should be able to check that ordering, so it is stated in that order.

**What is lost, stated so a reader can discount it.** The study can no longer say
anything about whether root helps netsanity, because netsanity does not use root. That
is a real gap and it is a gap in the product rather than in the design: the paper says
netsanity's discovery is privilege-invariant because it has one engine, and does not
present that as a finding. The comparison a reader may actually want — whether an
unprivileged scanner gives up completeness against a privileged one — is not lost. It is
in H1 and H2, which compare netsanity against `sudo nmap -sn` at every timing template,
and the pre-declared refutation conditions there are the ones that will answer it.

**Why this was not caught before the protocol was frozen.** `conditions.py` was written
to be the place a missing capability becomes visible, and it worked twice: two conditions
sat `BLOCKED` naming the CLI flags they needed until those shipped. It did not catch this
one because a missing *engine* is not a missing *flag* — the argv is well-formed, the
process exits zero, and the artifact is valid. The check that would have caught it is
reading the artifact's `engine.kind` against the condition's expectation, which
`runners.py` does and which nothing ran against a real privileged invocation until root
was available. That is an argument for running one real block of every condition before
freezing a protocol, and it is the strongest argument this study has produced for its own
phase-0 discipline.

**2026-09-11 — netsanity's history write is isolated per run, and that is a
deliberate departure from what the product does.** `netsanity scan` persists every run;
`nmap -sn` persists nothing. Measured as shipped, the two conditions are therefore not
matched on I/O, and the mismatch is not a constant: `LogHistoryStore` is an append-only
log that rewrites itself once it passes a line threshold, so across a seven-day window
one run in N pays for a full compaction **inside the wall clock this harness measures**,
and which run pays is a function of how long collection has been running. That is a
systematic penalty on the system under test, in the direction that weakens H1, arriving
on a schedule no covariate records. It was found in the harness rather than in the
analysis, which is the only reason it is an amendment and not a retraction.

Every netsanity condition now names its own store through `NETSANITY_HISTORY`, written
as an explicit `env` assignment in the argv so that the recorded command is the whole
truth about what ran — and because `sudo -n` resets the environment, so an inherited
variable would have reached the unprivileged conditions and silently not reached the
privileged ones, which are the two halves of H3 and H6.

One store **per run**, not per block. An empty store makes every run's write the same
constant amount of work; a per-block store would have the first run insert and the rest
update, which is a within-block trend in precisely the quantity being measured.

What this costs, stated so a reader can discount it. The comparison no longer measures
netsanity as a person runs it — a real scan writes into a history file that accumulates,
and this one does not. H1 is a claim about discovery, `--discovery-only` already removes
naming for the same reason, and persistence is no more part of discovery than naming is;
but the reported figure is a scanner's discovery time and not a product's, and the paper
says so where it reports it. The `env` prefix itself costs one extra `exec` per
netsanity run that nmap does not pay. It is on the order of a millisecond and it biases
H1 against netsanity, which is the acceptable direction for a bias that could not be
removed without making the privileged and unprivileged conditions differ from each
other.

**2026-09-06 — the primary testbed is programmable, not physical.** Section 3 described
a physical segment of deliberately varied devices as the ground-truth testbed. That
becomes the secondary testbed, retained for external validity. The primary is a
programmable segment where round-trip time and loss are imposed per address, because
the central claim (H2, P1) is that the advantage scales with RTT dispersion, and a
physical network supplies whatever dispersion its hardware happens to have — one or two
points on a curve the study needs the whole of, and no way to reach a dispersion of 1
where the technique should show no advantage at all. Feasibility is gated in
`PHASE0.md` section 0.1; if the shaping cannot be made repeatable on this hardware the
amendment is withdrawn and the physical testbed returns as primary, with the dispersion
claim correspondingly weakened.

**2026-09-08 — H3 is split into a parity claim and a privilege-gap claim.** Section 1's
H3 asks unprivileged netsanity to be "statistically indistinguishable from privileged
netsanity **and from unprivileged `nmap -sn`**". Those two comparisons are not the same
claim, and the second one contradicts what this study predicts and has already
measured. `THEORY.md` P6 predicts that unprivileged `nmap -sn` recall *falls below*
both netsanity conditions for hosts answering ICMP but no probed TCP port, and 0.3
measured exactly that on the development network: netsanity 11 hosts, unprivileged
`nmap -sn` 1 host, three interleaved runs each, the single host found being the only
address on that segment running a web server
(`FINDINGS-0.3-nmap.md`). As written, H3 is therefore refuted by the very result it
exists to demonstrate — a defect in the sentence, not in the claim underneath it.

The correction is additive. Section 1 is left exactly as it was written and frozen, so
a reader can see what the protocol said before this date and judge the change; H3 and
H6 below are read in its place from this date forward.

> **H3 (privilege parity, netsanity only, amended 2026-09-08).** Unprivileged netsanity
> achieves recall statistically indistinguishable from privileged netsanity on the same
> segment in the same block, using macOS `SOCK_DGRAM`/`IPPROTO_ICMP` where the
> privileged engine uses raw sockets and ARP.
> *Refuted if* privileged netsanity's per-host recall exceeds unprivileged netsanity's
> by a margin whose bootstrap 95% confidence interval excludes zero, under McNemar on
> paired per-host outcomes within a block, after Bonferroni correction. Equivalence is
> claimed only within the resolution the block count supports, and that resolution is
> reported alongside the result rather than being allowed to stand in for a proof of no
> difference.

> **H6 (the privilege gap is nmap's, not netsanity's; new 2026-09-08).** On a local
> segment, losing root costs `nmap -sn` substantially more recall than it costs
> netsanity, because unprivileged nmap falls back to TCP connect probes to exactly two
> ports (80 and 443, measured in 0.3) and can emit neither ICMP nor ARP, while
> unprivileged netsanity retains ICMP.
> *Refuted if* the median per-block recall of unprivileged `nmap -sn` — at its best
> timing template — is less than **0.25 below** unprivileged netsanity's on the
> pre-declared testbed composition, or if the difference is not significant under
> McNemar after Bonferroni correction.

**Why 0.25, and how that condition can actually fire.** A claim that "nmap is worse" is
not falsifiable and does not belong in a protocol. The threshold has to be a number
fixed before collection that the data is genuinely able to fall short of, and it has to
be tied to a testbed whose composition is declared in advance, because the size of the
gap is a property of what is on the segment rather than of either scanner. A segment of
hosts that all run web servers would show a gap near zero; a segment of hosts that
answer ICMP and open no TCP port would show a gap near one. Neither would be
informative on its own.

So the testbed composition is pre-declared as part of this amendment, and 0.25 is
derived from it rather than chosen to be safe: of the programmable responders, **at
least one quarter must be hosts that answer ICMP and serve at least one of ports 80 or
443**, alongside the ICMP-filtered and TCP-only hosts section 3 already requires. On
such a segment, unprivileged nmap is expected to recover roughly the web-serving
quarter and netsanity roughly all of it, so the predicted gap is near 0.75 and a
measured gap of 0.25 is comfortably inside what the design can resolve — while a gap
that fails to reach 0.25 is a real possibility if the mechanism is weaker than P6
claims, if netsanity's own unprivileged recall is poorer than 0.2 suggested, or if
nmap's `-T5` template recovers hosts on retry that a single pass missed. The condition
fires on any of those.

**Scope: local segment only, and the abstract must say so.** The mechanism behind H6 is
specific to a segment the scanner shares with its targets. There, privileged nmap uses
ARP, which every host with a MAC address must answer regardless of its ICMP or TCP
policy, so nmap's privileged/unprivileged difference on a local segment is close to
total. Across a router there is no ARP to lose: privileged nmap falls back to ICMP echo
plus a small TCP/UDP probe set, unprivileged nmap keeps the TCP connect probes, and the
gap between them is much smaller. This study measures only the local-segment regime, so
H6 is a local-segment claim and nothing in it supports a statement about routed
scanning. Per section 9, that limit goes in the abstract and not only in the
limitations section.

**Consequences for section 7's analysis plan.** The Bonferroni family grows from four
statistically tested hypotheses (H1, H2, H3, H5 — H4 is a reported capability
comparison and carries no test) to five, and every p-value in the family is corrected
against five from this date. H3 is now a single paired comparison rather than two, and
the comparator that was removed from it is not dropped but relocated to H6 with its own
refutation condition, so the number of comparisons made against the data is unchanged;
only their attribution is. The `nmap -sn` unprivileged condition in section 2's matched
configuration table serves H1, H2 and H6, and no longer serves H3.
