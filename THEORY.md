# Technical analysis: scope, model and theory

Written before the harness exists, so that the experiment tests predictions rather
than discovering them. Every prediction in section 13 is derived here and mapped to a
hypothesis in `PROTOCOL.md`; if the data contradicts one, the model is wrong and the
paper says so.

---

## 1. Scope

**In scope.** Host discovery on an IPv4 local segment at /24 scale: which addresses
are occupied, how quickly that can be established, and how completely. The timing
discipline that governs retransmission and the declaration of absence. Name and model
resolution by fusion of link-local advertisement protocols. Identity continuity across
randomised hardware addresses. The macOS-specific privilege and permission surface.

**Out of scope, and the paper must say so in the abstract.** Port scanning, service
and version detection, OS fingerprinting by stack behaviour, scripting engines, IPv6,
routed or enterprise topologies, internet-scale scanning, and evasion or stealth. Any
of these would be a different paper with a different baseline.

**Why the scope is drawn here.** The interesting question on a local segment is not
throughput. A /24 is 254 addresses; at any plausible probe rate the wire is idle. The
binding constraint is *latency dispersion* — how long you are willing to wait for the
slowest device before concluding the rest are absent — and that is a scheduling
problem, not a bandwidth one. Internet-scale scanners solve the opposite problem and
their techniques do not transfer.

---

## 2. Setting

Let `A` be the address set probed, `N = |A|`. Let `H ⊆ A` be the hosts actually
present and reachable during the observation window, `h = |H|`, and `D = A \ H` the
dead addresses, `|D| = N − h`.

On a consumer /24, `h` is small and `N − h` is large — the live network measured
during development gave `h = 9`, `N − h = 245`. **The cost of a sweep is dominated by
what you spend on addresses where nothing is listening**, and that observation drives
everything below.

For a host `i`, let `R_i` be its response latency, a random variable, with CDF
`F_i(t) = P(R_i ≤ t)`. Let `ℓ_i` be its per-probe loss probability. A single probe
with budget `b` elicits a usable reply with probability

    p_i(b) = (1 − ℓ_i) · F_i(b)

The empirical `R` on the development network spans roughly 14 ms to 351 ms — a
dispersion ratio of about 25× within one segment, wired and Wi-Fi mixed. **That
dispersion is the whole problem.** A homogeneous network would make this paper
unnecessary.

---

## 3. The measurement model

A sweep is characterised by:

| Symbol | Meaning |
|---|---|
| `k` | attempts per address before absence is declared |
| `c` | concurrency — probes in flight |
| `T` | a single fixed budget per attempt (the classical design) |
| `r` | retransmission budget: how long before resending (this work) |
| `t` | declaration budget: how long after the last send before declaring absence |
| `ρ` | probe rate, probes per second |
| `L` | mean time a probe occupies a slot |

The two designs differ in one respect only: whether the same number answers *when do I
resend* and *when do I give up*.

---

## 4. Analysis A — the shared budget

Under a single fixed `T`, an address with no host consumes `k · T`, because every
attempt runs to timeout. Total sweep time, with `c` probes in flight:

    T_shared ≈ ((N − h) · k · T) / c        (dead-dominated regime)

Recall is a function of the same `T`:

    recall(T) = (1/h) · Σ_{i∈H} [ 1 − (1 − p_i(T))^k ]

Because `recall` is monotone increasing in `T` and the summands saturate at different
`T` for different hosts, achieving full recall requires `T ≳ q_high`, some high
quantile of the RTT distribution across `H`. Substituting:

    T_shared ≈ ((N − h) · k · q_high) / c

**Every dead address pays the slowest host's tail, `k` times.** This is not an
implementation flaw in any particular scanner; it is a consequence of using one number
for two decisions. Fixed timing templates are points on this curve, chosen in advance.

Sanity check against the development network: `N − h = 245`, `k = 3`,
`q_high ≈ 600 ms`, `c ≈ 240` gives ≈ 1.8 s, which matches the 1.2–2.1 s observed
before the split was implemented. The model is at least not obviously wrong.

---

## 5. Analysis B — decoupled budgets

Separate the two decisions.

