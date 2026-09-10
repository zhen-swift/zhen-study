"""Instrumented miss attribution for THEORY.md correction C3.

C3 records an unexplained result from the scratch simulator: under 15% loss with
k = 3, both policies are bounded above by 1 - 0.15^3 = 0.9966; the fixed policy
reaches it, the split policy saturates at 0.9926, and widening the declaration window
does not close the gap.  The correction says the mechanism is not understood.

This script produces the evidence to settle it and computes nothing.  It emits one row
per *host observation* — every live host in every replicate, found or not — carrying
why that host ended up where it did:

  transmissions            how many probes it actually received
  lost_transmissions       how many of those were dropped by the loss process
  rejected_arrivals        replies that physically arrived but were not matchable
  first_rejected_arrival   when the earliest such reply landed
  last_send / horizon      the last transmission of the sweep and the instant after
                           which the scanner has declared and stops matching

and a category derived from that row alone:

  all_transmissions_lost                every probe was dropped; no policy could win
  reply_after_last_matchable_instant    a reply arrived but the window had closed
  never_transmitted                     the address never got a probe (a bug if seen)
  unexplained                           none of the above (a bug if seen)

It runs three arms:

  new_release   this simulator, closing a probe's slot when its reply matches
  new_hold      this simulator, holding the slot until the budget expires, which is
                what the scratch script did — the candidate artefact
  scratch       the scratch script itself, unmodified, at its own parameters

The third arm exists because the honest answer to C3 may be "the gap was mine".  If it
is, it must be reported as a measurement defect and not as a property of the technique.

Writes:  data/c3_misses.csv        one row per host that was NOT found, with the
                                    attribution fields above
         data/c3_runs.csv           one row per sweep, hosts_found and hosts_total, so
                                    recall is recomputable without any miss row
         data/c3_scratch_runs.csv   the scratch script's own runs, at its own
                                    replicate count and at a much larger one
"""

from __future__ import annotations

import csv
import random
import sys
from pathlib import Path

from mechanism import FIXED, SPLIT, IndependentLoss, make_population, simulate
import run_sim

SCHEMA_VERSION = 1

# The frontier.py cell, verbatim, because that is where C3 was observed.
N_ADDRS, N_HOSTS, K, C_SLOTS = 254, 9, 3, 240
Q_LOW, Q_HIGH, LOSS = 0.049, 0.600, 0.15
R = Q_LOW * 1.05
BUDGETS = (0.63, 0.9, 1.3, 2.0, 5.0)
REPLICATES = 2000

MISS_COLUMNS = [
    "schema_version", "arm", "policy", "release_on_reply", "budget_seconds",
    "replicate", "addr", "rtt_seconds", "transmissions", "lost_transmissions",
    "rejected_arrivals", "first_rejected_arrival_seconds",
    "last_send_seconds", "horizon_seconds", "sweep_seconds", "category",
]

RUN_COLUMNS = [
    "schema_version", "arm", "policy", "release_on_reply", "budget_seconds",
    "replicate", "hosts_found", "hosts_total", "sweep_seconds",
    "last_send_seconds", "horizon_seconds", "probes_sent", "peak_inflight",
]

SCRATCH_COLUMNS = [
    "schema_version", "arm", "policy", "budget_seconds", "replicate",
    "hosts_found", "hosts_total", "sweep_seconds",
]


def categorise(out, transmitted):
    if not transmitted:
        return "never_transmitted"
    if out.found_at is not None:
        return "found"
    if out.lost_transmissions >= out.transmissions:
        return "all_transmissions_lost"
    if out.rejected_arrivals:
        return "reply_after_last_matchable_instant"
    return "unexplained"


