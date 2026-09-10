"""Regenerate every number the write-up cites, from the CSV and nothing else.

Reads only ``data/``.  Touches no network, imports nothing from ``sim/``, and runs
end to end in a few seconds so that a reader can check any figure in the text against
its source without rerunning the simulation.
"""

from __future__ import annotations

import math

import pandas as pd

import load
import pareto

pd.set_option("display.width", 200)


def wilson(k, n, z=1.96):
    return pareto.wilson(k, n, z)


def paired(df, key, value="sweep_seconds"):
    """Median over replicates of each policy, keyed on one condition variable.  The
    policies are paired on the replicate index because they were run against the same
    population, the same loss realisation and the same visiting order."""
    piv = df.pivot_table(index=[key, "replicate"], columns="policy", values=value)
    out = piv.groupby(level=0).median()
    if {"fixed", "split"} <= set(out.columns):
        out["speedup"] = out["fixed"] / out["split"]
    return out


def pooled_recall(df, keys):
    g = df.groupby(keys, as_index=False)[["hosts_found", "hosts_total"]].sum()
    g["recall"] = g["hosts_found"] / g["hosts_total"]
    ci = [wilson(k, n) for k, n in zip(g["hosts_found"], g["hosts_total"])]
    g["ci_lo"] = [c[0] for c in ci]
    g["ci_hi"] = [c[1] for c in ci]
    return g


def rule(title):
    print("\n" + "=" * 78)
    print(title)
    print("=" * 78)


def e1(df):
    rule("e1 — speedup against dispersion, and where it saturates")
    d = df[df.experiment == "e1_dispersion"]
    W = int(d["waves_expected"].iloc[0])
    out = paired(d, "dispersion")
    out["law_W_d_over_W1_d"] = [W * x / (W - 1 + x) for x in out.index]
    out["law_error"] = out["speedup"] - out["law_W_d_over_W1_d"]
    print(f"wave count for this cell: ceil(N*k/c) = ceil({d['n_addrs'].iloc[0]}*"
          f"{d['attempts_k'].iloc[0]}/{d['concurrency_c'].iloc[0]}) = {W}")
    print(out.round(4).to_string())
    print(f"\nasymptote of the fitted law as dispersion -> infinity: {W}")
    print("THEORY.md C2 reported, at the same cell: 1.00, 1.69, 2.53, 3.21, 3.77, "
          "4.18, 4.55")
    print("the same law with W = 5 gives:          "
          + ", ".join(f"{5*x/(4+x):.2f}" for x in
                      (1.0, 2.041, 4.082, 7.143, 12.245, 20.408, 40.816)))


def e2(df):
    rule("e2 — the speed/recall frontier and the domination test")
    pts = pareto.points(df[df.experiment == "e2_frontier"])
    print(pts.round(4).to_string(index=False))
    pareto.report(pts, roi=None, label="no region of interest (as first written)")
    pareto.report(pts, roi=pareto.REGION_OF_INTEREST,
                  label="region of interest, recall >= 0.95")


def e3(df):
    rule("e3 — host density, and where the advantage starts to degrade")
    for exp in ("e3_density", "e3b_density_c64"):
        d = df[df.experiment == exp]
        if d.empty:
            continue
        c = int(d["concurrency_c"].iloc[0])
        n = int(d["n_addrs"].iloc[0])
        T = float(d["fixed_budget_T_seconds"].iloc[0])
        W = int(d["waves_expected"].iloc[0])
        out = paired(d, "n_hosts")
        out["density"] = out.index / n
        out["fixed_over_wave_form"] = out["fixed"] / (W * T)
        sparse = out["speedup"].iloc[0]
        print(f"\n-- {exp}: N={n}, c={c}, waves={W}, sparse speedup {sparse:.3f}x")
        print(out.round(4).to_string())
        knee = out[out["fixed_over_wave_form"] < 0.99]
        if len(knee):
            h = int(knee.index[0])
            print(f"   first density at which the fixed policy beats its own wave "
                  f"form by more than 1%: h = {h} ({h / n:.3%})")
        half = out[out["speedup"] <= sparse / 2]
        if len(half):
            h = int(half.index[0])
            print(f"   first density at which the speedup has halved: h = {h} "
                  f"({h / n:.3%})")
        else:
            print(f"   the speedup never halves; its minimum is "
                  f"{out['speedup'].min():.3f}x at h = "
                  f"{int(out['speedup'].idxmin())}")


