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

## The rule that matters most

The harness never computes a statistic and the analysis never touches the network.
Collection produces raw evidence, analysis produces numbers, and they meet only at an
append-only file. That separation is what lets someone rerun the analysis and get
these figures without owning this network.

A dirty git tree aborts a block. Measuring uncommitted code produces a number nobody
can reproduce.