def observations():
    """Returns (miss_rows, run_rows).  Neither is aggregated: a run row carries the
    two counts recall is a ratio of, and a miss row carries one host."""
    misses, runs = [], []
    for release in (True, False):
        arm = "new_release" if release else "new_hold"
        for policy in (FIXED, SPLIT):
            for budget in BUDGETS:
                T = budget if policy == FIXED else Q_HIGH * 1.05
                t = budget
                for rep in range(REPLICATES):
                    pop_seed = run_sim._seed("c3", rep, "pop")
                    loss_seed = run_sim._seed("c3", rep, "loss")
                    order_seed = run_sim._seed("c3", rep, "order")
                    pop = make_population(N_ADDRS, N_HOSTS, Q_LOW, Q_HIGH,
                                          random.Random(pop_seed))
                    loss = IndependentLoss(LOSS, list(pop.hosts), K, loss_seed)
                    res = simulate(policy, pop, loss, k=K, c=C_SLOTS, r=R, t=t, T=T,
                                   order_seed=order_seed,
                                   release_on_reply=release,
                                   record_outcomes=True)
                    common = {
                        "schema_version": SCHEMA_VERSION,
                        "arm": arm,
                        "policy": policy,
                        "release_on_reply": int(release),
                        "budget_seconds": f"{budget:.9g}",
                        "replicate": rep,
                    }
                    runs.append(dict(common,
                                     hosts_found=res.hosts_found,
                                     hosts_total=res.n_hosts,
                                     sweep_seconds=f"{res.sweep_seconds:.9g}",
                                     last_send_seconds=f"{res.last_send_seconds:.9g}",
                                     horizon_seconds=f"{res.horizon_seconds:.9g}",
                                     probes_sent=res.probes_sent,
                                     peak_inflight=res.peak_inflight))
                    for addr, out in sorted(res.outcomes.items()):
                        if out.found_at is not None:
                            continue
                        misses.append(dict(
                            common,
                            addr=addr,
                            rtt_seconds=f"{out.rtt:.9g}",
                            transmissions=out.transmissions,
                            lost_transmissions=out.lost_transmissions,
                            rejected_arrivals=len(out.rejected_arrivals),
                            first_rejected_arrival_seconds=(
                                f"{min(out.rejected_arrivals):.9g}"
                                if out.rejected_arrivals else ""),
                            last_send_seconds=f"{res.last_send_seconds:.9g}",
                            horizon_seconds=f"{res.horizon_seconds:.9g}",
                            sweep_seconds=f"{res.sweep_seconds:.9g}",
                            category=categorise(out, out.transmissions > 0)))
    return misses, runs


def scratch_runs():
    """The scratch script, unmodified, at its own parameters.

    frontier.py used 60 replicates and reused the same seeds for every budget, which
    is exactly the shape that freezes a Monte Carlo fluctuation into what looks like a
    stable saturation.  Both the original replicate count and a much larger one are
    run here so the difference between them is visible in the data rather than
    asserted in prose.
    """
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import sweep_sim

    rows = []
    for reps, tag in ((60, "scratch_as_written"), (REPLICATES, "scratch_more_reps")):
        for policy, budgets in (("shared", BUDGETS), ("split", BUDGETS)):
            for budget in budgets:
                T = budget if policy == "shared" else Q_HIGH * 1.05
                t = budget
                for i in range(reps):
                    # frontier.py's seeding, verbatim: population 1000+i, sweep 7000+i,
                    # identical for every budget.
                    pop = sweep_sim.make_population(N_ADDRS, N_HOSTS, Q_LOW, Q_HIGH,
                                                    LOSS, random.Random(1000 + i))
                    out = sweep_sim.simulate(policy, N_ADDRS, pop, K, C_SLOTS, R, t, T,
                                             random.Random(7000 + i))
                    rows.append({
                        "schema_version": SCHEMA_VERSION,
                        "arm": tag,
                        "policy": policy,
                        "budget_seconds": f"{budget:.9g}",
                        "replicate": i,
                        "hosts_found": round(out["recall"] * N_HOSTS),
                        "hosts_total": N_HOSTS,
                        "sweep_seconds": f"{out['time']:.9g}",
                    })
    return rows


def main():
    data = Path(__file__).resolve().parents[1] / "data"
    data.mkdir(parents=True, exist_ok=True)

    misses, runs = observations()
    with (data / "c3_runs.csv").open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=RUN_COLUMNS, lineterminator="\n")
        w.writeheader()
        w.writerows(runs)
    print(f"wrote {len(runs)} sweeps", file=sys.stderr)
    with (data / "c3_misses.csv").open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=MISS_COLUMNS, lineterminator="\n")
        w.writeheader()
        w.writerows(misses)
    print(f"wrote {len(misses)} missed-host rows", file=sys.stderr)

    scr = scratch_runs()
    with (data / "c3_scratch_runs.csv").open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=SCRATCH_COLUMNS, lineterminator="\n")
        w.writeheader()
        w.writerows(scr)
    print(f"wrote {len(scr)} scratch runs", file=sys.stderr)


if __name__ == "__main__":
    main()
