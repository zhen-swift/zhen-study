"""Produce evidence.  One row per replicate, per policy, and no aggregation at all.

This is the collection half of the separation HARNESS.md insists on: this file never
computes a statistic.  There is no mean, no median, no ratio across replicates and no
frontier here.  Every summary in the paper is recomputed by ``analysis/`` from the CSV
this writes, so no number is trapped in code that produced it.

The model predictions in each row are not statistics: they are functions of the
condition's parameters alone, evaluated per row so that a residual can be taken
without re-deriving the condition.  ``model.py`` is imported here and nowhere near
``mechanism.py``.

Usage:
    python3 run_sim.py                     # writes ../data/sim_results.csv
    python3 run_sim.py --out FILE
    python3 run_sim.py --only e1_dispersion e2_frontier
    python3 run_sim.py --smoke              # the tiny grid the tests reuse
"""

from __future__ import annotations

import argparse
import csv
import random
import sys
import time
import zlib
from pathlib import Path

import conditions as C
import model
from mechanism import (FIXED, SPLIT, BurstyLoss, Dithered, IndependentLoss,
                       LateSpacing, PeriodicLoss, UniformSpacing,
                       make_population, simulate)

SCHEMA_VERSION = 3

COLUMNS = [
    "schema_version",
    "experiment",
    "condition_id",
    "replicate",
    "policy",
    # condition parameters, every one of them, so no row needs its condition looked up
    "n_addrs",
    "n_hosts",
    "host_density",
    "q_low_seconds",
    "q_high_seconds",
    "dispersion",
    "loss_rate",
    "loss_model",
    "burst_seconds",
    "attempts_k",
    "concurrency_c",
    "retransmit_r_seconds",
    "declare_t_seconds",
    "fixed_budget_T_seconds",
    "release_on_reply",
    "tie_break",
    "slot_hold",
    "horizon_anchor",
    "spacing_policy",
    "spread_seconds",
    "spacing_jitter",
    "reply_allowance_seconds",
    "waves_expected",
    # seeds: everything needed to replay this exact row
    "pop_seed",
    "loss_seed",
    "order_seed",
    # outcomes
    "sweep_seconds",
    "recall",
    "hosts_found",
    "hosts_total",
    "probes_sent",
    "peak_inflight",
    "last_send_seconds",
    "horizon_seconds",
    "time_to_first_host_seconds",
    "waves_observed",
    # predictions and residuals, per row, from model.py
    "recall_bound",
    "model_naive_seconds",
    "model_wave_seconds",
    "model_wave_last_seconds",
    "residual_naive_seconds",
    "residual_wave_seconds",
    "residual_wave_last_seconds",
    "residual_naive_ratio",
    "residual_wave_ratio",
    "residual_wave_last_ratio",
]


def _seed(*parts):
    """Stable across processes and Python builds; str.__hash__ is not."""
    return zlib.crc32("|".join(str(p) for p in parts).encode()) & 0x7FFFFFFF


def _horizon(cond):
    """A generous upper bound on how long any sweep in this condition can last, used
    only to pre-generate the correlated-loss realisation far enough into the future."""
    step = max(cond.fixed_budget_T, cond.retransmit_r)
    return (cond.waves_expected + 3) * step + cond.declare_t + 10.0


def _spacing(cond, addrs, replicate):
    """Build the schedule this condition names.  None means the simulator's own
    default, which is a uniform gap of r — what the sweep did before correction C8."""
    if cond.spacing_policy == "uniform":
        return None
    base = cond.retransmit_r
    inner = LateSpacing(base, cond.spread_seconds)
    if cond.spacing_jitter <= 0:
        return inner
    return Dithered(inner, cond.spacing_jitter, addrs, cond.attempts_k + 1,
                    _seed(cond.experiment, replicate, "dither"))


