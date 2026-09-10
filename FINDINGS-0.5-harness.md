# 0.5 — The harness, dry

`PHASE0.md` 0.5. Six modules, Python, stubbed tools, and one question: can the whole
structure be run end to end and produce records that survive being read back.

**Gate status: met, with one deliberate hole.** A `--dry-run` produces schema-valid
NDJSON for every condition and `load.py` reads it back with zero validation warnings.
The hole is `oracles.py`, which is 0.4 and is not built, because 0.4 depends on a
testbed decision that is still open. It is not silently absent: every record carries
`oracle.status`, and a **live** block refuses to start at all until it exists.

---

## What was built

```
Study/harness/
  __init__.py      the independence rule, stated
  conditions.py    the condition matrix, as data — 12 ready, 2 blocked
  schema.py        the NDJSON record, versioned, validated on write and on read
  provenance.py    versions, git state, power, and the Local Network assertion
  runners.py       how each tool is invoked and parsed, plus the dry-run stubs
  capture.py       per-run tcpdump, neighbour-table flush, Wi-Fi covariates
  run_block.py     one block of every condition, randomised; the only entry point
Study/analysis/
  load.py          extended: `runs()` and `validate_runs_file()` read the NDJSON back
```

`oracles.py` is absent by decision, not by omission. See the last section.

### Independence, asserted rather than claimed

HARNESS.md's first rule is that the measurement apparatus must not share code with the
thing measured. `run_block.py --self-check` parses every module in the package with
`ast` and fails if any `Import` or `ImportFrom` node names netsanity or swift:

```
$ python Study/harness/run_block.py --self-check
self-check: no forbidden imports in 7 harness modules
```

Parsed rather than grepped. The first version of that check matched line prefixes and
flagged a docstring sentence beginning *"from this process"* — which is the failure mode
of every textual import check, and it fired on the first run.

## The four things the earlier findings changed

### 1. The matched configuration is built from a real flag

0.2 shipped `--discovery-only`, so `ns.disc.unpriv` and `ns.disc.priv` are written
against a flag that exists rather than against a note saying one is needed. The
condition matrix is where a missing flag becomes visible, and two entries are still
`BLOCKED` for exactly that reason:

| id | blocked on | why it matters |
|---|---|---|
| `ns.fixed.timeout` | `--retransmit-timeout` on `netsanity scan` | H2 claims adaptive per-host timing dominates fixed templates. Without a way to pin netsanity's *own* retransmit timeout, the ablation only ever compares netsanity to nmap's templates and never to netsanity's own fixed-timing behaviour — which is the comparison that isolates the mechanism. `--deadline` is not this flag: it bounds the whole scan, not the per-host interval. |
| `ns.budget.shared` | `--shared-budget` on `netsanity scan` | H5 is split budget versus one shared budget. There is no CLI knob and no environment override — `SweepSpacing` computes both internally — so **H5 cannot be measured at all today.** This is PROTOCOL.md section 2 row 4, and it is unwritable. |

They are printed on every invocation rather than being quietly filtered out:

```
note: ns.fixed.timeout is excluded from every block — it needs --retransmit-timeout ...
note: ns.budget.shared is excluded from every block — it needs --shared-budget ...
```

### 2. The Local Network permission is asserted per run

The load-bearing one. Denial returns **zero results rather than an error** and there is
no API to query the grant, so a denied run is exit 0, a well-formed artifact, and an
empty address set — indistinguishable from a network with nothing on it. A study that
recorded that as "recall 0" would be publishing a fabricated number.

So it is asserted with a positive control rather than queried. `provenance.py` sends an
unprivileged ICMP echo from its own process — `SOCK_DGRAM`/`IPPROTO_ICMP`, the same
socket family netsanity's unprivileged engine uses, which macOS grants without root — to
addresses declared with `--control-host`, and reads the kernel's neighbour table, which
is readable *without* the permission. Measured, live:

```
{"verdict": "granted",
 "method": "unprivileged SOCK_DGRAM/IPPROTO_ICMP echo to declared control hosts,
            with the kernel neighbour table as the negative control",
 "control_hosts": ["10.10.20.1"], "controls_answered": 1, "neighbour_entries": 7}
```