def e4(df):
    rule("e4 — scale, at constant density and constant concurrency")
    d = df[df.experiment == "e4_scale"]
    out = paired(d, "n_addrs")
    waves = d.groupby("n_addrs")["waves_expected"].first()
    disp = float(d["dispersion"].iloc[0])
    out["waves"] = waves
    out["law_W_d_over_W1_d"] = [waves[n] * disp / (waves[n] - 1 + disp)
                                for n in out.index]
    out["law_error"] = out["speedup"] - out["law_W_d_over_W1_d"]
    print(f"dispersion held at {disp:g}x, concurrency held at "
          f"{int(d['concurrency_c'].iloc[0])}")
    print(out.round(4).to_string())
    print(f"\nas the wave count grows the law tends to the dispersion itself: "
          f"{disp:g}")


def e5(df):
    rule("e5 — correlated loss")
    d = df[df.experiment == "e5_bursty"]
    t = paired(d, "burst_seconds")
    r = pooled_recall(d, ["burst_seconds", "policy"])
    r = r.pivot(index="burst_seconds", columns="policy", values="recall")
    out = t.join(r, rsuffix="_recall")
    out.columns = ["fixed_seconds", "split_seconds", "speedup",
                   "fixed_recall", "split_recall"]
    out["recall_cost_of_splitting"] = out["fixed_recall"] - out["split_recall"]
    print(f"marginal loss rate held at {d['loss_rate'].iloc[0]}, k="
          f"{d['attempts_k'].iloc[0]}; burst 0 is the independent model")
    print(out.round(4).to_string())


def e6(df):
    rule("e6 — attempts, by loss regime (P5)")
    d = df[df.experiment == "e6_attempts"]
    r = pooled_recall(d, ["loss_rate", "attempts_k", "policy"])
    piv = r.pivot_table(index=["loss_rate", "attempts_k"], columns="policy",
                        values="recall")
    piv["bound"] = [1 - l ** k for l, k in piv.index]
    t = d.pivot_table(index=["loss_rate", "attempts_k", "replicate"],
                      columns="policy", values="sweep_seconds").groupby(
                          level=[0, 1]).median()
    piv["fixed_seconds"] = t["fixed"]
    piv["split_seconds"] = t["split"]
    print(piv.round(4).to_string())
    print("\nmarginal recall of the k-th attempt, split policy:")
    m = piv["split"].unstack(level=1).diff(axis=1)
    print(m.round(4).to_string())


def e7(df):
    rule("e7 — C3 with enough replicates (see also c3_report.py)")
    d = df[df.experiment == "e7_c3"]
    r = pooled_recall(d, ["release_on_reply", "policy", "declare_t_seconds",
                          "fixed_budget_T_seconds"])
    bound = 1 - float(d["loss_rate"].iloc[0]) ** int(d["attempts_k"].iloc[0])
    r["gap_to_bound"] = bound - r["recall"]
    print(f"ceiling 1 - loss^k = {bound:.6f}")
    print(r.round(5).to_string(index=False))


def e8(df):
    rule("e8 — two scheduler choices, and what they cost")
    d = df[df.experiment == "e8_scheduler"]
    f = d[d.policy == "fixed"].copy()
    f["waves_used"] = f["sweep_seconds"] / f["fixed_budget_T_seconds"]
    W = int(d["waves_expected"].iloc[0])
    tab = f.groupby(["tie_break", "release_on_reply"])["waves_used"].agg(
        median="median", mean="mean", max="max")
    tab["fraction_wasting_a_wave"] = f.groupby(
        ["tie_break", "release_on_reply"])["waves_used"].apply(
            lambda s: (s > W + 0.5).mean())
    print(f"expected wave count ceil(N*k/c) = {W}")
    print(tab.round(4).to_string())
    print("\nspeedup by dispersion, for each scheduler:")
    piv = d.pivot_table(index=["tie_break", "release_on_reply", "dispersion",
                               "replicate"],
                        columns="policy", values="sweep_seconds")
    s = piv.groupby(level=[0, 1, 2]).median()
    s["speedup"] = s["fixed"] / s["split"]
    print(s["speedup"].unstack(level=2).round(3).to_string())


