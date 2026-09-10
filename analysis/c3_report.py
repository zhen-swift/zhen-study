"""Answer correction C3: where does the split policy's recall gap come from?

Reads only the CSVs.  Every number printed here is recomputed from them.
"""

from __future__ import annotations

import math

import pandas as pd

import load

BOUND = 1 - 0.15 ** 3


def wilson(k, n, z=1.96):
    if n == 0:
        return (float("nan"), float("nan"))
    p = k / n
    d = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / d
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (centre - half, centre + half)


def recall_table(runs, label):
    g = runs.groupby(["arm", "policy", "budget_seconds"], as_index=False)[
        ["hosts_found", "hosts_total"]].sum()
    g["recall"] = g["hosts_found"] / g["hosts_total"]
    lo, hi = zip(*[wilson(k, n) for k, n in zip(g["hosts_found"], g["hosts_total"])])
    g["ci_lo"], g["ci_hi"] = lo, hi
    g["gap_to_bound"] = BOUND - g["recall"]
    print(f"\n### {label}")
    print(f"{'arm':<20} {'policy':<7} {'budget':>7} {'obs':>7} {'recall':>8} "
          f"{'95% CI':>17} {'bound-recall':>13}")
    for _, r in g.sort_values(["arm", "policy", "budget_seconds"]).iterrows():
        print(f"{r['arm']:<20} {r['policy']:<7} {r['budget_seconds']:7.2f} "
              f"{int(r['hosts_total']):7d} {r['recall']:8.4f} "
              f"[{r['ci_lo']:.4f},{r['ci_hi']:.4f}] {r['gap_to_bound']:13.4f}")
    return g


def main():
    print("=" * 78)
    print("C3: the split policy's recall gap")
    print("=" * 78)
    print(f"Independent-loss ceiling with loss=0.15, k=3:  1 - 0.15^3 = {BOUND:.4f}")

    scratch = load.c3_scratch()
    scratch["arm"] = scratch["arm"]
    st = scratch.groupby(["arm", "policy", "budget_seconds"], as_index=False)[
        ["hosts_found", "hosts_total"]].sum()
    st["recall"] = st["hosts_found"] / st["hosts_total"]
    lo, hi = zip(*[wilson(k, n) for k, n in zip(st["hosts_found"], st["hosts_total"])])
    st["ci_lo"], st["ci_hi"] = lo, hi
    print("\n### Arm 3: the scratch script itself, unmodified")
    print(f"{'arm':<20} {'policy':<7} {'budget':>7} {'obs':>7} {'recall':>8} "
          f"{'95% CI':>17}")
    for _, r in st.sort_values(["arm", "policy", "budget_seconds"]).iterrows():
        print(f"{r['arm']:<20} {r['policy']:<7} {r['budget_seconds']:7.2f} "
              f"{int(r['hosts_total']):7d} {r['recall']:8.4f} "
              f"[{r['ci_lo']:.4f},{r['ci_hi']:.4f}]")

    runs = load.c3_runs()
    recall_table(runs, "Arms 1 and 2: this simulator, slot released on reply vs held")

    misses = load.c3_misses()
    print("\n### Miss attribution — why was each unfound host unfound?")
    tally = (misses.groupby(["arm", "policy", "category"])
                   .size().rename("hosts").reset_index())
    total_obs = (runs.groupby(["arm", "policy"])["hosts_total"].sum()
                     .rename("observations").reset_index())
    tally = tally.merge(total_obs, on=["arm", "policy"])
    tally["per_1000_observations"] = 1000 * tally["hosts"] / tally["observations"]
    print(f"{'arm':<20} {'policy':<7} {'category':<38} {'hosts':>6} {'/1000':>7}")
    for _, r in tally.sort_values(["arm", "policy", "category"]).iterrows():
        print(f"{r['arm']:<20} {r['policy']:<7} {r['category']:<38} "
              f"{int(r['hosts']):6d} {r['per_1000_observations']:7.3f}")

    print("\n### Did any host arrive, but too late to be matched?")
    late = misses[misses["rejected_arrivals"] > 0]
    print(f"rows with at least one rejected arrival: {len(late)} of {len(misses)}")
    if len(late):
        print(late.groupby(["arm", "policy", "budget_seconds"]).size().to_string())
        print("\nrtt vs the window it missed, for those rows:")
        cols = ["arm", "policy", "budget_seconds", "rtt_seconds",
                "first_rejected_arrival_seconds", "last_send_seconds",
                "horizon_seconds"]
        print(late[cols].head(20).to_string(index=False))

    print("\n### Split vs fixed, paired on the replicate, at each budget")
    piv = runs.pivot_table(index=["arm", "budget_seconds", "replicate"],
                           columns="policy", values="hosts_found")
    piv = piv.dropna().reset_index()
    piv["diff"] = piv["split"] - piv["fixed"]
    agg = piv.groupby(["arm", "budget_seconds"]).agg(
        replicates=("diff", "size"),
        split_ahead=("diff", lambda s: int((s > 0).sum())),
        fixed_ahead=("diff", lambda s: int((s < 0).sum())),
        mean_diff_hosts=("diff", "mean"))
    print(agg.to_string())


if __name__ == "__main__":
    main()
