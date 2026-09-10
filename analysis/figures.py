"""Every figure, from the CSV and nothing else.

Matplotlib only.  No seaborn, no style sheets, no rcParams file: every visual choice
is written here so a reader gets the same figure on a machine configured differently.

The figures are sized for a two-column paper (single column 3.4 in, full width 7.0 in)
and must survive greyscale printing, so nothing is distinguished by colour alone —
every series carries a distinct marker and a distinct dash pattern, and the palette is
a ramp of greys rather than hues.
"""

from __future__ import annotations

import math
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

import load
import pareto

# ---------------------------------------------------------------------------------
# Presentation, stated once and explicitly.
# ---------------------------------------------------------------------------------

plt.rcParams.update({
    "font.family": "sans-serif",
    "font.sans-serif": ["DejaVu Sans", "Helvetica", "Arial", "sans-serif"],
    "font.size": 8,
    "axes.labelsize": 8,
    "axes.titlesize": 8,
    "xtick.labelsize": 7,
    "ytick.labelsize": 7,
    "legend.fontsize": 7,
    "legend.frameon": False,
    "axes.linewidth": 0.6,
    "grid.linewidth": 0.4,
    "lines.linewidth": 1.1,
    "lines.markersize": 3.6,
    "xtick.direction": "out",
    "ytick.direction": "out",
    "xtick.major.width": 0.6,
    "ytick.major.width": 0.6,
    "figure.dpi": 110,
    "savefig.dpi": 400,
    "savefig.bbox": "tight",
    "savefig.pad_inches": 0.02,
    "pdf.fonttype": 42,          # embed real fonts, not type-3 outlines
    "ps.fonttype": 42,
})

SINGLE = (3.4, 2.5)
WIDE = (7.0, 2.6)

# Distinct in greyscale by three independent channels at once.
SERIES = [
    {"color": "0.00", "marker": "o", "ls": "-", "mfc": "0.00"},
    {"color": "0.42", "marker": "s", "ls": "--", "mfc": "white"},
    {"color": "0.62", "marker": "^", "ls": "-.", "mfc": "0.62"},
    {"color": "0.30", "marker": "D", "ls": ":", "mfc": "white"},
    {"color": "0.75", "marker": "v", "ls": (0, (3, 1, 1, 1, 1, 1)), "mfc": "0.75"},
]


def style(i):
    s = dict(SERIES[i % len(SERIES)])
    return {"color": s["color"], "marker": s["marker"], "linestyle": s["ls"],
            "markerfacecolor": s["mfc"], "markeredgecolor": s["color"],
            "markeredgewidth": 0.8}


def tidy(ax):
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.grid(True, color="0.88", linewidth=0.4)
    ax.set_axisbelow(True)


def save(fig, name):
    out = load.FIGURES
    out.mkdir(parents=True, exist_ok=True)
    for ext in ("png", "pdf"):
        fig.savefig(out / f"{name}.{ext}")
    plt.close(fig)
    print(f"  {name}.png  {name}.pdf")


def paired_speedup(d, key):
    piv = d.pivot_table(index=[key, "replicate"], columns="policy",
                        values="sweep_seconds")
    med = piv.groupby(level=0).median()
    med["speedup"] = med["fixed"] / med["split"]
    return med


# ---------------------------------------------------------------------------------


def fig_speedup_vs_dispersion(df):
    d = df[df.experiment == "e1_dispersion"]
    W = int(d["waves_expected"].iloc[0])
    med = paired_speedup(d, "dispersion")
    x = list(med.index)

    fig, ax = plt.subplots(figsize=SINGLE)
    fine = [1 + i * 0.25 for i in range(int((120 - 1) / 0.25) + 1)]
    ax.plot(fine, [W * v / (W - 1 + v) for v in fine], color="0.55",
            linestyle="-", linewidth=0.9, zorder=1,
            label=r"$Wd/(W\!-\!1\!+\!d)$, $W=%d$" % W)
    ax.axhline(W, color="0.0", linestyle=":", linewidth=0.8, zorder=1)
    ax.annotate(f"asymptote = wave count $W$ = {W}", xy=(1.5, W), xytext=(1.5, W - 0.45),
                fontsize=6.5, color="0.15")

    st = style(0)
    ax.plot(x, med["speedup"], label="simulated", zorder=3, **st)

    # THEORY.md correction C2, as recorded, for contrast.
    c2_x = [1.0, 2.041, 4.082, 7.143, 12.245, 20.408, 40.816]
    c2_y = [1.00, 1.69, 2.53, 3.21, 3.77, 4.18, 4.55]
    st = style(1)
    ax.plot(c2_x, c2_y, label="THEORY.md C2, as recorded", zorder=2, **st)

    ax.set_xscale("log")
    ax.set_xticks([1, 2, 4, 8, 16, 32, 80])
    ax.get_xaxis().set_major_formatter(matplotlib.ticker.ScalarFormatter())
    ax.set_xlabel(r"RTT dispersion $q_{\mathrm{high}}/q_{\mathrm{low}}$")
    ax.set_ylabel("median speedup, fixed / split")
    ax.set_ylim(0.8, 5.2)
    ax.set_xlim(0.9, 110)
    ax.legend(loc="lower right")
    tidy(ax)
    save(fig, "fig1_speedup_vs_dispersion")