Three outcomes, and only `granted` is admissible. No control answered but the neighbour
table lists live hosts is `denied_likely` — the machine has demonstrably been talking to
those hosts and our probes to them got nothing back. Neither is `indeterminate`, because
an empty segment and a denied permission are not distinguishable from here and claiming
otherwise would be a guess.

*What that proves, and what it does not.* The grant attaches to the responsible
application rather than to the binary, and a bare SPM executable has no bundle of its
own, so what is asserted is the grant held by the process tree the harness runs in —
which is exactly the population of processes it launches. It is not a claim about any
other terminal.

*A defect found while testing this.* The first version returned `denied_likely` when no
control host had been declared at all, because nothing answered and the neighbour table
was non-empty. That is a harness misconfiguration being reported as a permission
denial — it would have sent someone to a settings pane to fix something that was not
broken. It now returns `indeterminate` with a reason, and a live block refuses to start
without at least one `--control-host`.

### 3. Wall clock is the harness's, never the tool's

`runners.py` brackets every process with `time.monotonic()`, and that is the only place a
duration is taken. Both tools do report their own timing and both reports are recorded —
netsanity's `run.started_at`/`finished_at`, nmap's `<runstats><finished elapsed>` — under
the field name `tool_self_reported_seconds`, which is chosen so no analysis can reach for
it believing it to be the measurement.

The schema enforces it rather than leaving it to code review. Every record must carry
`wall_clock_source: "harness_monotonic"` and validation rejects anything else, and the
record's own duration must fit inside the timestamps that bracket it.

### 4. A dirty tree aborts the block

Before anything runs, not after. Demonstrated on this tree, which is dirty:

```
$ python Study/harness/run_block.py --blocks 1 --control-host 10.10.20.1
BLOCK ABORTED: the working tree is dirty, so the block is aborted before it starts.
Measuring uncommitted code produces a number nobody can reproduce.
  .github/workflows/ci.yml
  CHANGELOG.md
  ...
```

Untracked files count as dirty. Stricter than strictly necessary, and the right side to
err on: the harness cannot tell a scratch note from a source file someone forgot to add,
and the difference between those two is the difference between reproducible and not.

`--dry-run` may proceed on a dirty tree only if asked twice, with `--allow-dirty`, and
its records are stamped `dry_run: true`. The schema's dirty-tree rule then applies to
evidence and not to apparatus checks — a dry run measures stubs, so the commit it ran
against says nothing about any number in it. `--allow-dirty` is refused outright in live
mode.

*A defect found while testing this.* The abort message named the wrong paths. `_run()`
stripped every command's stdout, which ate the leading space of `git status --porcelain`'s
first line and shifted every path by one character — `.github/workflows/ci.yml` was
reported as `github/workflows/ci.yml`. Fixed by not stripping output whose leading
whitespace is data, and the reason is written at the function.

## The gate

```
$ rm -rf Study/data/dryrun.ndjson Study/data/dryrun-raw
$ python Study/harness/run_block.py --dry-run --allow-dirty --blocks 3 --seed 1 \
      --control-host 10.10.20.1 --netsanity .../release/netsanity
...
36 record(s) appended to Study/data/dryrun.ndjson

$ python Study/analysis/load.py Study/data/dryrun.ndjson
Study/data/dryrun.ndjson: 36 record(s), 0 validation warning(s)
```

| clause | evidence |
|---|---|
| every condition | 12 runs per block, and the set matches `conditions.ready()` exactly in all three blocks |
| schema-valid | 36 records written, every one validated *before* the line was appended |
| read back clean | `load.py` reports 0 validation warnings; `runs()` returns a 36-row frame |
| one schema version | `schema_version` is `[1]` throughout; the loader refuses a mixed file |
| randomised within block | all three block orders distinct; the seed is recorded per record |
| harness timing | `wall_clock_source` is `harness_monotonic` in all 36 |
| permission asserted | `permission_verdict` is `granted` in all 36, from a live ICMP control |

The dry run takes 0.8 s for three blocks, which is the point of it: the structure can be
re-proved after every change to it.

### The stubs run the real parsers

A dry run that bypassed the parsers would prove only that the loop iterates. The stubs
emit real output in each tool's real format — a netsanity `ScanReport` JSON document and
an nmap `-oX` XML document — and hand it to the same `parse_netsanity` and
`parse_nmap_xml` the live runners use. The stubbed durations are short real sleeps rather
than fabricated numbers, so the schema's timing checks are not vacuous at the moment they
are being tested.

