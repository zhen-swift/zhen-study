"""The speed/recall frontier, and the domination test done properly.

The scratch version of this test called a 50 ms fixed budget "non-dominated" because
it finished 3 ms sooner than the nearest split configuration — at recall 0.109.  A
Pareto test with no region of interest rewards a scanner for finding nothing, and any
frontier computed that way will always contain a degenerate fast point.  A host
discovery scan that misses nine hosts in ten is not a point on a trade curve, it is a
failure, and the frontier must say so.

PROTOCOL.md section 1 H2 is the claim under test: "for any nmap template, there exists
a netsanity configuration that is both faster and at least as complete".  The
simulation's analogue is: for any fixed budget, does some split configuration exist
that is both faster and at least as complete?

Both frontiers are reported: unrestricted, which is what the scratch script computed,
and restricted to a region of interest of recall >= 0.95, which is the one the paper
should carry.  Reporting only the restricted one would be choosing the answer.
"""

from __future__ import annotations

import math

import pandas as pd

import load

REGION_OF_INTEREST = 0.95


def wilson(k, n, z=1.96):
    if n == 0:
        return (float("nan"), float("nan"))
    p = k / n
    d = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / d
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (centre - half, centre + half)


def points(df):
    """One point per condition: median sweep time (PROTOCOL section 7 — the time
    distribution is right-skewed and a mean flatters the tail) and pooled recall."""
    rows = []
    for cid, g in df.groupby("condition_id"):
        found = int(g["hosts_found"].sum())
        total = int(g["hosts_total"].sum())
        lo, hi = wilson(found, total)
        policy = g["policy"].iloc[0]
        budget = (g["fixed_budget_T_seconds"].iloc[0] if policy == "fixed"
                  else g["declare_t_seconds"].iloc[0])
        rows.append({
            "condition_id": cid,
            "policy": policy,
            "budget_seconds": float(budget),
            "replicates": len(g),
            "time_median": g["sweep_seconds"].median(),
            "time_q1": g["sweep_seconds"].quantile(0.25),
            "time_q3": g["sweep_seconds"].quantile(0.75),
            "recall": found / total,
            "recall_ci_lo": lo,
            "recall_ci_hi": hi,
            "host_observations": total,
        })
    return pd.DataFrame(rows).sort_values(["policy", "budget_seconds"])


def dominated_by(point, challengers):
    """Strict Pareto domination: at least as fast, at least as complete, better in
    one.  Ties in both leave the point standing, which is the conservative reading."""
    for _, c in challengers.iterrows():
        if (c["time_median"] <= point["time_median"]
                and c["recall"] >= point["recall"]
                and (c["time_median"] < point["time_median"]
                     or c["recall"] > point["recall"])):
            return c["condition_id"]
    return None


def report(pts, roi=None, label=""):
    fixed = pts[pts["policy"] == "fixed"]
    split = pts[pts["policy"] == "split"]
    if roi is not None:
        fixed = fixed[fixed["recall"] >= roi]
        split = split[split["recall"] >= roi]
    print(f"\n### {label}")
    if roi is not None:
        print(f"region of interest: recall >= {roi:.2f}")
        excl = pts[(pts["recall"] < roi)]
        print(f"excluded for failing it: "
              f"{', '.join(excl['condition_id']) if len(excl) else 'none'}")
    if fixed.empty:
        print("no fixed point qualifies; the comparison is vacuous here")
        return []
    if split.empty:
        print("no split point qualifies; every fixed point survives by default")
        return list(fixed["condition_id"])
    survivors = []
    print(f"{'fixed condition':<22} {'T':>7} {'median t':>9} {'recall':>8} "
          f"{'verdict':<34}")
    for _, f in fixed.iterrows():
        by = dominated_by(f, split)
        verdict = f"dominated by {by}" if by else "NON-DOMINATED"
        if by is None:
            survivors.append(f["condition_id"])
        print(f"{f['condition_id']:<22} {f['budget_seconds']:7.3f} "
              f"{f['time_median']:9.3f} {f['recall']:8.4f} {verdict:<34}")
    if not survivors:
        print("  -> every fixed budget in this region is dominated by some split "
              "configuration.")
    return survivors


def main():
    df = load.results()
    e2 = df[df["experiment"] == "e2_frontier"]
    pts = points(e2)

    print("=" * 78)
    print("The speed/recall frontier (e2: dispersion "
          f"{e2['dispersion'].iloc[0]:.1f}x, loss {e2['loss_rate'].iloc[0]}, "
          f"k={e2['attempts_k'].iloc[0]})")
    print("=" * 78)
    print(f"{'condition':<22} {'policy':<7} {'budget':>7} {'median t':>9} "
          f"{'IQR':>17} {'recall':>8} {'95% CI':>17}")
    for _, r in pts.iterrows():
        print(f"{r['condition_id']:<22} {r['policy']:<7} {r['budget_seconds']:7.3f} "
              f"{r['time_median']:9.3f} "
              f"[{r['time_q1']:.3f},{r['time_q3']:.3f}] {r['recall']:8.4f} "
              f"[{r['recall_ci_lo']:.4f},{r['recall_ci_hi']:.4f}]")

    report(pts, roi=None,
           label="Frontier as the scratch script computed it (no region of interest)")
    report(pts, roi=REGION_OF_INTEREST,
           label="Frontier over the region of interest")
    return pts


if __name__ == "__main__":
    main()