def fig_pareto(df):
    pts = pareto.points(df[df.experiment == "e2_frontier"])
    fixed = pts[pts.policy == "fixed"].sort_values("budget_seconds")
    split = pts[pts.policy == "split"].sort_values("budget_seconds")
    roi = pareto.REGION_OF_INTEREST

    fig, ax = plt.subplots(figsize=SINGLE)
    ax.axhspan(roi, 1.06, color="0.90", zorder=0, linewidth=0)
    ax.axhline(roi, color="0.35", linestyle="--", linewidth=0.7, zorder=1)

    st = style(0)
    ax.plot(fixed["time_median"], fixed["recall"],
            label="fixed budget $T$", zorder=3, **st)
    st = style(1)
    ax.plot(split["time_median"], split["recall"],
            label="split, declaration window $t$", zorder=3, **st)

    worst = fixed.iloc[0]
    ax.annotate(f"$T$ = {worst['budget_seconds']*1000:.0f} ms, recall "
                f"{worst['recall']:.3f}:\nthe degenerate frontier point",
                xy=(worst["time_median"], worst["recall"]),
                xytext=(0.46, 0.06), textcoords="axes fraction",
                fontsize=6.2, color="0.15", ha="left", va="bottom",
                arrowprops=dict(arrowstyle="-", color="0.55", linewidth=0.5,
                                shrinkA=1, shrinkB=3))
    ax.text(0.975, 0.875, f"region of interest: recall $\\geq$ {roi:.2f}",
            transform=ax.transAxes, va="top", ha="right", fontsize=6.5,
            color="0.25")

    ax.set_xscale("log")
    ax.set_xticks([0.2, 0.3, 0.5, 1.0, 2.0, 3.0, 5.0])
    ax.get_xaxis().set_major_formatter(matplotlib.ticker.FuncFormatter(
        lambda v, _: f"{v:g}"))
    ax.get_xaxis().set_minor_formatter(matplotlib.ticker.NullFormatter())
    ax.set_xlabel("median sweep time (s), log scale")
    ax.set_ylabel("recall")
    ax.set_ylim(0.0, 1.06)
    ax.set_xlim(0.17, 6.5)
    ax.legend(loc="upper left", bbox_to_anchor=(0.40, 0.50))
    tidy(ax)
    save(fig, "fig2_pareto_frontier")


def fig_recall_vs_attempts(df):
    d = df[df.experiment == "e6_attempts"]
    g = d.groupby(["loss_rate", "attempts_k", "policy"], as_index=False)[
        ["hosts_found", "hosts_total"]].sum()
    g["recall"] = g["hosts_found"] / g["hosts_total"]

    fig, axes = plt.subplots(1, 2, figsize=WIDE, sharey=True)
    for ax, policy, title in zip(axes, ("fixed", "split"),
                                 ("fixed budget", "split budget")):
        sub = g[g.policy == policy]
        for i, (loss, gg) in enumerate(sub.groupby("loss_rate")):
            gg = gg.sort_values("attempts_k")
            ax.plot(gg["attempts_k"], gg["recall"],
                    label=f"$\\ell$ = {loss:g}", **style(i))
            ax.plot(gg["attempts_k"], [1 - loss ** k for k in gg["attempts_k"]],
                    color="0.70", linestyle=(0, (1, 1.5)), linewidth=0.7, zorder=1)
        ax.set_xlabel("transmissions per address, $k$")
        ax.set_xticks([1, 2, 3, 4, 5])
        ax.set_title(title)
        tidy(ax)
    axes[0].set_ylabel("recall (pooled)")
    axes[0].set_ylim(0.6, 1.02)
    axes[1].legend(loc="lower right", ncol=1)
    axes[0].annotate(r"dotted: the bound $1-\ell^{\,k}$", xy=(1.1, 0.625),
                     fontsize=6.5, color="0.35")
    save(fig, "fig3_recall_vs_attempts")