Both parsers were then verified against genuine output rather than only against the
stubs:

- `parse_netsanity` against a live `netsanity scan --discovery-only --json` artifact:
  5 addresses, `mode: discovery_only`, `engine.kind: unprivileged`, `stages: ["discovery"]`.
- `parse_nmap_xml` against a live `nmap -sn ... --reason -T3` XML file: 1 address
  (`10.10.20.1`), reason `syn-ack`, `elapsed 21.96`, `exit success`.

### The validator was tested adversarially

"Zero warnings" is only worth something if the validator can produce one. Eleven
mutations of a real record, every one of which must be rejected — and every one was:

| mutation | caught by |
|---|---|
| `wall_clock_source` set to `nmap_runstats_elapsed` | the self-report rule |
| `parse.ok = false` with `exclusion = null` | the silent-empty-set rule |
| `found_count` disagreeing with the address list | the assembled-not-edited check |
| an exclusion reason not in the pre-specified set | section 7's fixed exclusion list |
| `git_dirty = true` on a live record | the dirty-tree rule |
| `local_network_permission` removed | the provenance key check |
| `wall_clock_seconds` longer than its own timestamps | the bracketing check |
| unsorted or duplicated addresses | the address-set normal form |
| `capture.status = ok` with no pcap path | the capture check |
| `schema_version = 2` | the version check |
| `"localhost"` in the address set | the IPv4 check |

## What the block count should be, from measured variance

`run_block.py --sizing`. Computed from nmap's four observed wall clocks — 3.61, 12.61,
20.98 s from 0.3 and 21.96 s taken while verifying the XML parser — rather than from a
guess. Every number in the note is generated from the samples, so it cannot drift from
the table above it; that is not hypothetical, it drifted once during writing when the
fourth sample was added.

```
nmap -sn wall clock, n=4: [3.61, 12.61, 20.98, 21.96]
  mean 14.79s  median 16.80s  sd 8.55s  cv 0.58
  sigma 95% CI [4.85s, 31.89s] — a factor of 7, which is what four samples buys

     CI half-width  blocks (mean)  if sigma low  if sigma high  blocks (median)
  +/- 10% ( 1.48s)            128            41           1786              202
  +/- 20% ( 2.96s)             32            10            447               50
  +/- 25% ( 3.70s)             21             7            286               32
  +/- 50% ( 7.40s)              5             2             71                8
```

What that means for 0.6, so the pilot has a number to test rather than invent:

- **PROTOCOL.md's n ≥ 30 per stratum buys about ±21% on nmap's mean within a stratum and
  about ±26% on its median — not the ±10% a reader will assume.** Pooled across four
  strata (n = 120) the median interval tightens to roughly ±13%.
- **That is ample for the hypothesis tests and thin for the headline number.** H1 and H2
  are rank comparisons, and the two distributions do not overlap at all — netsanity at
  0.37–0.71 s against nmap at 3.6–22.0 s — so Mann–Whitney separates them at n well under
  10 per group. What n ≥ 30 is buying is a publishable interval around nmap's median.
- **The pilot's real job is to pin σ, not to confirm 30.** Four samples admit σ anywhere
  in [4.8 s, 31.9 s] and the block count scales with σ²: a ±25% interval needs 7 blocks at
  the bottom of that range and 286 at the top, against a seven-day window that supplies
  about 120 per condition. If the pilot's σ lands in the upper half, the paper's headline
  number has to become a wider interval or a different statistic — an amendment to write
  before collection rather than a surprise to find after it.
- **Run 10 pilot blocks, not 3.** Three samples cannot distinguish those cases: at n = 3
  the 95% interval on σ spans a factor of 12. Ten roughly halves it and costs about an
  hour at a 15 s cooldown.

Block cost, from the observed per-condition times: about 271 s per block at a 15 s
cooldown, so 30 blocks × 4 strata is roughly 9 hours of wall clock spread across the
seven-day window. The matrix fits.

## What stops a live block, and why each is a halt rather than a skip

All four verified by running them:

| condition | behaviour |
|---|---|
| dirty working tree | abort before the block starts, listing what is dirty |
| no `--control-host` declared | refuse at argument parsing: the permission cannot be asserted without one |
| Local Network permission not `granted` | abort, naming the verdict and the remedy |
| `oracles.py` absent | abort: recall is meaningless without knowing what was there |
| `sudo -n` refused mid-block | `PrivilegeUnavailable` stops the block, not the run |
| capture failed | stop the block: a run without its oracle is not evidence |
| parse failure | the run is **excluded**, with `parse_failure` and the parser's own message |

The `sudo` one is worth its own sentence. A refused `sudo -n` is not a per-run exclusion,
because if root is not arranged then every privileged run in every remaining block fails
identically — and a study that quietly drops half its conditions overnight is worse than
one that halts on the first night. Same reasoning for the capture.

## What could not be verified

**`oracles.py` is not built, and a live block cannot run.** Deliberate. The three oracles
are gate 0.4 — a testbed manifest, the switch client table, and the passive capture — and
all three are shaped by a testbed decision that is still open: 0.1's VM approach works but
costs two responders per machine (five VMs for ten addresses, ten to fifteen for a
realistic /24), and a wired VLAN with one Linux box hosting macvlan responders would
replace it. Building oracles against an apparatus that may be discarded is waste. Every
record therefore carries `oracle.status`, `not_configured` for a live run and `stubbed`
for a dry one, and the exclusion reason `oracle_not_configured` exists in the schema so
this state is a recorded fact rather than a missing field.

**No live block has ever been run.** Everything above is either a dry run against stubs
or a single live invocation of one tool to verify one parser. Timings from a real block,
the interaction of `tcpdump` with a real sweep, and whether five virtual machines answer a
254-probe burst the way they answer a serial ping are all 0.6 and are all untested.

**`tcpdump`, the neighbour-table flush, and the privileged conditions are unexercised.**
All three need root, which is not available to the agent on this machine, and the same
credential boundary that leaves half of gate 0.3 open leaves these untested. The code
paths are written and reviewed; they have not run. Whatever arrangement `PHASE0.md`
settles on for unattended root has to cover `tcpdump` and `arp -a -d` as well as `nmap`.

**Airtime utilisation is not recorded, and the field says so.** The protocol asks for
channel utilisation as a Wi-Fi contention covariate. It is not readable on macOS 26
without root — `airport` was removed and `wdutil info` is root-only and redacts — so what
is recorded is what *is* readable: channel, band, width, PHY mode and signal/noise from
`system_profiler`. Those are link covariates, not utilisation, and
`airtime_utilisation` is present and `null` alongside a note saying why, rather than a
number that would be mistaken for it. On the programmable segment the question does not
arise at all: it is a vmnet bridge with no radio, and the field reads `not_applicable`.

The Wi-Fi sample is taken **once per block**, not once per run, and the record says so.
`system_profiler` takes about ten seconds to answer, and a ten-second stall between two
timed runs is a covariate that perturbs the thing it is meant to describe.

**`scipy` is not installed in `Study/.venv`.** HARNESS.md names pandas, scipy and
matplotlib; pandas 3.0.5 and matplotlib 3.11.1 are present and scipy is not. Nothing in
the harness needs it — it is deliberately stdlib-only, because it has to run unattended
for seven days and every import is something that can fail at 03:00, and the chi-square
quantiles the sizing function uses are hard-coded for that reason. But `stats.py` cannot
be written without it, and that is phase 2's first blocker.

## What contradicts the documents

**HARNESS.md's layout lists `oracles.py` among the collection scripts; `PHASE0.md` 0.5
does not.** 0.5 names six files and oracles is not one of them; the oracles are 0.4's
gate. The six were built and `oracles.py` was not, following `PHASE0.md`, and the reason
is recorded above.

**PROTOCOL.md section 2 row 4 describes a condition that cannot be expressed.** "Ablation,
budget | single shared budget vs split" requires a flag netsanity does not have. The
protocol's own rule for the naming flag — *"if the CLI has no flag for that, adding one
is a prerequisite of this study, not a finding of it"* — applies to this one identically,
and it has not been done. H5 is currently unmeasurable.

**`analysis/load.py` was written against the simulator's CSVs and had no reader for the
collection NDJSON at all.** It has one now, added alongside the existing functions rather
than replacing them. It imports exactly one module from the harness — `schema` — which is
the shared *definition* of the record and is what lets the reader refuse a file the writer
would not have produced. Nothing else crosses.
