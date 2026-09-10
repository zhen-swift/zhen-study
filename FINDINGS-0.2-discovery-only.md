# 0.2 — Discovery-only mode

`PHASE0.md` 0.2. Hypotheses H1 through H3 compare `netsanity scan` against `nmap -sn`,
which performs host discovery and nothing else. Until now netsanity had no way to stop
after discovery, so every timing comparison in the study would have measured netsanity
doing naming work that the comparator never does. The matched configuration in
`PROTOCOL.md` section 2 requires this flag to exist.

**Gate status: met.** Evidence below, all of it from live runs against
`10.10.20.0/24` rather than from the test doubles.

---

## What was built

`--discovery-only`, a positive flag on `netsanity scan` with its own help text:

```
--discovery-only        Report what is on the network without resolving what
                        it is called. Skips mDNS, SSDP and NetBIOS, so the
                        scan finishes as soon as discovery does.
```

Positive rather than `--no-naming`, so it says what you get instead of what you lose
and composes with `--deep` without a double negative. It is a product feature and is
documented as one: the fast path for when you want to know what is on the network and
not what it is called. Default behaviour is unchanged.

Three things carry the mode into the artifact.

**The naming stage is not started.** `ScanPipeline` guards the naming call rather than
running it against an empty protocol set, so nothing is appended to `Timing.stages`.
The entry is *absent*, not present and zeroed — a stage that ran and found nothing is a
different fact from a stage that never ran, and the analysis has to be able to tell
them apart.

**`run.mode` records it explicitly**, as `"full"` or `"discovery_only"`. A reader
holding one artifact should not have to infer the mode from which stages happen to be
missing, because absence has other causes: naming is already skipped when discovery
found nothing, when the outcome is not `complete`, and when the deadline has expired.

**The decoder tolerates its absence.** `ScanRun`'s decoder is hand-written for one
reason: the synthesized one requires every non-optional key, so adding `mode` would
have made every artifact written by an earlier build fail to decode — turning an
additive field into a breaking change by accident. A missing `mode` reads as `.full`,
which is what those documents meant.

## The schema version was not bumped, and why

The reasoning is written where the version is defined, in `ScanReport.swift`. In short:

The new field is additive and optional on read, which is the easy half. The absent
stage is the half worth arguing. A consumer that iterates `stages` expecting to find a
naming entry would now not find one — but such a consumer was already wrong, because a
stages array without a naming entry has been a valid schema-1 document since before
this flag existed, for the three reasons listed above, and the port stage has only ever
appeared under `--deep`. `stages` has always been a record of what ran, never a
fixed-shape tuple.

So this mode produces no document shape a schema-1 consumer could not already receive.
A bump would have cost every existing consumer a refusal to decode in exchange for no
new safety. If a future change ever makes a stage's *absence* mean something a schema-1
reader would misinterpret, that is the change that bumps it.

## Gate evidence

Three interleaved runs of each mode against `10.10.20.0/24`, 2026-09-06.

| | run 1 | run 2 | run 3 |
|---|---|---|---|
| `--discovery-only` wall clock | 473 ms | 735 ms | 704 ms |
| default wall clock | 3113 ms | 3170 ms | 3200 ms |

Per-stage, from the artifacts themselves:

| mode | run | discovery | naming | run window |
|---|---|---|---|---|
| discovery-only | 1 | 433.1 ms | — | 433 ms |
| discovery-only | 2 | 696.2 ms | — | 696 ms |
| discovery-only | 3 | 665.1 ms | — | 665 ms |
| full | 1 | 406.3 ms | 2669.0 ms | 3076 ms |
| full | 2 | 477.3 ms | 2654.5 ms | 3132 ms |
| full | 3 | 490.9 ms | 2669.7 ms | 3161 ms |

**Naming is roughly 85% of a default scan's wall clock on this network** — 2.65 s of a
3.1 s run, and it is the flat part: the naming stage takes its budgeted time almost
exactly regardless of what discovery found. That is the magnitude of the confound this
flag removes. Without it, H1's timing comparison against `nmap -sn` would have charged
netsanity roughly seven times its discovery cost for work the comparator never does.

**Recall is unaffected.** Both modes found the same 11 devices on every run. The mode
changes what is *reported about* the hosts, not which hosts are found — three devices
carry names under the default and none do under `--discovery-only`. This matters for
the study beyond the gate: the recall hypotheses can be measured in discovery-only mode
without the mode itself being a confound.

*Gate clauses, one at a time.*

- **Naming stage absent.** `stages` is `["discovery"]` in all three discovery-only
  artifacts and `["discovery", "naming"]` in all three defaults.
- **Run metadata names the mode.** `run.mode` is `"discovery_only"` and `"full"`
  respectively, present on the wire under a key of its own.
- **Round-trips through the decoder unchanged.** All six live artifacts decode, pass
  `validateSchema()`, and re-encode byte-identically to the bytes the CLI wrote, modulo
  the single trailing newline the CLI adds when writing a line to stdout. Re-decoding
  the re-encoded bytes is a fixed point.
- **Backwards compatibility, on real data.** A live artifact with the `mode` key
  deleted decodes as `full`. Re-encoding it adds the key, so the bytes differ — that is
  an upgrade rather than a failure, and it is the intended behaviour.
- **Exit codes unaffected.** Exit 0 in all six runs. There is a test asserting exit
  status is unaffected by the mode.

*Tests.* A `Discovery-only mode` suite covers: the naming stage is absent rather than
empty; the naming protocols are never *started* (asserted by a spy on the resolver, not
by an empty result, because the point is that no work happens); the default is
unchanged; the mode is in run metadata; both modes round-trip; the mode reaches the
wire under its own key; a document written before the mode existed decodes as full; and
exit status is unaffected. Full suites pass: **260 tests in netsanity-core, 49 in
netsanity-cli.**

## What could not be verified

**One network, one interface.** Everything above is `10.10.20.0/24` over `en0`. The
flag's behaviour is not network-dependent — it is a branch around a function call — but
the *timings* are this network's and should not be quoted as results. They are
diagnostics, as `PHASE0.md` requires.

**`--deep` composition is verified by a run but not by a test.**
`netsanity scan --discovery-only --deep` produces `stages: ["discovery", "deep_scan"]`
with `mode: "discovery_only"` and ports on every device — the two flags are independent
and the double-negative the flag's naming was chosen to avoid does not appear. That is
one live run, not a regression test; the study does not use `--deep`, so no test was
added for a combination it will never exercise.

**The 254-probe burst behaviour is unchanged and unexamined here.** Discovery-only
changes nothing about discovery itself; the discovery-stage timings above vary between
433 ms and 696 ms across three runs, which is the sweep's own variance and a matter for
0.6 rather than for this gate.