def fig_model_residuals(df):
    """Ratio of simulated to predicted, which is what a residual plot should show:
    an observed-against-predicted scatter on log axes hides a 30% error."""
    forms = [("residual_naive_ratio", "model_naive_seconds",
              "sections 4 and 5, as written"),
             ("residual_wave_ratio", "model_wave_seconds",
              "wave form (correction C1)"),
             ("residual_wave_last_ratio", "model_wave_last_seconds",
              "wave form, last interval removed")]
    df = df.copy()
    df["dead_dominated"] = df["host_density"] < 0.05

    fig, axes = plt.subplots(1, 3, figsize=WIDE, sharey=True)
    for ax, (rcol, pcol, title) in zip(axes, forms):
        ax.axhline(1.0, color="0.45", linewidth=0.8, zorder=2)
        for i, policy in enumerate(("fixed", "split")):
            for dead in (True, False):
                sub = df[(df.policy == policy) & (df.dead_dominated == dead)]
                if sub.empty:
                    continue
                st = style(i)
                ax.scatter(sub[pcol], sub[rcol], s=2.4,
                           marker=st["marker"],
                           facecolors=(st["color"] if dead else "none"),
                           edgecolors=st["color"], linewidths=0.3,
                           zorder=3,
                           label=(f"{policy}, "
                                  f"{'h/N < 5%' if dead else 'h/N >= 5%'}"))
        ax.set_xscale("log")
        ax.set_title(title, fontsize=7)
        ax.set_xlabel("predicted sweep time (s)")
        tidy(ax)
    axes[0].set_ylabel("simulated / predicted")
    axes[0].set_ylim(0.33, 1.8)
    axes[0].legend(loc="lower left", handletextpad=0.3, borderpad=0.2,
                   labelspacing=0.22, markerscale=2.4)
    save(fig, "fig4_model_residuals")


def fig_density(df):
    fig, ax = plt.subplots(figsize=SINGLE)
    for i, (exp, label) in enumerate((("e3_density", "$c$ = 240, 4 waves"),
                                      ("e3b_density_c64", "$c$ = 64, 12 waves"))):
        d = df[df.experiment == exp]
        if d.empty:
            continue
        med = paired_speedup(d, "n_hosts")
        n = float(d["n_addrs"].iloc[0])
        ax.plot([h / n for h in med.index], med["speedup"], label=label, **style(i))
    ax.axhline(1.0, color="0.35", linestyle=":", linewidth=0.8)
    ax.set_xscale("log")
    ax.set_xlabel("live hosts as a fraction of addresses")
    ax.set_ylabel("median speedup, fixed / split")
    ax.legend(loc="lower left")
    tidy(ax)
    save(fig, "fig5_density_crossover")


def fig_scale(df):
    d = df[df.experiment == "e4_scale"]
    med = paired_speedup(d, "n_addrs")
    waves = d.groupby("n_addrs")["waves_expected"].first()
    disp = float(d["dispersion"].iloc[0])
    fig, ax = plt.subplots(figsize=SINGLE)
    ax.plot(list(med.index), med["speedup"], label="simulated", **style(0))
    ax.plot(list(med.index), [waves[n] * disp / (waves[n] - 1 + disp)
                              for n in med.index],
            color="0.55", linewidth=0.9, linestyle="-", zorder=1,
            label=r"$Wd/(W\!-\!1\!+\!d)$")
    ax.axhline(disp, color="0.0", linestyle=":", linewidth=0.8)
    ax.annotate(f"asymptote = dispersion = {disp:g}", xy=(300, disp - 1.0),
                fontsize=6.5, color="0.15")
    ax.set_xscale("log")
    ax.set_xlabel("addresses swept, $N$ (concurrency and density held fixed)")
    ax.set_ylabel("median speedup, fixed / split")
    ax.set_xticks([254, 1022, 4094, 16382, 65534])
    ax.set_xticklabels(["/24", "/22", "/20", "/18", "/16"])
    ax.legend(loc="lower right")
    tidy(ax)
    save(fig, "fig6_scale")


