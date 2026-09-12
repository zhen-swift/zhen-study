# The collection driver

`run_block.py` runs one block of every condition and knows nothing about calendars.
Nothing decided which blocks run when. `collect.py` does, and this records what it is,
what was decided and why, and the evidence for its gate.

**Gate: met.** The driver ran a full stratum's worth of blocks end to end, and killing
it six conditions into a block and restarting it left the data correct — verified by
`harness/prove_collect.py`, which is checked in and re-runnable.

---

## What it has to do, from the protocol

Thirty blocks in each of four time-of-day strata, across at least seven consecutive
days. Four six-hour windows in local time — overnight, morning, afternoon, evening —
because what the strata sample is the household's day, and that has a period of one day
in the local zone rather than in UTC.

**The seven-day floor is the design and the driver enforces it rather than racing it.**
Thirty blocks over seven days is 4.3 a day, so a stratum may take at most five blocks in
one day. Without that cap the driver would satisfy a stratum in a single afternoon and
report the design met, and thirty blocks in one afternoon is a different experiment with
the same block count: device sleep cycles and household load are the thing being
sampled, and sampling one afternoon thirty times measures one afternoon.

## It keeps no bookkeeping of its own

Every count is read from the append-only NDJSON the analysis reads. There is no progress
file, and that is the design rather than an economy.

A driver with its own state has two sources of truth, and they disagree the first time
it is killed between appending a record and updating its state. The disagreement is
silent — you find it weeks later as a stratum four blocks short of what something
claimed. Reading the evidence costs one pass over a few megabytes and cannot drift from
what was collected, because it *is* what was collected.

**A block counts when the file holds a record for every live condition under that block
id.** A block interrupted half way leaves its records behind — the file is append-only
and records what happened — and never becomes complete, so it is neither lost nor
counted twice. `run_block.py` already numbers the next block from the highest id in the
file, so the interrupted id is never reused. That is the whole of the restart story, and
it needed no new mechanism.

**Coverage and usability are counted apart.** "Complete" is a statement about the
matrix: every condition produced a record. Whether those records are evidence is the
exclusion rate's question, and the census reports that separately, with the reasons
broken down and a flag when it crosses section 7's 5% ceiling. Folding the two together
would make a night of denied permissions look like a night of missing blocks, and those
want different repairs.

## launchd or a supervised loop: both, layered

The question as posed has no good single answer, because the two solve different halves.

A bare supervised loop dies with its terminal and does not come back after a reboot,
across a seven-day window. A launchd job invoking one block at a time would survive
that, and could not hold `caffeinate` across the gaps between blocks — the assertion
would drop as each block ended, the Mac would sleep through the four-hour trough before
the next one, and the overnight stratum, which exists precisely to sample the hours
nobody is at the machine, is the one that would silently not run.

So launchd owns liveness across reboots and crashes, and a long-lived loop inside it
owns pacing and the wake assertion. `launchd/dev.netsanity.study.collect.plist` is the
job; JC installs it.

**The contract with launchd is the exit code, and the driver honours it deliberately.**
Exit 0 means it stopped on purpose — finished, or halted with an alarm file written.
Non-zero means it crashed in a way it did not anticipate. So `KeepAlive` is
`SuccessfulExit: false`: a crash is restarted, a halt is left alone. `KeepAlive: true`
would restart it into the same wall every five minutes for a week and bury the reason
in a log nobody would then want to read.

**A LaunchAgent as the owner, not a root LaunchDaemon, and this one is not a
preference.** A root daemon would make `sudo -n` succeed for nothing, since root running
sudo is never asked for a password, and that is genuinely tempting. It would also run
the *unprivileged* conditions as root — and unprivileged `nmap -sn` as root is not
unprivileged nmap, it is privileged nmap with a different argv. H1 and H6 both turn on
that distinction and H6 is a claim about exactly the gap it would erase. Dropping back
with `sudo -u` for those conditions would change the recorded argv of the measured
conditions and put the Local Network permission's responsible process in question, which
`FINDINGS-0.5-harness.md` shows is load-bearing and cannot be queried. So the agent runs
as the owner and root arrives through a sudoers entry scoped to three binaries.

## Keeping the host awake without keeping the network awake

`caffeinate -i -w <own pid>`, spawned once at startup.

`-i` and nothing else: it prevents idle *system* sleep, says nothing about the display,
and says nothing at all about the machines being observed. Their sleep cycle is part of
what the strata sample, so keeping them awake would delete the thing being measured. On
the programmable segment the question is moot — the responders are VMs on a host-local
vmnet bridge — but the secondary physical testbed is real devices and the same driver
runs against it.

`-w` on the driver's own pid means the assertion dies when the driver does, including
when it is killed. A crashed driver that left behind a Mac which will never sleep again
is the kind of thing found six weeks later.

