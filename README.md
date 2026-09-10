# The study

A measurement study of what netsanity's sweep scheduling actually buys, against
`nmap -sn` as the comparator. It is a separate deliverable from the scanner, kept in
the same repository because the scanner is the thing under measurement and a study
that drifts from the build it measured is worth nothing.

**Nothing here has produced evidence yet.** Phase 0 is the apparatus, and collection
does not begin until every one of its gates is met.

## Read in this order

| | |
|---|---|
| `THEORY.md` | Why sweep scheduling should matter at all: the model, what it predicts, and the eight corrections that survived contact with a simulator. |
| `SIMULATION.md` | The simulator that tests the model. **Evidence about the model, not about netsanity** — the distinction is the whole reason it is a separate document. |
| `PROTOCOL.md` | The study design: hypotheses, the matched configuration, exclusion rules. **Frozen.** Amendments are appended and dated rather than edited in, which is why its sections keep their numbers when the rest of the repository's do not. |
| `PHASE0.md` | The six tasks that make the study executable, each with a gate that must be met before the next begins. |
| `HARNESS.md` | The apparatus: what collects, what analyses, and the rule that keeps them apart. |

`FINDINGS-*.md` record one phase-0 task each, with the evidence for its gate.
`testbed/FINDINGS-0.1.md` records the programmable segment.

## Where phase 0 stands

| | | |
|---|---|---|
| 0.1 | Programmable testbed | **Met.** Ten shaped responders, worst error 5.0% against a 10% tolerance. Needs re-planning for the H6 amendment before it is rebuilt. |
| 0.2 | Discovery-only mode | **Met.** Shipped as `netsanity scan --discovery-only`. |
| 0.3 | Characterising nmap | **Partial.** The unprivileged half is established three ways. `sudo nmap -sn` has never run and no capture was taken — blocked on a credential, not a method. |
| 0.4 | The three oracles agree | **Not started**, deliberately: `oracles.py` is shaped by a testbed decision that is still open, and a live block refuses to start without it. |
| 0.5 | The harness, dry | **Met**, with 0.4 as a declared hole. 36 schema-valid records, zero validation warnings. |
| 0.6 | Pilot | **Not started.** Gated on 0.4. |

## A third blocker, found 2026-09-09: this machine answers no ICMP

`PHASE0.md` lists two outstanding decisions, unattended root and keeping the host
awake. There is a third, and it is not a decision — it is the state of the machine.

**Nothing on the local subnet answers ICMP from this host.** Not netsanity: 762
probes across a /24, zero replies, every device in the report sourced from the kernel
neighbour table and the run carrying the "no host answered a probe" degradation. Not
`/sbin/ping` either, which fails identically against the default gateway — a host
that is demonstrably alive, since this machine reaches the internet through it. A
system tool failing the same way is what says this is the machine rather than the
scanner.

Two things changed since the 2026-09-04 measurements in `data/`, which recorded four
to twelve ICMP replies per run and therefore worked:

- The host has moved from `10.10.20.0/24` to `192.168.1.0/24`.
- An IPsec tunnel is up (`ipsec0`, `10.1.15.176`) and holds a default route.

The tunnel is the obvious suspect and has not been confirmed as the cause. What is
confirmed is the effect, and it matters more than the mechanism: **a pilot run today
would measure a network on which no host answers ICMP**, and every hypothesis that
turns on round-trip dispersion would be measuring the absence of round trips. The
comparison against `nmap -sn` would still run and would still produce numbers, which
is what makes this dangerous rather than merely inconvenient — unprivileged nmap
falls back to TCP connect probes and would keep finding hosts while netsanity's ICMP
sweep found none.

**The programmable testbed is unaffected, and that is what saves phase 0.** Checked
the same day: `netbed1` brought up, and `192.168.64.4` answers at 0.87 ms with no
loss, against its calibrated 1 ms target. The segment is host-local vmnet over
`bridge100` rather than the physical LAN, so whatever is eating ICMP on `en0` does not
reach it.

That matters because the programmable segment is the **primary** testbed — the
physical one was demoted to secondary in this phase's own amendment. So collection can
proceed on the primary while the host's ICMP problem is unresolved. What cannot
proceed is anything on the physical LAN, which includes the external-validity runs the
secondary testbed exists for.

## The rule that matters most

The harness never computes a statistic and the analysis never touches the network.
Collection produces raw evidence, analysis produces numbers, and they meet only at an
append-only file. That separation is what lets someone rerun the analysis and get
these figures without owning this network.

A dirty git tree aborts a block. Measuring uncommitted code produces a number nobody
can reproduce.