*When do I resend?* A lost frame costs one packet to replace. Resending early is cheap
and the only penalty is a duplicate probe, so `r` should be small — driven by a **low**
quantile `q_low` of observed RTTs, tightening as the sweep learns the network.

*When do I declare absence?* This needs the tail, but it is asked **once**, at the end,
and it overlaps every address simultaneously rather than being paid per address.

    T_split ≈ ((N − h) · k · q_low) / c  +  t,    t ≳ q_high

The speedup, in the regime where the first term dominates:

    T_shared / T_split  →  q_high / q_low

**The advantage is exactly the RTT dispersion ratio.** On a homogeneous segment it
vanishes; on a segment mixing gigabit Ethernet with 2.4 GHz Wi-Fi and sleeping IoT
devices it is large. With the measured `q_low ≈ 49 ms` and `q_high ≈ 600 ms` the
predicted ratio is ≈ 12×, reduced by the additive tail to roughly the 3–6× actually
observed.

---

## 6. The enabling condition

The split is only sound if a reply arriving after its own attempt's window has closed
is still attributed to the probe that caused it. Otherwise shortening `r` converts slow
hosts into missed hosts and the technique degenerates into "use a shorter timeout",
which trades recall for speed rather than improving both.

Two requirements:

1. **Per-transmission identity.** Each transmission carries a unique token, so a late
   reply is attributable to the exact attempt it answers. Sequence-number reuse breaks
   this — at /16 scale a 16-bit field wraps and attribution silently becomes wrong,
   which is worse than losing it.
2. **Expired probes stay matchable.** A probe whose window has passed remains in the
   pending table until the declaration budget expires, not until its own window does.

Given both, a late reply is *evidence of presence* rather than a stray. This is the
mechanism the paper contributes; the budget split is the consequence.

**Corollary, and it is testable.** Karn's rule — discard RTT samples from retransmitted
probes, because you cannot tell which transmission a reply answers — is unnecessary
under per-transmission tokens, since the ambiguity it exists to resolve does not arise.
Retaining the conservative discard costs estimator responsiveness on lossy links. This
is a small, sharp, checkable claim about a forty-year-old rule in a context its authors
did not target.

---

## 7. Concurrency

Little's Law fixes the relationship between the three quantities that are usually
guessed at:

    c = ρ · L

Concurrency is not a tuning constant. To sustain a probe rate `ρ` where each probe
occupies a slot for mean time `L`, you need `ρL` in flight. Since decoupling reduces
the effective `L` from `q_high` toward `q_low`, either the same `c` sustains a higher
rate, or the same rate needs less `c` — the second mattering on macOS, where the soft
descriptor limit is 256 and the real ceiling is `kern.maxfilesperproc`.

Bounding `c` also bounds the latency tail, which is the QJUMP result applied one layer
down: an unbounded fan-out does not finish sooner, it makes the slowest probe slower.

---

## 8. Absence as a decision

Declaring an address empty is accepting a null hypothesis after `k` failed trials. The
error probability is

    P(false absence for host i) = ∏_{j=1..k} (1 − p_i(b_j))

and expected recall follows directly. Two consequences the experiment should see:

- The marginal value of attempt `k+1` is large where `ℓ` is high (Wi-Fi, sleeping
  devices) and near zero where it is low (wired). A uniform `k` is therefore wasteful
  at one end and insufficient at the other — which suggests per-host `k`, an extension
  this paper identifies but does not implement.
- Recall cannot be reported without a stated observation window. A device asleep for
  the whole window is not a miss, and any study that cannot distinguish the two is
  measuring its own oracle rather than the scanner. Hence the passive capture in the
  protocol.

---

## 9. Naming as evidence fusion

Name resolution is not a lookup but an arbitration among sources of differing trust:
mDNS, SSDP, NetBIOS, reverse DNS, and within mDNS a per-service-type quality rank.

Model the candidate set as a totally ordered set under `(source priority, rank)`.
Resolution is then `min()` — an operation, not a procedure — which makes the cascade
associative, order-independent and trivially testable. Ties must break deterministically
on a stable field, or the winner varies with network arrival order and the same device
appears to be renamed between runs.