def replicate_rows(cond, replicate):
    # Common random numbers, keyed on the experiment rather than the condition: every
    # condition within an experiment sees the same population, the same loss draws and
    # the same visiting order for a given replicate index, so points on a frontier are
    # paired rather than independently noisy.
    #
    # Sharing seeds is what froze the C3 artefact into place in the scratch script, so
    # it is worth being explicit about why it is safe here and was not there.  The
    # defect was not the sharing, it was sharing across only 60 replicates: a two-host
    # fluctuation then looked like a stable saturation because it was literally the
    # same two hosts in every column.  With 200-1000 replicates per condition and a
    # confidence interval reported next to every rate, a fluctuation of that size
    # cannot be mistaken for a finding.  diagnose_c3.py runs the scratch code at both
    # replicate counts so that claim is checkable rather than asserted.
    pop_seed = _seed(cond.experiment, replicate, "pop")
    loss_seed = _seed(cond.experiment, replicate, "loss")
    order_seed = _seed(cond.experiment, replicate, "order")

    pop = make_population(cond.n_addrs, cond.n_hosts, cond.q_low, cond.q_high,
                          random.Random(pop_seed))
    addrs = list(pop.hosts)
    if cond.loss_model == "bursty":
        loss = BurstyLoss(cond.loss, cond.burst_seconds, addrs,
                          horizon=_horizon(cond), seed=loss_seed)
    elif cond.loss_model == "periodic":
        loss = PeriodicLoss(cond.loss, cond.burst_seconds, addrs, seed=loss_seed,
                            shared_phase=True)
    else:
        loss = IndependentLoss(cond.loss, addrs, cond.attempts_k, loss_seed)

    spacing = _spacing(cond, addrs, replicate)

    rows = []
    for policy in cond.policies:
        res = simulate(policy, pop, loss,
                       k=cond.attempts_k, c=cond.concurrency_c,
                       r=cond.retransmit_r, t=cond.declare_t,
                       T=cond.fixed_budget_T,
                       order_seed=order_seed,
                       release_on_reply=cond.release_on_reply,
                       tie_break=cond.tie_break,
                       spacing=spacing,
                       slot_hold=cond.slot_hold,
                       horizon_anchor=cond.horizon_anchor,
                       reply_allowance=cond.reply_allowance)
        naive = model.predict(policy, "naive",
                              n_addrs=cond.n_addrs, n_hosts=cond.n_hosts,
                              k=cond.attempts_k, c=cond.concurrency_c,
                              r=cond.retransmit_r, t=cond.declare_t,
                              T=cond.fixed_budget_T)
        wave = model.predict(policy, "wave",
                             n_addrs=cond.n_addrs, n_hosts=cond.n_hosts,
                             k=cond.attempts_k, c=cond.concurrency_c,
                             r=cond.retransmit_r, t=cond.declare_t,
                             T=cond.fixed_budget_T)
        wave_last = model.predict(policy, "wave_last",
                                  n_addrs=cond.n_addrs, n_hosts=cond.n_hosts,
                                  k=cond.attempts_k, c=cond.concurrency_c,
                                  r=cond.retransmit_r, t=cond.declare_t,
                                  T=cond.fixed_budget_T)
        rows.append({
            "schema_version": SCHEMA_VERSION,
            "experiment": cond.experiment,
            "condition_id": cond.condition_id,
            "replicate": replicate,
            "policy": policy,
            "n_addrs": cond.n_addrs,
            "n_hosts": cond.n_hosts,
            "host_density": f"{cond.host_density:.9g}",
            "q_low_seconds": f"{cond.q_low:.9g}",
            "q_high_seconds": f"{cond.q_high:.9g}",
            "dispersion": f"{cond.dispersion:.9g}",
            "loss_rate": f"{cond.loss:.9g}",
            "loss_model": cond.loss_model,
            "burst_seconds": f"{cond.burst_seconds:.9g}",
            "attempts_k": cond.attempts_k,
            "concurrency_c": cond.concurrency_c,
            "retransmit_r_seconds": f"{cond.retransmit_r:.9g}",
            "declare_t_seconds": f"{cond.declare_t:.9g}",
            "fixed_budget_T_seconds": f"{cond.fixed_budget_T:.9g}",
            "release_on_reply": int(cond.release_on_reply),
            "tie_break": cond.tie_break,
            "slot_hold": cond.slot_hold,
            "horizon_anchor": cond.horizon_anchor,
            "spacing_policy": cond.spacing_policy,
            "spread_seconds": f"{cond.spread_seconds:.9g}",
            "spacing_jitter": f"{cond.spacing_jitter:.9g}",
            "reply_allowance_seconds": f"{cond.reply_allowance:.9g}",
            "waves_expected": cond.waves_expected,
            "pop_seed": pop_seed,
            "loss_seed": loss_seed,
            "order_seed": order_seed,
            "sweep_seconds": f"{res.sweep_seconds:.9g}",
            "recall": f"{res.recall:.9g}",
            "hosts_found": res.hosts_found,
            "hosts_total": res.n_hosts,
            "probes_sent": res.probes_sent,
            "peak_inflight": res.peak_inflight,
            "last_send_seconds": f"{res.last_send_seconds:.9g}",
            "horizon_seconds": f"{res.horizon_seconds:.9g}",
            "time_to_first_host_seconds": ("" if res.time_to_first_host is None
                                           else f"{res.time_to_first_host:.9g}"),
            "waves_observed": res.waves_observed,
            "recall_bound": f"{model.recall_bound(cond.loss, cond.attempts_k):.9g}",
            "model_naive_seconds": f"{naive:.9g}",
            "model_wave_seconds": f"{wave:.9g}",
            "model_wave_last_seconds": f"{wave_last:.9g}",
            "residual_naive_seconds": f"{res.sweep_seconds - naive:.9g}",
            "residual_wave_seconds": f"{res.sweep_seconds - wave:.9g}",
            "residual_wave_last_seconds": f"{res.sweep_seconds - wave_last:.9g}",
            "residual_naive_ratio": f"{res.sweep_seconds / naive:.9g}" if naive else "",
            "residual_wave_ratio": f"{res.sweep_seconds / wave:.9g}" if wave else "",
            "residual_wave_last_ratio": (f"{res.sweep_seconds / wave_last:.9g}"
                                         if wave_last else ""),
        })
    return rows


