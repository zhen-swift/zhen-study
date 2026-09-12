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

`FINDINGS-*.md` record one task each, with the evidence for its gate.
`testbed/FINDINGS-0.1.md` records the programmable segment, and
`FINDINGS-3-driver.md` the collection driver.

## Where phase 0 stands

| | | |
|---|---|---|
| 0.1 | Programmable testbed | **Met, and rebuilt better on 2026-09-12.** Ten shaped responders spanning 1 ms to 500 ms, worst calibration error now 1.7% against a 10% tolerance, down from 5.0%. Composition matches what H6 pre-declares: three of ten answer ICMP and serve a web port, against a floor of a quarter. |
| 0.2 | Discovery-only mode | **Met.** Shipped as `netsanity scan --discovery-only`. |
| 0.3 | Characterising nmap | **Met.** Privileged nmap ran on 2026-09-12: the capture shows ARP, zero ICMP, zero TCP, recall 10/10. Privileged netsanity ran too and turned out not to be a distinct condition — no privileged engine exists — so H3 was withdrawn by the amendment of that date and `ns.disc.priv` left the matrix. Nothing remains to run. |
| 0.4 | The three oracles agree | **Met.** `testbed/gate-0.4.json`: three consecutive rounds, manifest and inventory and capture reporting the same ten addresses, no disagreements. |
| 0.5 | The harness, dry | **Met.** 0.4 is no longer a hole. 39 schema-valid records across 13 conditions, zero validation warnings. |
| 0.6 | Pilot | **Not started.** Gated on unattended root, which is the last thing outstanding. Thirteen live conditions; a block is about twelve minutes, most of it `nmap -T2`. |
| 3 | Collection driver | **Met.** `harness/collect.py`: strata, a per-stratum-per-day cap that enforces the seven-day floor, counts read from the data rather than from bookkeeping, and `caffeinate -i` held on its own pid. A stratum ran end to end and a mid-block kill left the data correct — `harness/prove_collect.py`. |

## The binary is frozen, from 2026-09-12

`study/binary-2026-09-12b` tags commit `ad09ed1`, and `netsanity` 0.4.0 is built from a
worktree checked out there — a worktree because `provenance.py` aborts a block on a
dirty tree, and a checkout somebody is working in goes dirty. `frozen-binary.json`
carries the version, the checksum and the paths in a form the harness can read;
`REPRODUCIBILITY.md` explains what the checksum does and does not prove, which matters
because this build is not byte-reproducible and the appendix has to say so.

**It is the second tag of that day and the first one measured nothing.** An earlier
`study/binary-2026-09-12` froze the code with five known defects deliberately left in
it, on the rule that a rebuild mid-collection costs the window rather than the fix.
Gate 0.3 then established that collection could not start at all — H3 had no engine to
test and unattended root is still not arranged — so the window did not exist yet and
the five were fixed, along with a sixth found while checking them.
`DEFERRED-DEFECTS.md` keeps the reasoning for all six, because what was known and when
is part of the record even after it stops being a live constraint.

`netsanity-core` and `netsanity-cli` are closed again from here. The next defect found
in either goes in `DEFERRED-DEFECTS.md` and waits, and once the first block lands the
rule is real: a rebuild then does cost every block already taken.

## A note on where measurements are taken, added 2026-09-09

The secondary testbed is a *particular* physical network — the home LAN,
`10.10.20.0/24` — and not "whatever network the laptop is on". That was implicit and
is now written down, because it is the kind of thing that is obvious until a run
happens somewhere else and the numbers look plausible anyway.

Observed while verifying the timing flags from a network that is not it. On
`192.168.1.0/24`, nothing answers ICMP: 762 probes across the /24 for zero replies,
every device in the report sourced from the kernel neighbour table, and 239 of 256
ARP entries incomplete. `/sbin/ping` fails the same way against the default gateway.
That is the ordinary shape of client isolation on a network you do not own, not a
fault to be fixed — a guest or corporate segment that forwards to the internet and
drops station-to-station traffic behaves exactly like this.

**Why it is worth a note rather than a shrug.** A run there would still produce
numbers. Unprivileged nmap falls back to TCP connect probes and would keep finding
hosts while netsanity's ICMP sweep found none, so the matched comparison would
quietly become ICMP-versus-TCP — a result that looks like a finding about the
scanners and is really a finding about the network. `provenance.py` already records
the interface and the address, so an off-LAN block is detectable after the fact; what
it does not do is refuse. Worth considering when 0.6 lands: the harness knows which
network the protocol names, and could decline to start on any other.

**The programmable testbed is unaffected**, which is why none of this touches the
critical path. Checked the same day: `netbed1` up, `192.168.64.4` answering at
0.87 ms with no loss against its calibrated 1 ms target. It is host-local vmnet over
`bridge100` and never leaves the machine. Since this phase's own amendment made the
programmable segment primary and demoted the physical one to secondary, collection
can proceed from anywhere. Only the external-validity runs need to be at home.

## The rule that matters most

The harness never computes a statistic and the analysis never touches the network.
Collection produces raw evidence, analysis produces numbers, and they meet only at an
append-only file. That separation is what lets someone rerun the analysis and get
these figures without owning this network.

A dirty git tree aborts a block. Measuring uncommitted code produces a number nobody
can reproduce.