**Losing candidates are retained deliberately.** They are the explanation for the name
chosen, and discarding them makes the system unaccountable to its user. This is a
design claim, not a performance one, and the paper presents it as such.

---

## 10. Identity under address randomisation

Randomised hardware addresses are now the common case on consumer networks, not the
exception — six of nine devices on the development network. Keying identity on the MAC
therefore manufactures a new device on every rotation and destroys the history the tool
exists to provide.

Model a host as an equivalence class over identifiers of differing stability: a
universally administered MAC, an mDNS instance name, a DHCP hostname, a randomised MAC,
an IP lease. Weight each by stability; resolve by strongest match; merge classes when
two identifiers resolve to different classes. This is union-find with weighted keys.

The essential asymmetry: **a false merge is unrecoverable and a false split is not.**
Two devices merged into one lose their separate histories irretrievably; two records
that should be one can be joined later when better evidence arrives. The loss function
is asymmetric, so the decision threshold must be biased toward splitting — accept a
weak-key match only when no stronger evidence contradicts it.

Note also that stability of the identity key and confidence in the identification are
*different quantities*, computed from different inputs, and conflating them is the
error the design phase of this project actually made. A rotating-MAC laptop with a
clean Bonjour name is well identified and weakly keyed; a router named only from its
model string is the reverse.

---

## 11. Platform surface

Three macOS facts shape the design and none of them generalise:

**Unprivileged ICMP.** `socket(AF_INET, SOCK_DGRAM, IPPROTO_ICMP)` succeeds for an
ordinary user. Full host discovery therefore needs no root, where a scanner assuming
raw sockets must either escalate or fall back to TCP connect probes against a small
port set — which is a strictly weaker signal, since a host may answer ICMP and no TCP
port. The kernel rewrites the identifier field, so replies must be matched on sequence
and source, and the checksum is the application's responsibility.

**Local Network permission.** Denial returns zero results rather than an error. A
scanner cannot query the grant, so denial can only be *inferred* — the signature is an
empty ICMP sweep against a populated neighbour table. Any user-facing claim about it
must be hedged, and a study must assert the permission state per run or its recall
numbers are meaningless.

**Descriptors and BPF.** The soft `RLIMIT_NOFILE` is 256 and the hard limit reports a
value the kernel will not honour; `kern.maxfilesperproc` is the real ceiling. `/dev/bpf`
nodes are exclusive-open, so a packet capture — including the study's own oracle — can
deny the privileged engine the resource it needs. The harness must record this rather
than let it silently degrade a condition.

---

## 12. Related work, and where this sits

**Transport RTO estimation** (Jacobson; Karn and Partridge) gives the smoothed-RTT and
mean-deviation estimator and the retransmission-ambiguity rule. We apply it to
discovery probing rather than a connection, and section 6 argues the ambiguity rule is
unnecessary here.

**Internet-scale scanning** (ZMap, masscan) is stateless and optimises send rate at
constant timeout — the right design when the address space is enormous and per-host
state is unaffordable. Local discovery inverts both assumptions: the space is tiny and
per-host state is nearly free, which is what makes per-host adaptation available to us
and not to them.

**Fixed timing templates** (nmap `-T0`…`-T5`) are the baseline: a discrete set of
points on the section 4 curve, chosen before the network is observed. Our claim is that
adaptation dominates the whole set, not that any individual template is badly chosen.

**Timer data structures** (Varghese and Lauck) make expiry management O(1), which
matters once each of tens of thousands of probes carries its own deadline rather than
sharing a global one — the split budget is only affordable with the right timer.

**Bounded in-flight work and tail latency** (QJUMP) supplies the concurrency argument
of section 7.

**Stack specialisation** (Marinos, Watson and Handley) is the systems backdrop:
syscall overhead, buffering and copies dominate at these rates, and batching readiness
notification is the same principle at the syscall boundary.

**Link-local naming** (mDNS/DNS-SD, SSDP, NBSTAT) is prior art we consume rather than
extend; the contribution is the arbitration model of section 9.

**MAC address randomisation** literature motivates section 10; our contribution is the
asymmetric-cost framing of the merge decision.

---

## 13. Predictions

Each is derived above, each is falsifiable, each maps to a hypothesis in the protocol.