def fig_bursty(df):
    d = df[df.experiment == "e5_bursty"]
    g = d.groupby(["burst_seconds", "policy"], as_index=False)[
        ["hosts_found", "hosts_total"]].sum()
    g["recall"] = g["hosts_found"] / g["hosts_total"]
    # The independent-loss condition has no outage duration at all; it is drawn at the
    # left edge and labelled, rather than silently placed at some arbitrary small
    # number on a log axis.
    edge = 0.008
    fig, ax = plt.subplots(figsize=SINGLE)
    for i, policy in enumerate(("fixed", "split")):
        sub = g[g.policy == policy].sort_values("burst_seconds")
        x = [max(v, edge) for v in sub["burst_seconds"]]
        y = list(sub["recall"])
        ax.plot(x, y, **style(i))
        ax.annotate(policy, xy=(x[-1], y[-1]), xytext=(4, -1),
                    textcoords="offset points", fontsize=7,
                    color=style(i)["color"], va="center")
    ax.axvline(edge, color="0.75", linewidth=0.5)
    ax.annotate("independent loss", xy=(edge * 1.15, 0.845), fontsize=6.2,
                color="0.35", rotation=90, va="bottom")
    r = float(d["retransmit_r_seconds"].iloc[0])
    ax.axvline(r, color="0.35", linestyle="--", linewidth=0.7)
    ax.annotate(f"retransmission interval\n$r$ = {r*1000:.0f} ms",
                xy=(r * 1.15, 0.845), fontsize=6.2, color="0.15", va="bottom")
    ax.set_xscale("log")
    ax.set_xlim(edge * 0.85, 3.4)
    ax.set_xlabel("mean outage duration (s), marginal loss held at 0.15")
    ax.set_ylabel("recall (pooled)")
    ax.set_ylim(0.84, 1.008)
    tidy(ax)
    save(fig, "fig7_bursty_loss")


def main():
    df = load.results()
    print("writing figures to", load.FIGURES)
    fig_speedup_vs_dispersion(df)
    fig_pareto(df)
    fig_recall_vs_attempts(df)
    fig_model_residuals(df)
    fig_density(df)
    fig_scale(df)
    fig_bursty(df)
    fig_spacing(df)




def fig_spacing(df):
    """Correction C8's fix: recall against how the loss is distributed in time."""
    e9 = df[df.experiment == "e9_spacing"].copy()
    if e9.empty:
        return
    e9["schedule"] = e9["condition_id"].str.rsplit("_", n=1).str[-1]
    e9["cell"] = e9["condition_id"].str.split("_").str[1]
    e9 = e9[(e9.cell == "deployment") & (e9.loss_model != "periodic")]

    series = [("fixed", "uniform", "fixed budget (comparator)"),
              ("split", "uniform", "three tight transmissions"),
              ("split", "spread", "spread into the tail window"),
              ("split", "late400", "late 400 ms, paid for")]
    edge = 0.008          # where the independent-loss condition is drawn
    fig, ax = plt.subplots(figsize=SINGLE)
    for i, (policy, schedule, label) in enumerate(series):
        sub = e9[(e9.policy == policy) & (e9.schedule == schedule)]
        if sub.empty:
            continue
        g = sub.groupby("burst_seconds", as_index=False)[
            ["hosts_found", "hosts_total"]].sum().sort_values("burst_seconds")
        x = [max(v, edge) for v in g["burst_seconds"]]
        y = g["hosts_found"] / g["hosts_total"]
        ax.plot(x, y, label=label, **style(i))
    ax.axvline(edge, color="0.75", linewidth=0.5)
    ax.annotate("independent loss", xy=(edge * 1.15, 0.848), fontsize=6.2,
                color="0.35", rotation=90, va="bottom")
    ax.set_xscale("log")
    ax.set_xlim(edge * 0.85, 3.4)
    ax.set_ylim(0.84, 1.008)
    ax.set_xlabel("mean outage duration (s), marginal loss held at 0.15")
    ax.set_ylabel("recall (pooled)")
    ax.legend(loc="lower left")
    tidy(ax)
    save(fig, "fig8_spacing_under_correlated_loss")


if __name__ == "__main__":
    main()
