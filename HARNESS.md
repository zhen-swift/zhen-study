# The proving phase — harness and analysis

Python, and deliberately not Swift: the measurement apparatus must be independent of
the thing being measured. A harness that shares code with netsanity can share a bug
with it, and a reviewer is entitled to assume the worst.

**One rule above all others: the harness never computes a statistic, and the analysis
never touches the network.** Collection produces raw evidence; analysis produces
numbers; they meet only at an append-only NDJSON file. That separation is what lets
someone rerun the analysis and get your figures without owning your network.

---

## Layout

```
Study/
  PROTOCOL.md                  frozen; the harness must not contradict it
  harness/
    conditions.py              the condition matrix, as data
    provenance.py              versions, git hash, hardware, power, thermal state
    oracles.py                 the three ground-truth sources
    capture.py                 per-run packet capture
    runners.py                 how each tool is invoked and parsed
    run_block.py               executes one block; the only entry point
    schema.py                  the NDJSON record, versioned and validated
  data/
    runs.ndjson                append-only; every run, including excluded ones
    captures/                  one pcap per run, referenced by run id
  analysis/
    load.py                    NDJSON to DataFrame, with schema checks
    stats.py                   the tests named in the protocol, and nothing else
    pareto.py                  the frontier and Figure 1
    figures.py                 every plot
    report.py                  regenerates every number the paper cites
```

---

## The collection scripts

### `conditions.py`

The condition matrix from the protocol, expressed once, as data. Both the harness and
the analysis import it, so a condition cannot exist in the data that the protocol does
not describe. Each entry carries an id, the tool, the exact argv, the privilege
requirement, and which hypotheses it serves.

If a condition needs a CLI flag that does not exist yet — the naming-disable switch for
H1 through H3 — this module is where that dependency becomes visible, because the entry
cannot be written without it.

### `provenance.py`

Called once per run, before and after. Records the netsanity commit hash and whether
the tree is dirty, `nmap --version` verbatim, `swift --version`, `sw_vers`,
`sysctl hw.model`, uptime, thermal pressure, whether the machine is on AC, and the
state of the Local Network permission. **A dirty tree aborts the block.** Measuring
uncommitted code produces a number nobody can reproduce.

### `oracles.py`

Three independent views, returning the same shape so the analysis can compare them:

- **Testbed manifest** — a checked-in YAML of hosts you deliberately placed, each with
  its address, link type, and expected behaviour (answers ICMP, filtered, TCP-only,
  sleeps).
- **Switch client table** — read out of band, parsed to an address set.
- **Passive capture** — post hoc from the pcap: which addresses emitted or answered
  anything during the run window. This is the only oracle that distinguishes a scanner
  miss from a sleeping device, and it is therefore the one that decides recall.

`agree()` returns the intersection, the disagreements, and a verdict. A block whose
oracles disagree is recorded with its exclusion reason rather than dropped silently.

### `capture.py`

Starts `tcpdump` on the segment before each run and stops it after, one pcap per run
id. Also samples channel utilisation so Wi-Fi contention is a recorded covariate
rather than an unexplained outlier. Capture failure aborts the run — a run without its
oracle is not evidence.

### `runners.py`

One function per tool. Each returns the same record: argv, exit status, wall clock
measured with `time.monotonic()` around the process, stdout and stderr verbatim, the
parsed address set, and for netsanity the artifact as parsed JSON.

Two rules. Wall clock is measured by the harness around the process, never taken from
the tool's own report — self-reported timing is exactly what a reviewer will not
accept. And parsing failure is an exclusion, never a silent empty set: an empty result
and an unparseable result are different findings.

### `run_block.py`

The only entry point. One block is one run of every condition, in randomised order.

```
for block in range(n):
    seed and record the shuffle
    flush the neighbour table            # cache state is a condition, not an accident
    for condition in shuffled(conditions):
        cooldown()                       # fixed, measured in the pilot
        start capture
        run
        stop capture
        read the oracles
        append one NDJSON record, fsync
```

Resumable by block id, so a seven-day run survives a reboot. Fails loudly and stops
rather than skipping a condition — a gap nobody notices is worse than a halt.

`--dry-run` executes the whole structure with the tools stubbed, which is how you
prove the harness before spending a week of wall clock on it.

### `schema.py`

The NDJSON record, versioned, validated on write and on read. One run per line:
identifiers, condition, provenance, timings, the address sets from tool and oracles,
covariates, and the exclusion reason if any. Adding a field bumps the version; the
loader refuses a file that mixes versions without an explicit merge.

---

## The analysis scripts

`load.py` reads NDJSON and validates it, and is the only module that touches the raw
file. `stats.py` implements exactly what the protocol names — Mann-Whitney U with
Cliff's delta, McNemar on paired per-host outcomes, bootstrap confidence intervals,
Bonferroni across the family — and nothing more; a test that is not in the protocol
does not get added here without an amendment. `pareto.py` computes the speed/recall
frontier per condition and answers H2 by testing whether any nmap point is
non-dominated. `report.py` regenerates every number the paper cites, so a figure and
its prose cannot drift.

Stack: pandas, scipy, matplotlib. Nothing exotic — a reviewer should be able to run it
without a lockfile archaeology expedition.

---

## Two things to settle before phase 0

**Unattended sudo.** The privileged conditions need root, and a sudo timestamp will not
survive seven days. Do not weaken this by leaving a shell authorised: either run the
privileged conditions from a separate root-owned launchd job, or add a sudoers entry
scoped to exactly the nmap binary for the duration of the study and remove it after.
Whichever you choose, it goes in the paper's reproducibility appendix, because it is
part of the method. Configure it yourself — I will not be entering credentials.

**Keeping the Mac awake.** The scanning host must stay up for the whole window, while
the *observed* devices must be free to sleep, since their sleep cycle is part of what
the strata sample. `caffeinate -i` around the block loop, and record display and power
state per run so a reviewer can see it was controlled.

---

## Phase 0 checklist

1. Add the naming-disable flag to the CLI. Prerequisite, not a finding.
2. Install nmap; record the version; confirm both privileged and unprivileged runs work.
3. Write `conditions.py`, `schema.py`, `provenance.py`; run `--dry-run` end to end.
4. Build the testbed and get three consecutive oracle agreements on a known set.
5. Pilot three blocks; measure variance; fix the cooldown; confirm the data parses.
6. Only then start collection.