**P1.** The speed advantage over any fixed template is proportional to RTT dispersion
`q_high / q_low`. Stratify runs by measured dispersion; the advantage should grow with
it and vanish on a homogeneous segment. *(H2. A flat relationship refutes the
mechanism even if the mean advantage is large.)*

**P2.** Recall is invariant to the budget split, given per-transmission tokens and
matchable expired probes. *(H5. A recall drop means straggler attribution is broken,
not that the technique is wrong.)*

**P3.** nmap's templates trace a monotone speed/recall frontier; adaptation lies
strictly below-right of every point. A single non-dominated nmap point refutes H2.

**P4.** Peak in-flight probes track `ρ · L` as Little's Law predicts, and the split
reduces `L` and therefore the concurrency needed for a given rate. *(Secondary metric.)*

**P5.** The marginal recall gain from attempt three is significant on Wi-Fi hosts and
insignificant on wired ones, motivating per-host `k` as future work.

**P6.** Unprivileged netsanity recall ≈ privileged netsanity recall, while unprivileged
`nmap -sn` recall falls below both for hosts answering ICMP but no probed TCP port.
*(H3. A specific asymmetry, not a general claim about privilege.)*

**P7.** Total sweep time is approximately `((N−h)·k·q_low)/c + t`. Fit the model to
observed times; a poor fit means the cost model is wrong and section 5 must be revised
before the result is claimed.

---

## 14. Assumptions, and where they break

Probe outcomes are treated as independent across attempts — false under correlated
loss such as a Wi-Fi power-save cycle, which makes `k` attempts worth less than the
model says. Response latency is treated as stationary within a run — false when
another host begins a large transfer. The dead-dominated regime assumes `h ≪ N`, which
holds on consumer /24s and fails in a dense enterprise VLAN where the tail term begins
to dominate and the advantage shrinks. Ground truth is assumed knowable, which is why
three oracles are used and disagreements are excluded rather than resolved.

Each of these belongs in the paper's threats-to-validity section verbatim, not
softened.

---

## 15. Notation

`A, N` address set and its size · `H, h` hosts present and count · `D` dead addresses ·
`R_i, F_i` host latency and its CDF · `ℓ_i` per-probe loss · `p_i(b)` reply probability
within budget · `k` attempts · `c` concurrency · `ρ` probe rate · `L` mean slot
occupancy · `T` shared budget · `r` retransmission budget · `t` declaration budget ·
`q_low, q_high` low and high quantiles of observed RTT.

---

## 16. Simulation results — three corrections to this document

A mechanism-level simulator (`Study/sim/`) was written from the probe/wait/resend/
declare loop, deliberately not from the closed form in section 5, and run before any
measurement. It contradicts this document in three places. The corrections are recorded
here rather than silently applied, because the original claims are what the protocol
was frozen against.

### C1 — The closed form has the wrong shape at realistic scale

Section 5 treats sweep time as continuous in `c`. The simulator overshoots that formula
by roughly 63% for the shared policy while matching it to within 2% for the split
policy. The cause is discretisation: with `N·k ≈ 762` probes and `c = 240`, a sweep is
three to five *waves*, not a continuous flow, and retries serialise into additional
waves. The correct form is

    T_shared ≈ ⌈N·k / c⌉ · T

with the ceiling mattering precisely because the wave count is small. The split policy
matches the continuous form because its per-wave cost is small enough that
discretisation is negligible against the additive tail. **Section 5's formula stands as
an asymptotic statement and fails as a predictor at /24 scale.** P7 must fit the wave
form.

### C2 — Speedup is not the dispersion ratio; it saturates

Section 5 claims the advantage equals `q_high / q_low`. It does not. Both policies grow
linearly in `q_high` — the shared one through `T`, the split one through the tail `t` —
so the ratio is asymptotically bounded, not proportional. Simulated:

| dispersion | 1× | 2× | 4× | 7× | 12× | 20× | 41× |
|---|---|---|---|---|---|---|---|
| speedup | 1.00× | 1.69× | 2.53× | 3.21× | 3.77× | 4.18× | 4.55× |