## Failing loudly, because nobody is watching at 03:00

Three places, and the reason is always written next to the failure:

- **`Study/data/collect.log`** — every decision, every block, every reason for waiting,
  `fsync`ed per line so a power cut cannot cost the last thing it said.
- **`Study/data/collect-status.json`** — the current state, rewritten atomically each
  cycle: running, waiting, halted, crashed or complete, with the census inside it.
- **`Study/data/COLLECTION-STOPPED.txt`** — written on a halt, in the directory a person
  looking for the data cannot miss, naming what stopped and how far it had got.

**The driver refuses to start while that file exists.** Whatever stopped collection is
still true until a person says otherwise, and a driver that restarts into a broken
apparatus and quietly records nothing is the failure mode the whole design is against.
Deleting the file is the acknowledgement; the census is read from the data, so it
resumes exactly where the evidence says it is.

It also refuses to start with no `--control-host`, because the Local Network permission
cannot be asserted without one and a denied run is a well-formed artifact with an empty
address set — indistinguishable from a network with nothing on it.

## The gate

**A stratum's worth of blocks, end to end.** Thirty complete blocks in the morning
stratum, dry, then the driver correctly went to `waiting` — "morning already has 30" —
rather than continuing into a stratum whose window it was not in.

**Interrupted mid-block and restarted.** `harness/prove_collect.py`. Timing cannot land
that cut: a dry block is about two tenths of a second, because `run_block.py` skips the
cooldown when the tools are stubbed, so any `sleep` overshoots by dozens of blocks —
which is what the first two attempts did, killing tidily between blocks and proving
nothing. The cut is taken on the line count instead: thirteen lines to a block, so line
32 is six conditions into block 2, and it lands there whatever the machine is doing.
Both the driver and its child get `SIGKILL`, which is what a power cut does; `SIGTERM`
would exercise the tidy path, and the tidy path is not the one that worries anybody.

```
cutting in at 32 lines (block 2 is 6/13 done)
  block 0: COMPLETE   block 1: COMPLETE   block 2: PARTIAL (7/13)
  census counts: 2 complete, partial=[2], runs=33
restarting...
  block 0..1: COMPLETE   block 2: PARTIAL (7/13)   block 3..5: COMPLETE
  census counts: 5 complete, partial=[2], runs=72

  [ok] the kill left exactly one partial block
  [ok] the census refused to count it
  [ok] the partial block is unchanged after the restart
  [ok] the restart never reused the interrupted block id
  [ok] no completed block lost records
  [ok] complete count rose by exactly the blocks the restart finished
  [ok] every record still parses
```

**Dry-run records can never inflate a real census.** The census skips anything stamped
`dry_run` unless the driver is itself in dry run, which is the only way its own logic
can be proved without spending the week it exists to manage. The two universes do not
mix: a rehearsal left in the data directory is invisible to a real count.

## Decisions a reader should be able to argue with

**System python, not `Study/.venv`.** The harness is stdlib-only by design, the
collection worktree has no virtual environment in it, and every import is something that
can fail at 03:00. Verified end to end under `/usr/bin/python3` 3.9.6, which is what
macOS 26 ships.

**No `Nice`, no `LowPriorityIO`, no throttling keys in the job.** The measured quantity
is wall clock and a scheduler that deprioritised the harness would put its thumb on
exactly that. `ProcessType Background` is kept because it is what this is; if the pilot
shows it as a timing effect, it comes out and the change is an amendment rather than
something discovered later.

**The block targets are flags, defaulting to the protocol's numbers.** 0.6's pilot is a
handful of blocks rather than 120, and a driver whose targets are constants cannot be
proved end to end without waiting a week to watch it. Anything other than the defaults
is logged as "not the protocol's design" and recorded in the status file, so a rehearsal
cannot quietly pass for a collection run.

## What is still open

**Unattended root, and it is JC's.** `launchd/netsanity-study.sudoers` is written and
not installed. Touch ID does not substitute: `run_block.py` invokes `sudo -n`, `-n`
means fail rather than prompt, and no PAM configuration puts a person at the machine at
04:00. Four of the thirteen conditions need root, and `tcpdump` needs it for all
thirteen.

**The cooldown is still 15 s because that is the default.** 0.6 sets it from measured
variance. The driver passes it through and records it per run.

**`-T2` is extrapolated, not measured.** About 510 s for a `/24`, from its capture rate
rather than from a completed run, and it is the largest single term in a block — a block
is about twelve minutes and roughly seven of them are that one condition. The pilot
should run it to completion once and replace the number. If it is materially larger, the
five-blocks-a-day cap is what absorbs it, and the seven-day floor does not move.
