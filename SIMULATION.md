# The simulation study

A mechanism-level simulation of the two sweep policies, run before the physical testbed
exists, to find out which of THEORY.md's claims survive contact with something that
does not know the closed form.

It is not evidence about netsanity. It is evidence about the *model*, and its value is
that a model can be refuted in an afternoon where a testbed takes seven days.

## The rule the whole thing rests on

`sim/mechanism.py` is written from the mechanism — probe, wait, resend, declare — and
never from the cost formula in THEORY.md sections 4 and 5. It does not import
`sim/model.py`, it names no quantity from it, and no constant in it was chosen to make
a prediction come out right. If it were tuned toward the formula, agreement between the
two would prove algebra.

`sim/model.py` is the formula, transcribed, and exists only to be compared against
simulated output. Where they disagree, the disagreement is reported. The simulator is
never adjusted to match the model; that direction of fitting is the failure mode the
separation exists to prevent.

The same separation HARNESS.md imposes on the real study applies here: **code that
produces evidence never computes a statistic, and code that computes statistics never
produces evidence.** `sim/` writes CSV. `analysis/` reads CSV and imports nothing from
`sim/`. Every number in the write-up is recomputed from `data/`.

## Layout

```
sim/
  mechanism.py       the simulator; standard library only, no model, no statistics
  model.py           THEORY.md's closed forms, transcribed, plus the two corrections
  conditions.py      the grid, as data: nine regimes, 168 conditions
  run_sim.py         produces data/sim_results.csv; one row per replicate, no aggregation
  diagnose_c3.py     instrumented miss attribution for correction C3
  test_mechanism.py  26 tests; nothing below is worth reading until they pass
  sweep_sim.py       the original scratch simulator, kept unmodified
  frontier.py        the original scratch frontier script, kept unmodified
analysis/
  load.py            the only module that opens a file; validates schema versions
  pareto.py          the frontier and the domination test, with a region of interest
  report.py          regenerates every number the write-up cites
  c3_report.py       the answer to correction C3
  figures.py         every figure, PNG and PDF, greyscale-legible, two-column sized
data/                the CSVs, and a README describing every column
figures/             fig1 .. fig7, .png and .pdf
```

The two scratch scripts are kept rather than deleted, and are not dead weight: the
strongest validation available without a testbed is that the new simulator reproduces
the old one sweep for sweep when configured the way the old one was configured. That is
a test (`AgreesWithTheScriptItReplaces`), and the two differences between them are named
parameters — `tie_break` and `release_on_reply` — not silent rewrites. `diagnose_c3.py`
also runs the scratch code directly, at its own replicate count and at a much larger
one, because the answer to C3 turned out to be a property of the replicate count.

## Running it

```
cd Study
python3 -m venv .venv && .venv/bin/pip install numpy pandas matplotlib   # analysis only
cd sim  && python3 -m unittest test_mechanism -v                          # ~5 s
         python3 run_sim.py                                              # ~50 s
         python3 diagnose_c3.py                                          # ~35 s
cd ../analysis && ../.venv/bin/python report.py
                 ../.venv/bin/python c3_report.py
                 ../.venv/bin/python figures.py
```

The simulator needs no third-party package; only the analysis does. Everything is
deterministic — the same command produces byte-identical output, which is itself one of
the tests.

## What the simulator models

A sweep over `N` addresses of which `h` are live, with at most `c` probes in flight. A
probe holds a slot from transmission until it is closed, by a matching reply or by its
wait budget expiring. An unfound address whose probe closed without a reply is
re-queued, to at most `k` transmissions.

**fixed** — one budget `T` serves both roles, and a reply arriving after its own
transmission's window has closed is unattributable and discarded.

**split** — retransmission interval `r`, sized from the fast end of the RTT
distribution; absence is not declared until `t` after the *last* transmission of the
sweep. Per-transmission identity (THEORY.md section 6) is what makes a reply arriving
long after its own `r` window still attributable.

Both policies are handed identical populations and identical loss realisations, indexed
by (address, transmission) or by wall-clock instant rather than by the order a
particular policy consumes random numbers, so every paired comparison is exact.

Loss is either independent per transmission, or a two-state process correlated in
wall-clock time with the same marginal rate — the Wi-Fi power-save shape that
THEORY.md section 14 admits breaks the independence assumption.

## What is tested before any number is read

Concurrency is never exceeded at any instant, reconstructed from the open and close
instants rather than read off the simulator's own counter. No slot leaks. With zero loss
and zero dispersion both policies find every host and send identical probes at identical
instants, and dispersion of exactly 1 confers no speed advantage. A host is found only
if some transmission of it survived, and pooled recall sits at `1 − ℓ^k` within four
standard errors and approaches it as budgets grow. Recall is pathwise monotone in the
budget, in the declaration window and in the attempt count. A host slower than every
budget is never found — and one just inside it always is, so the first result is the
budget binding rather than the simulator finding nothing. Probes sent never exceed
`N·k`. The same seeds reproduce byte-identical CSV. And the simulator reproduces the
script it replaces, exactly, when configured the way that script was configured.

## The nine regimes

| id | what varies | why it cannot be done on a testbed |
|---|---|---|
| `e1_dispersion` | RTT spread, 1× to 80× | you cannot order a household to have 80× dispersion |
| `e2_frontier` | ten fixed budgets against nine split configurations | 5,700 sweeps at one cell |
| `e3_density` / `e3b_density_c64` | 1 to 254 live hosts, at two concurrency levels | you cannot put 254 devices on a /24 twice |
| `e4_scale` | /24 through /16 at constant density | there is no /16 |
| `e5_bursty` | outages of 20 ms to 2 s at fixed marginal loss | you cannot dial a device's power-save cycle |
| `e6_attempts` | k from 1 to 5 crossed with five loss regimes | 10,000 sweeps |
| `e7_c3` | the C3 question at 2,000 replicates | needs 18,000 host observations per cell |
| `e8_scheduler` | two implementation choices that cost a whole wave | it is a property of the code, not the network |

## Findings

Recorded as corrections C4 through C8 in THEORY.md section 16, with the numbers, and
regenerated by `analysis/report.py` and `analysis/c3_report.py` from `data/`.