The advantage is real, grows monotonically with dispersion — which is what P1 actually
predicted — and saturates near the wave count for dead addresses rather than at the
dispersion ratio. **P1's direction survives; its magnitude claim does not.** The paper
must state the bound, because a reader who applies the original claim to a 40×
dispersion network and expects 40× will be disappointed by a factor of nine.

### C3 — Strict domination fails at the extreme recall end

P3 claimed the split policy dominates every fixed budget. Under 15% loss and 12×
dispersion it dominates the practical frontier but not the endpoint: the most generous
fixed budgets reach recall 0.996 while the split policy saturates at 0.993, at four to
six times the wall clock. Extending the declaration window does not close the gap —
recall plateaus at 0.9926 whether the tail is 450 ms or 3 s — so the residue is not a
timing artefact. Both policies are bounded above by `1 − ℓ^k = 0.9966`; the fixed
policy reaches that ceiling and the split policy lands just under it, and the mechanism
for that 0.4% is not yet understood and must be run down before the claim is made.

The check also exposed a flaw in how domination was defined: a fixed budget of 50 ms is
technically non-dominated because it finishes 3 ms sooner than anything else — at
recall 0.109. **P3 must be restated over a region of interest** (recall ≥ 0.95, say),
because a Pareto test without one rewards configurations that answer instantly by
finding nothing.

### What this changes about the study

Nothing in the protocol's design, and everything about what the paper may claim. The
mechanism is sound and the direction of every prediction survives. Three magnitude
claims were wrong, and they were wrong in the direction that flatters us — which is
exactly the kind of error a reviewer looks for first, and exactly why the simulator was
written before the testbed rather than after the data.

The simulator is not evidence about the real system. It is evidence about the *model*,
and its value is that it refuted the model cheaply. The real measurement still has to
happen, and it now has a corrected cost form to fit and a properly-scoped domination
test to run.

---

### The full study, and five further corrections

The three corrections above came from two scratch scripts. Those scripts have since
been replaced by a tested simulator (`Study/sim/mechanism.py`), a separate transcription
of the cost model (`Study/sim/model.py`) that the simulator never imports, a condition
grid (`Study/sim/conditions.py`), and an analysis half that reads only the CSV
(`Study/analysis/`). 61,488 sweeps across nine regimes, plus 40,000 more for the C3
diagnosis. Twenty-six tests run before any number was read.

The new simulator reproduces the scratch script sweep for sweep when configured the way
the scratch script was configured, which is the only reason its disagreements elsewhere
are worth anything. Both differences are named parameters, not silent rewrites:
`tie_break` and `release_on_reply`.

Corrections C4 through C8 follow. C4 and C6 withdraw parts of C1–C3; that is what
happens when a scratch result is checked properly, and the withdrawal is recorded here
rather than by deleting the text that was wrong.

### C4 — C3's recall gap does not exist. It was the replicate count.

C3 recorded the split policy saturating at 0.9926 against a ceiling of
`1 − ℓ³ = 0.9966`, called the gap stable under a widening declaration window, and said
the mechanism was not understood. There is no mechanism. The gap is two hosts.

Running the **unmodified scratch script** at its own 60 replicates reproduces C3
exactly: shared 0.9963, split 0.9926, on 540 host observations each. Running **the same
code** at 2,000 replicates gives 0.9966 for both policies — the ceiling, to four
decimal places, on 18,000 observations each. The gap did not narrow because the
declaration window widened; it disappeared because the sample got large enough to see
that it was never there. `frontier.py` reused the seeds `1000+i` and `7000+i` for every
budget, so the same two unlucky hosts appeared in every column and a fluctuation of
1.5 standard errors looked like a stable plateau.

The new simulator agrees, and says more. Across 2,000 replicates at each of five
budgets from 630 ms to 5 s, both policies recover 0.9968 [0.9959, 0.9976], and the
paired difference between them is exactly zero in **every one of 2,000 replicates at
every budget** — not close to zero, zero. Of 1,140 missed hosts, all 1,140 are
categorised `all_transmissions_lost`, and **none** had a reply that arrived after the
last matchable instant. Nor is it the slot-release rule: holding a slot to its budget
and releasing it on reply give identical recall to the last digit.

