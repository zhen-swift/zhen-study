"""Correction C8's fix: what each candidate spacing schedule buys, and what it costs.

Reads only the CSV. Every number in the write-up and in `SweepSpacing.swift`'s comment
comes from here.

Four schedules, against the same burst table at the same marginal loss rate:

  uniform        every gap is the retransmit interval — what the sweep did before C8
  late400        the final transmission is delayed by a fixed 400 ms, and the sweep is
                 extended to pay for it
  spread         the final transmission is delayed by whatever the tail window can
                 absorb, and the declaration instant is anchored to the last tight
                 transmission so the sweep is not extended at all
  spread_dither  the same, with the gap scattered per host

Two cells, differing in the one thing the price depends on: whether the tail budget is
its 250 ms floor (slack to spend) or the network's own tail (nothing to spend).
"""

from __future__ import annotations

import math

import pandas as pd

import load

pd.set_option("display.width", 220)

ORDER = ["uniform", "late400", "spread", "spread_dither"]
LABEL = {
    "uniform": "uniform (before C8)",
    "late400": "late 400 ms (paid)",
    "spread": "spread into tail (free)",
    "spread_dither": "spread + dither .25",
}


def wilson(k, n, z=1.96):
    if n == 0:
        return (float("nan"), float("nan"))
    p = k / n
    d = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / d
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (centre - half, centre + half)


def schedule_of(condition_id):
    return condition_id.rsplit("_", 1)[-1]


def outage_of(row):
    if row["loss_model"] == "independent":
        return "independent"
    return f"{row['loss_model'][:4]} {row['burst_seconds'] * 1000:.0f}ms"


def main():
    df = load.results()
    e9 = df[df.experiment == "e9_spacing"].copy()
    if e9.empty:
        raise SystemExit("no e9_spacing rows; run sim/run_sim.py")
    e9["schedule"] = e9["condition_id"].map(schedule_of)
    e9["cell"] = e9["condition_id"].str.split("_").str[1]
    e9["outage"] = e9.apply(outage_of, axis=1)

    outages = (["independent"]
               + [f"burs {v * 1000:.0f}ms" for v in (0.05, 0.10, 0.25, 0.50, 1.0, 2.0)]
               + [f"peri {v * 1000:.0f}ms" for v in (0.10, 0.25, 0.50, 1.0)])

    for cell in ("deployment", "study"):
        sub = e9[e9.cell == cell]
        if sub.empty:
            continue
        r = float(sub["retransmit_r_seconds"].iloc[0]) * 1000
        t = float(sub["declare_t_seconds"].iloc[0]) * 1000
        allowance = float(sub["reply_allowance_seconds"].iloc[0]) * 1000
        print("\n" + "=" * 118)
        print(f"cell {cell}: r = {r:.0f} ms, tail = {t:.0f} ms, "
              f"reply allowance = {allowance:.0f} ms, "
              f"slack = {max(0.0, t - allowance):.0f} ms")
        print("=" * 118)

        rows = []
        for label, g in sub.groupby(["policy", "schedule"]):
            policy, schedule = label
            if policy == "fixed":
                name = "fixed budget (comparator)"
            else:
                name = LABEL.get(schedule, schedule)
            rec = {}
            for outage, gg in g.groupby("outage"):
                found = int(gg["hosts_found"].sum())
                total = int(gg["hosts_total"].sum())
                rec[outage] = found / total
            times = g[g.outage == "independent"]["sweep_seconds"]
            rows.append((policy, schedule, name, rec, times.median()))

        rows.sort(key=lambda x: (x[0] != "fixed",
                                 ORDER.index(x[1]) if x[1] in ORDER else 99))
        seen = set()
        base_time = None
        print(f"{'schedule':<26} " + " ".join(f"{o:>10}" for o in outages)
              + f" | {'sweep s':>8} {'vs before':>10}")
        for policy, schedule, name, rec, tm in rows:
            if policy == "fixed" and "fixed" in seen:
                continue
            seen.add("fixed" if policy == "fixed" else schedule)
            if policy == "split" and schedule == "uniform":
                base_time = tm
            delta = ("" if base_time is None or policy == "fixed"
                     else f"{tm - base_time:+10.3f}")
            print(f"{name:<26} "
                  + " ".join(f"{rec.get(o, float('nan')):10.4f}" for o in outages)
                  + f" | {tm:8.3f} {delta:>10}")

        print("\n  recall recovered by the free schedule, in points, against uniform:")
        u = next(r for r in rows if r[0] == "split" and r[1] == "uniform")[3]
        s = next((r for r in rows if r[0] == "split" and r[1] == "spread"), None)
        d = next((r for r in rows if r[0] == "split" and r[1] == "spread_dither"), None)
        for tag, rec in (("spread", s), ("spread+dither", d)):
            if rec is None:
                continue
            gains = {o: 100 * (rec[3].get(o, float("nan")) - u.get(o, float("nan")))
                     for o in outages}
            print(f"    {tag:<14} "
                  + " ".join(f"{gains[o]:+10.1f}" for o in outages))

        indep_u = u.get("independent")
        for policy, schedule, name, rec, tm in rows:
            if policy != "split":
                continue
            if abs(rec.get("independent", 0) - indep_u) > 1e-9:
                print(f"    NOTE: {name} changes independent-loss recall "
                      f"({rec['independent']:.4f} vs {indep_u:.4f})")


if __name__ == "__main__":
    main()