def emit(conds, fileobj, progress=None):
    writer = csv.DictWriter(fileobj, fieldnames=COLUMNS, lineterminator="\n")
    writer.writeheader()
    written = 0
    for i, cond in enumerate(conds, 1):
        for rep in range(cond.replicates):
            for row in replicate_rows(cond, rep):
                writer.writerow(row)
                written += 1
        if progress is not None:
            progress(i, len(conds), cond, written)
    return written


def smoke_conditions():
    """A tiny grid, used by the determinism test and by --smoke."""
    return [
        C._cell("smoke", "smoke_a", replicates=3),
        C._cell("smoke", "smoke_b", dispersion=41.0, loss=0.15, replicates=3),
        C._cell("smoke", "smoke_c", policies=("split",), loss=0.15,
                loss_model="bursty", burst_seconds=0.25, replicates=3),
    ]


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(Path(__file__).resolve().parents[1]
                                         / "data" / "sim_results.csv"))
    ap.add_argument("--only", nargs="*", default=None,
                    help="restrict to these experiment names")
    ap.add_argument("--smoke", action="store_true")
    args = ap.parse_args(argv)

    conds = smoke_conditions() if args.smoke else C.all_conditions()
    if args.only:
        conds = [c for c in conds if c.experiment in set(args.only)]
    if not conds:
        print("no conditions selected", file=sys.stderr)
        return 2

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()

    def progress(i, n, cond, written):
        print(f"[{i:3d}/{n}] {cond.condition_id:<28} rows={written:<7d} "
              f"{time.monotonic() - started:7.1f}s", file=sys.stderr, flush=True)

    with out.open("w", newline="") as fh:
        written = emit(conds, fh, progress=progress)
    print(f"wrote {written} rows to {out} in {time.monotonic() - started:.1f}s",
          file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