**P3's endpoint claim stands.** C3 should not have been written, and the paper must not
carry it. The general lesson is the one the protocol already states for the real study
and the simulation had not yet learned: a difference of two observations in 540 is not
a finding, and reusing seeds across conditions turns Monte Carlo noise into something
that looks like structure.

### C5 — The domination test, restated over a region of interest

As C3 noted, a Pareto test with no region of interest rewards a scanner for finding
nothing. Both frontiers, at 12× dispersion and 15% loss, 300 replicates per point:

*Without* a region of interest, exactly one fixed budget survives — `T` = 50 ms, which
finishes in 0.200 s at recall **0.111**, six milliseconds ahead of the fastest split
configuration. Every other fixed budget is dominated.

*Within* recall ≥ 0.95, seven of the ten fixed budgets and five of the nine split
configurations fail the requirement outright and are not competitors at all. Of the
three fixed budgets that qualify, **all three are dominated** — `T` = 630 ms takes
2.520 s at recall 0.9956, against a split configuration reaching the same recall in
0.784 s. **P3 holds over the region of interest and is vacuous outside it.** The paper
must state the region before the frontier, not after.

### C6 — C2's table is the right law with the wrong constant, and the constant was a bug

The speedup does saturate, as C2 says. It does not saturate near "the wave count for
dead addresses" as a vague ceiling: it follows

    speedup  =  W·d / (W − 1 + d),        W = ⌈N·k / c⌉,   d = q_high / q_low

exactly. Over dispersions 1× to 80× at the reference cell the largest deviation between
this expression and the simulated median is **0.0000** — the law is not fitted, it is
the ratio of two closed forms that each hold to the microsecond.

C2's recorded table is *the same law with W = 5*:

| dispersion | 1× | 2× | 4.1× | 7.1× | 12.2× | 20.4× | 40.8× |
|---|---|---|---|---|---|---|---|
| C2, as recorded | 1.00× | 1.69× | 2.53× | 3.21× | 3.77× | 4.18× | 4.55× |
| `5d/(4+d)` | 1.00× | 1.69× | 2.53× | 3.21× | 3.77× | 4.18× | 4.55× |
| `4d/(3+d)`, measured | 1.00× | 1.60× | 2.29× | 2.80× | 3.20× | 3.48× | 3.73× |

But `⌈254·3/240⌉ = 4`, not 5. The scratch simulator was spending a whole extra budget
on a single straggler, and the answer to the question that was asked of the fixed
policy — whether the discrepancy is an artefact of how it releases slots — is **yes,
partly**, though the recall gap of C3 was not. Two independent implementation choices
cause it, and *either one alone* is enough to prevent it:

1. **Ordering simultaneous timeouts by address rather than by the order the probes went
   out.** When a whole wave of budgets expires at once, the retransmission queue is
   refilled in the order the timeouts are processed. Address order scrambles launch
   order, and an address that started late can be pushed behind the backlog and slip a
   wave; its remaining transmissions then cannot fit.
2. **Holding a slot until its budget expires even after the host has answered.**
   Releasing on reply returns a handful of slots mid-wave, which is enough slack to
   absorb the slip.

The scratch script made both choices. With both, 47% of visiting orders spend five
waves instead of four; with either one fixed, **0%** do. Its own 40 replicates split
21/19 in favour of the five-wave mode, so its median reported 5·T and every speedup in
C2's table is inflated by the resulting 25%.

Two consequences. For the paper: the asymptote is the wave count `W`, and raising `W`
raises the ceiling — swept from /24 to /16 at constant density and constant
concurrency, the same configuration goes from 3.20× to **11.74×**, against 11.84×
predicted, because `W` grows to 820 and the binding constraint becomes the dispersion
itself rather than the wave count. C2's "saturates near 4.5" is an artefact of one
address-space size. For the implementation: netsanity's retransmission queue must be
FIFO in launch order and must free a slot the moment a reply matches. Neither is a
performance nicety; together they are a quarter of the sweep.

### C7 — C1's wave form is exact for the fixed policy, and one interval too long for the split policy