def residuals(df):
    rule("Model residuals — THEORY.md sections 4 and 5 against the simulation")
    df = df.copy()
    for form in ("naive", "wave", "wave_last"):
        df[f"abs_{form}"] = (df[f"residual_{form}_seconds"]).abs()
    dead = df[df["host_density"] < 0.05]
    print("Dead-dominated conditions only (host density < 5%, which is the regime "
          "section 14 assumes):")
    g = dead.groupby("policy").agg(
        rows=("sweep_seconds", "size"),
        naive_median_ratio=("residual_naive_ratio", "median"),
        wave_median_ratio=("residual_wave_ratio", "median"),
        wave_last_median_ratio=("residual_wave_last_ratio", "median"),
        naive_max_abs=("abs_naive", "max"),
        wave_max_abs=("abs_wave", "max"),
        wave_last_max_abs=("abs_wave_last", "max"))
    print(g.round(6).to_string())
    print("\nfraction of rows each form predicts to within 1 microsecond:")
    for policy, gg in dead.groupby("policy"):
        line = {form: float((gg[f"abs_{form}"] < 1e-6).mean())
                for form in ("naive", "wave", "wave_last")}
        print(f"  {policy:<6} " + "  ".join(f"{k}={v:.4f}" for k, v in line.items()))
    print("\nSplit residual of the wave form, in units of the retransmission "
          "interval r:")
    sp = dead[dead.policy == "split"]
    ratio = (sp["residual_wave_seconds"] / sp["retransmit_r_seconds"])
    print(f"  median {ratio.median():.6f}   min {ratio.min():.6f}   "
          f"max {ratio.max():.6f}   n={len(ratio)}")
    print("\nBy experiment, median ratio observed/predicted:")
    by = df.groupby(["experiment", "policy"])[
        ["residual_naive_ratio", "residual_wave_ratio",
         "residual_wave_last_ratio"]].median()
    print(by.round(4).to_string())
    print("\nWhere the wave form breaks: conditions whose median ratio is not 1.")
    bad = by[(by["residual_wave_last_ratio"] - 1).abs() > 0.01]
    print(bad.round(4).to_string() if len(bad) else "  none")


def headline(df):
    rule("Numbers for an abstract")
    e1d = paired(df[df.experiment == "e1_dispersion"], "dispersion")
    W = int(df[df.experiment == "e1_dispersion"]["waves_expected"].iloc[0])
    print(f"1. On a /24 with 240 probes in flight and three transmissions per "
          f"address, splitting the")
    print(f"   retransmission budget from the declaration budget cuts median sweep "
          f"time by")
    print(f"   {e1d.loc[12.0, 'speedup']:.2f}x at 12x RTT dispersion and "
          f"{e1d.loc[80.0, 'speedup']:.2f}x at 80x, with recall unchanged.")
    print(f"2. The advantage saturates at the wave count ceil(N*k/c) = {W}: measured "
          f"speedup follows")
    print(f"   W*d/(W-1+d) to within "
          f"{max(abs(e1d['speedup'] - [W*x/(W-1+x) for x in e1d.index])):.4f} across "
          f"dispersions 1x to 80x.")
    e4d = paired(df[df.experiment == "e4_scale"], "n_addrs")
    print(f"3. Raising the wave count raises the ceiling: at /16 the same "
          f"configuration gives")
    print(f"   {e4d['speedup'].iloc[-1]:.2f}x, approaching the dispersion itself "
          f"rather than a fixed constant.")
    e5d = df[df.experiment == "e5_bursty"]
    r = pooled_recall(e5d, ["burst_seconds", "policy"]).pivot(
        index="burst_seconds", columns="policy", values="recall")
    print(f"4. Under loss correlated in time rather than independent, the speed "
          f"advantage is unchanged")
    print(f"   but recall is not: at a mean outage of 1 s the split policy recovers "
          f"{r.loc[1.0, 'split']:.3f} against")
    print(f"   {r.loc[1.0, 'fixed']:.3f} for the fixed policy, so the trade stops "
          f"being free.")


def main():
    df = load.results()
    print(f"rows: {len(df)}   experiments: "
          f"{', '.join(sorted(df['experiment'].unique()))}")
    e1(df)
    e2(df)
    e3(df)
    e4(df)
    e5(df)
    e6(df)
    e7(df)
    e8(df)
    residuals(df)
    headline(df)


if __name__ == "__main__":
    main()
