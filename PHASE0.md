# Phase 0 — making the study executable

Nothing here collects data. Phase 0 exists to remove every reason the collection
could produce numbers nobody can defend, and it ends when a pilot of three blocks
parses cleanly.

The order matters: each task can invalidate the design of the ones after it, so they
run in sequence and each has a gate that must be met before the next begins.

---

## Amendment to the protocol: the testbed

`PROTOCOL.md` section 3 describes a physical segment of deliberately varied devices as
the ground-truth testbed. That is now the **secondary** testbed, kept for external
validity. The primary is a **programmable segment**, because the central claim is that
the advantage scales with RTT dispersion and a physical network gives you whatever
dispersion your hardware happens to have — one point, maybe two, and no way to reach
dispersion of 1 where the technique should provide no advantage at all.

Recorded as an amendment with today's date, and disclosed in the paper.

---

## 0.1 — Prove the shaping works before designing around it

**Do this first and be willing to lose it.** The whole primary testbed rests on being
able to impose a chosen round-trip time and loss rate on a chosen address, repeatably,
with real ICMP and real MAC addresses on a real segment. If that cannot be done on this
hardware, the study design changes and everything after this task changes with it.

Two candidate mechanisms, in order of preference:

**Per-responder shaping with `netem`**, inside a Linux VM bridged onto the network,
one responder per address. Delay is imposed at the host that answers, which is what a
genuinely slow device does, and it needs nothing from macOS. Containers on a macvlan or
network namespaces with distinct addresses and hardware addresses; the VM's own view of
what it is running becomes an oracle for free.

**Traffic shaping with `dnctl` and `pf`** on the scanning Mac, per destination address.
Simpler to stand up, but it shapes what the scanner sees rather than what the device
does, and recent macOS has restricted parts of `pf`. Treat as fallback.

*Gate.* Ten addresses, five configured delays spanning 1 ms to 500 ms, measured with
`ping` from the scanning Mac: each address lands within 10% of its configured delay,
three runs in a row, and the neighbour table shows a distinct hardware address for
every one of them. If MACs collapse or delays do not hold, stop and report — a
testbed that cannot be trusted is worse than no testbed, because its numbers look real.

## 0.2 — The naming-disable flag

`netsanity scan` currently runs discovery and three naming protocols. Hypotheses H1
through H3 compare against `nmap -sn`, which does host discovery only, so without a way
to switch naming off every timing comparison is measuring different work.

This is a product change, not a study hack: a discovery-only mode is a reasonable thing
for a scanner to offer. It belongs in the CLI's own interface with its own help text,
and the artifact must record which mode produced it.

*Gate.* `netsanity scan --discovery-only --json` produces an artifact whose naming
stage is absent rather than empty, and whose timing block says so.

## 0.3 — nmap, and its versions

Install it, record `nmap --version` verbatim, and confirm both `nmap -sn` and
`sudo nmap -sn` run against the programmable segment. Confirm what unprivileged nmap
actually does on this machine — it should fall back to TCP connect probes, and H3 turns
on that being true rather than assumed.

*Gate.* Both invocations run, both parse, and the fallback behaviour is confirmed by
reading the packet capture rather than the documentation.

## 0.4 — The three oracles agree

Manifest, the VM's own inventory, and a passive capture taken during the run. The
capture is the only one that separates a scanner miss from a device that was not
answering, and it is therefore the one that decides recall.

*Gate.* Three consecutive checks where all three oracles report the same address set on
a segment whose composition is known. A disagreement here is a bug in the oracles, and
finding it now costs an hour; finding it in week two costs the week.

## 0.5 — The harness, dry

`conditions.py`, `schema.py`, `provenance.py`, `runners.py`, `capture.py`,
`run_block.py`, as laid out in `HARNESS.md`. Build them against stubbed tools and run
the whole structure end to end with `--dry-run`.

Two rules that decide whether the data is worth anything, and they are easier to hold
now than to retrofit: wall clock is measured by the harness around the process and
never taken from either tool's own report; a dirty git tree aborts the block.

*Gate.* A dry run produces schema-valid NDJSON for every condition, and `load.py`
reads it back without a single validation warning.

## 0.6 — Pilot

Three real blocks against the programmable segment. Measure the variance, set the
cooldown from it rather than guessing, and confirm the exclusion machinery works by
deliberately breaking one run.

*Gate.* Exclusion rate under 5%, variance stable enough that the planned block count
gives usable confidence intervals, and every number in the pilot recomputable from the
NDJSON alone.

---

## What phase 0 does not do

No hypothesis is tested here and no result is claimed. If a number appears in a phase 0
report it is a diagnostic, not evidence. The first evidence comes from collection, and
collection does not start until every gate above is met.

## The two decisions still outstanding

**Unattended root.** The privileged conditions need it across a seven-day window and a
sudo timestamp will not survive. A root-owned launchd job for those conditions, or a
sudoers entry scoped to the nmap binary and removed afterwards. It goes in the
reproducibility appendix either way, because it is part of the method. JC configures
this; the agent does not touch credentials.

**Keeping the scanning host awake.** `caffeinate -i` around the block loop. The
observed devices must stay free to sleep — their sleep cycle is part of what the
time-of-day strata sample — but the host must not.