C1 is right about the shape and can be sharpened to an equality. In the dead-dominated
regime the wave form `⌈N·k/c⌉·T` predicts the fixed policy's sweep time to within one
microsecond in **97.7%** of rows — the exceptions being exactly the deliberately
mis-scheduled arms of C6 — while sections 4 and 5 as written predict **0%** of rows and
run 30.6% low.

C1's additive counterpart for the split policy is wrong by a fixed amount. The residual
of `⌈N·k/c⌉·r + t` is not scattered: it is **exactly −r**, with a median of −1.000000
retransmission intervals. The scanner never waits out the final wave's interval,
because once the last probe of the sweep is away the only thing left to wait for is the
declaration window, and `t` subsumes `r`. The correct form is

    T_split ≈ (⌈N·k / c⌉ − 1) · r + t

which predicts **94.0%** of split rows to within a microsecond. The coefficient was not
estimated from a fit; it was read off a residual that was constant.

Both forms have a stated domain, and the study locates its boundary. They hold while
live hosts are rare enough not to free slots early — section 14's `h ≪ N`. The first
density at which the fixed policy beats its own wave form by more than 1% is
**h = 14 on a /24 with c = 240** (5.5%), which is `N − c`, the number of addresses that
do not fit in the first wave; at c = 64 it is h = 20 (7.9%). Beyond that the wave form
over-predicts, by up to a factor of 2.3 when every address is live. **P7 has a form to
fit and a domain to check, and the paper must report the density of its testbed
alongside the fit or the fit means nothing.**

### C8 — Independence is not a harmless assumption. It is where the technique is paid for.

Section 14 lists per-transmission independence as an assumption and names Wi-Fi power
save as a case where it is false. Simulated against a two-state loss process with the
same *marginal* rate of 0.15 but outages of a given mean duration, the speed advantage
is completely unaffected — 3.20× at every outage length — and recall is not:

| mean outage | independent | 20 ms | 50 ms | 100 ms | 250 ms | 500 ms | 1 s | 2 s |
|---|---|---|---|---|---|---|---|---|
| fixed | 0.9967 | 0.9944 | 0.9933 | 0.9983 | 0.9950 | 0.9844 | 0.9550 | 0.9233 |
| split | 0.9967 | 0.9967 | 0.9739 | 0.9406 | 0.9078 | 0.8833 | 0.8650 | 0.8628 |

The mechanism is the technique's own design. The split policy packs its three
transmissions into roughly 150 ms, so any outage longer than that takes all three; the
fixed policy spreads the same three over `3·T ≈ 1.9 s` and usually straddles the
outage. The crossover sits at the retransmission interval `r` = 51 ms: at outages of
20 ms the split policy is still the better of the two, and by 50 ms — one interval —
it has already fallen two points behind and keeps falling.

**H5 as stated — "reduces total sweep time without reducing recall" — is false under
correlated loss**, at a cost of nine recall points at a one-second outage. This is not a
reason to abandon the technique; it is a reason to scope the claim, to dither the
retransmission interval so that k transmissions cannot all land inside one outage, and
to make burstiness a measured covariate of the real study rather than an assumption.
The passive capture in PROTOCOL.md section 3 already collects what is needed to
estimate it.

### What the simulation cannot address

It has nothing to say about H1, H3 or H4: it contains no nmap, no privilege model, no
naming protocols and no real hosts. It says nothing about whether netsanity's Swift
implementation achieves the concurrency it configures, whether macOS delivers ICMP
replies at the rate assumed, or whether real RTT distributions are log-uniform — the
last of which every result here is conditioned on and none of which the simulation can
check. It is evidence about the model, not about the system, and its whole value is
that it refuted three parts of the model in an afternoon rather than after seven days
of collection.

---

### C9 — C8's fix, its price list, and what H5 may now claim

C8 named the defect and proposed dithering the retransmission interval. Dither is not
the fix; spacing is. The measurements below are `e9_spacing` in `Study/data`, at a
fixed 15% marginal loss rate with only the *distribution of that loss in time* varying,
and they are regenerated by `analysis/spacing_report.py`.

**The cost of spreading is additive once, and only where concurrency covers the address
space.** Delaying the final transmission by Δ delays the sweep by Δ — not by Δ per
address, which is what makes the fix affordable at all. But that holds only while
`c ≥ N`. As written, a probe occupies its concurrency slot until its replacement is
due, so a longer gap holds a slot longer and a slot-limited queue multiplies the cost:
measured at 1.00× the added span on a /24 with `c = 256`, 2.00× at `c = 240`, 4× on a
/22, 15.4× on a /20 and **247× on a /16**. Releasing the slot after the base interval
instead — a slot bounds probes *awaiting a reply*, and an address waiting for its next
scheduled transmission has nothing in the air — takes it back to 1.00× on a /24 and to
**zero** at every larger prefix, where the spread fits entirely inside time the sweep
was already spending. Any implementation of this technique must decouple the two or the
fix does not scale.

**Bought unconditionally the fix fails C8's own non-negotiable.** A fixed 400 ms late
gap recovers 6 to 8 recall points but adds 375 ms to a 300 ms sweep, which is paying for
correlated loss on every network including those that do not have any. It leaves
independent-loss recall untouched and independent-loss *speed* badly dented, and a
change that trades speed for nothing on a clean network is a different trade rather than
a fix.

**Bought out of the tail window it is free.** The sweep already sits idle for the whole
tail budget, and where that budget is its floor rather than the network's own tail, most
of it is slack. Scheduling the final transmission into that slack — and anchoring the
declaration instant to the last *tight* transmission, so the sweep stops when it always
did — costs nothing:

| | indep | 50 ms | 100 ms | 250 ms | 500 ms | 1 s | 2 s | sweep |
|---|---|---|---|---|---|---|---|---|
| three tight | 0.998 | 0.936 | 0.911 | 0.883 | 0.873 | 0.855 | 0.848 | 0.300 s |
| spread into tail | 0.998 | 0.983 | 0.968 | 0.932 | 0.905 | 0.879 | 0.861 | **0.275 s** |
| late 400 ms, paid | 0.998 | 0.986 | 0.984 | 0.963 | 0.933 | 0.904 | 0.870 | 0.675 s |
| fixed budget | 0.998 | 0.996 | 0.994 | 0.976 | 0.942 | 0.910 | 0.877 | 0.750 s |

Under periodic outages — the shape Wi-Fi power save actually has, a duty cycle rather
than a memoryless one — the free schedule recovers more: +8.8 points at a 100 ms outage
and +10.7 at 250 ms. The sweep is 25 ms *shorter* than before, because anchoring on the
last tight transmission removes one retransmit interval from the end.

**Where the tail budget is earned rather than floored, the fix declines and says so.**
On a network whose slowest host answers in 600 ms the slack is zero, the schedule is
identical to the old one, and the artifact reports `spread_budget_millis: 0`. C8 is not
closed there without paying the 349 ms in the table above. That is the honest boundary
of the repair and the paper must state it rather than generalising the free case.

**H5 may now claim, bounded.** "Separating the retransmission budget from the
absence-declaration budget reduces total sweep time without reducing recall" is
defensible **on a network whose tail budget is its floor and whose outages are shorter
than the slack that floor provides** — roughly 200 ms on the cell measured. Beyond that
outage length recall still falls below a fixed budget's, by 3 points at 500 ms and 5.5
at 2 s. The unbounded form of H5 remains false and should not be restored.

Two implementation defects were found by measuring rather than by simulating, and both
are worth recording because a simulator would not have produced either:

1. **The spread must be bought from measured slack, not from the estimators' initial
   guesses.** Before any reply arrives, the tail budget and the reply allowance are both
   defaults, and their difference is not slack. Freezing on them spread the schedule by
   280 ms on a network with none to spare, and the artifact reported a spread of zero
   while the sweep had actually used one.
2. **Spreading has a feedback path into the tail estimate.** A longer transmit phase
   collects more late samples, which raises srtt + 4·rttvar, which lengthens the wait
   that follows. Measured on 10.10.20.0/24 as 90 to 230 ms of discovery time bought for
   nothing. The guard is C8's own premise: spread only when it would materially widen
   the schedule, which on a network whose retransmit interval has risen toward its
   ceiling it does not, because three transmissions 150 ms apart already span 300 ms.
