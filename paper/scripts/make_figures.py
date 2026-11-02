#!/usr/bin/env python3
"""Every figure in the paper, regenerated from the collected data.

    python3 Paper/scripts/make_figures.py

Reads `Study/data/runs.ndjson` and `Study/analysis/strata.json` and writes
`Paper/figures/*.pdf` and `*.png`.  It writes nothing into `Study/`.

The eight figures in `Study/figures/` belong to the simulation study and are not
measurements of anything; none of them is reused, adapted or redrawn here.
"""

from __future__ import annotations

import sys
from collections import defaultdict

import matplotlib.pyplot as plt
import numpy as np

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))

import figstyle as S
import paperdata as D


# ----------------------------------------------------------------------------- utils

def rank_correlation(xs, ys):
    """The analysis's own rank correlation, reproduced so the numbers agree.

    `Study/analysis/shapes.py` ranks with `argsort(argsort(...))`, which is ordinal
    and does not average tied ranks.  Recall is heavily tied — 37 of 109 warm
    unprivileged `-T2` runs sit at 0.40 and 52 at 1.00 — so a tie-corrected Spearman
    would print a different number from the one `RESULTS.md` carries.  The figure uses
    the convention the record uses; on the tie-free covariates the two agree.
    """
    x = np.asarray(xs, dtype=float)
    y = np.asarray(ys, dtype=float)
    if x.size < 3 or x.std() == 0 or y.std() == 0:
        return float("nan")
    return float(np.corrcoef(np.argsort(np.argsort(x)),
                             np.argsort(np.argsort(y)))[0, 1])


def summarise(runs, conditions, cache_state):
    """Median time with a bootstrap interval, median recall, and n, per condition."""
    out = {}
    for condition in conditions:
        sample = [r for r in runs
                  if r.condition_id == condition and r.cache_state == cache_state]
        if not sample:
            continue
        times = [r.wall_clock for r in sample]
        point, low, high = D.bootstrap_median_ci(times)
        out[condition] = {
            "n": len(sample),
            "time": point, "time_low": low, "time_high": high,
            "recall": D.median([r.recall for r in sample]),
        }
    return out


def pareto_front(points):
    """The non-dominated points: nothing is both faster and at least as complete.

    `PROTOCOL.md` H2 is a domination test and `THEORY.md` C5 says it is vacuous
    without a region of interest, so the caller supplies the candidate set.
    """
    front = []
    for name, (time, recall) in points.items():
        dominated = any(
            other != name
            and points[other][0] <= time
            and points[other][1] >= recall
            and (points[other][0] < time or points[other][1] > recall)
            for other in points
        )
        if not dominated:
            front.append(name)
    return sorted(front, key=lambda k: points[k][0])


# -------------------------------------------------------------------- fig 1: frontier

def figure_1_pareto(runs, outdir):
    fig, axes = plt.subplots(2, 1, figsize=(S.COLUMN_IN, 3.25), sharex=True)

    # Label placement is per panel and per point.  At 3.5 in there is no automatic
    # placement that avoids every collision, and a frontier figure whose labels
    # overlap is a frontier figure nobody can read.
    offsets = {
        "warm": {
            "ns.fixed.timeout": (2, 11), "ns.disc.unpriv": (14, -12),
            "ns.budget.shared": (2, 11), "nmap.sn.priv.T5": (-7, -13),
            "nmap.sn.priv.T4": (-3, 11), "nmap.sn.priv.T3": (23, -4),
            "nmap.sn.priv.T2": (-2, 11), "nmap.sn.unpriv.T5": (-15, 2),
            "nmap.sn.unpriv.T3": (1, 10), "nmap.sn.unpriv.T4": (21, -5),
            "nmap.sn.unpriv.T2": (0, 11),
        },
        "cold": {
            "ns.fixed.timeout": (3, -12), "ns.disc.unpriv": (17, 5),
            "ns.budget.shared": (-2, 11), "nmap.sn.priv.T5": (-2, -13),
            "nmap.sn.priv.T4": (16, 11), "nmap.sn.priv.T3": (-21, 11),
            "nmap.sn.priv.T2": (-2, 11), "nmap.sn.unpriv.T5": (-15, 2),
            "nmap.sn.unpriv.T3": (1, 10), "nmap.sn.unpriv.T4": (21, -5),
            "nmap.sn.unpriv.T2": (0, 11),
        },
    }

    for ax, cache_state, title in zip(
            axes, ("warm", "cold"),
            ("(a) warm cache — 1,458 of the 1,580 runs",
             "(b) cold cache — one flushed run per block")):
        stats = summarise(runs, D.DISCOVERY_CONDITIONS, cache_state)
        nmap_points = {k: (v["time"], v["recall"])
                       for k, v in stats.items() if k.startswith("nmap.")}
        front = pareto_front(nmap_points)
        best_time, best_recall = nmap_points[front[0]]

        # The quadrant that *beats* nmap's frontier: faster and at least as complete.
        # H2 is answered by which points fall inside it, so it is drawn rather than
        # left for the reader to construct from two coordinates.
        ax.axvspan(0, best_time, ymin=0, ymax=1, color="none")
        ax.fill_between([1e-3, best_time], best_recall, 1.14,
                        color=S.BLUE, alpha=0.07, linewidth=0, zorder=0)
        ax.plot([best_time, best_time], [best_recall, 1.14],
                color=S.ORANGE, linewidth=0.8, linestyle=(0, (3.5, 2)), zorder=1)
        ax.plot([1e-3, best_time], [best_recall, best_recall],
                color=S.ORANGE, linewidth=0.8, linestyle=(0, (3.5, 2)), zorder=1)

        for condition, value in stats.items():
            ax.errorbar(value["time"], value["recall"],
                        xerr=[[max(value["time"] - value["time_low"], 0)],
                              [max(value["time_high"] - value["time"], 0)]],
                        fmt=S.marker(condition), color=S.color(condition),
                        markersize=3.4, elinewidth=0.9, capsize=1.4,
                        markeredgecolor="white", markeredgewidth=0.4, zorder=3)

        for condition, value in stats.items():
            dx, dy = offsets[cache_state].get(condition, (0, 9))
            ax.annotate(f"{D.SHORT[condition]}\n$n$={value['n']}",
                        (value["time"], value["recall"]),
                        textcoords="offset points", xytext=(dx, dy),
                        ha="center", va="center", fontsize=5.0,
                        color=S.INK_2, linespacing=0.95, zorder=4)

        if cache_state == "warm":
            ax.annotate("everything in here is faster than\n"
                        "nmap's whole frontier and at least\n"
                        "as complete — H2's question",
                        (0.27, 0.40), xycoords=("data", "axes fraction"),
                        fontsize=5.2, color=S.BLUE, linespacing=1.2, zorder=2)

        ax.set_xscale("log")
        ax.set_ylim(0.32, 1.14)
        ax.set_yticks([0.4, 0.6, 0.8, 1.0])
        ax.set_ylabel("median recall")
        ax.set_title(title, loc="left", fontsize=6.6, color=S.INK, pad=2)
        S.recessive(ax, x=True, y=True)

    axes[0].set_xlim(0.17, 1.2e4)
    axes[1].set_xlabel("median time to complete (s), log scale")

    handles = [
        plt.Line2D([], [], marker="o", color=S.BLUE, linestyle="none",
                   markersize=3.4, label="netsanity"),
        plt.Line2D([], [], marker="s", color=S.ORANGE, linestyle="none",
                   markersize=3.4, label="nmap $-$sn, root"),
        plt.Line2D([], [], marker="^", color=S.VIOLET, linestyle="none",
                   markersize=3.4, label="nmap $-$sn, no root"),
        plt.Line2D([], [], color=S.ORANGE, linestyle=(0, (3.5, 2)), linewidth=0.8,
                   label="nmap's frontier"),
    ]
    axes[0].legend(handles=handles, loc="lower right", ncol=1, fontsize=5.8,
                   bbox_to_anchor=(1.005, -0.03))
    fig.tight_layout(pad=0.25, h_pad=0.9)
    S.save(fig, "fig1_pareto", outdir)
    plt.close(fig)


# --------------------------------------------------------------- fig 2: distributions

def figure_2_distributions(runs, outdir):
    fig, ax = plt.subplots(figsize=(S.COLUMN_IN, 2.45))
    rng = np.random.default_rng(20260922)

    order = list(D.ALL_CONDITIONS)
    for row, condition in enumerate(order):
        y = len(order) - row
        warm = [r.wall_clock for r in runs
                if r.condition_id == condition and r.cache_state == "warm"]
        cold = [r.wall_clock for r in runs
                if r.condition_id == condition and r.cache_state == "cold"]
        jitter = rng.uniform(-0.17, 0.17, len(warm))
        ax.scatter(warm, y + jitter, s=1.6, color=S.color(condition), alpha=0.35,
                   linewidths=0, zorder=2)
        cold_jitter = rng.uniform(-0.09, 0.09, len(cold))
        ax.scatter(cold, y + 0.30 + cold_jitter, s=3.0, facecolors="none",
                   edgecolors=S.INK, linewidths=0.45, zorder=4)
        if warm:
            q1, med, q3 = (D.quantile(warm, 0.25), D.median(warm),
                           D.quantile(warm, 0.75))
            ax.plot([q1, q3], [y - 0.34, y - 0.34], color=S.INK_2, linewidth=1.0,
                    solid_capstyle="butt", zorder=3)
            ax.plot([med], [y - 0.34], marker="|", color=S.INK, markersize=5,
                    markeredgewidth=1.0, zorder=5)

    ax.set_yticks([len(order) - i for i in range(len(order))])
    ax.set_yticklabels([D.SHORT[c] for c in order], fontsize=6.0)
    ax.set_ylim(0.3, len(order) + 0.9)
    ax.set_xscale("log")
    ax.set_xlim(0.2, 4200)
    ax.set_xlabel("time to complete (s), one point per run, log scale")
    S.recessive(ax, x=True, y=False)
    ax.tick_params(axis="y", length=0)

    handles = [
        plt.Line2D([], [], marker="o", color=S.MUTED, linestyle="none",
                   markersize=2.4, label="one warm run"),
        plt.Line2D([], [], marker="o", markerfacecolor="none",
                   markeredgecolor=S.INK, linestyle="none", markersize=3.0,
                   markeredgewidth=0.45, label="one cold run"),
        plt.Line2D([], [], color=S.INK_2, linewidth=1.0, label="IQR, median"),
    ]
    ax.legend(handles=handles, loc="upper left", ncol=3, fontsize=5.8,
              bbox_to_anchor=(-0.02, 1.075))
    fig.tight_layout(pad=0.25)
    S.save(fig, "fig2_distributions", outdir)
    plt.close(fig)


# ------------------------------------------------------------ fig 3: recall by cache

def figure_3_recall_by_cache(runs, outdir):
    order = [c for c in D.ALL_CONDITIONS if c != "nmap.naming.broadcast"]
    fig, ax = plt.subplots(figsize=(S.COLUMN_IN, 2.55))

    height = 0.40
    for row, condition in enumerate(order):
        y = len(order) - row
        for offset, cache_state, face in ((+height / 2, "warm", None),
                                          (-height / 2, "cold", "none")):
            sample = [r for r in runs if r.condition_id == condition
                      and r.cache_state == cache_state]
            if not sample:
                continue
            value = D.median([r.recall for r in sample])
            ax.barh(y + offset, value, height=height * 0.92,
                    color=S.color(condition) if face is None else "none",
                    edgecolor=S.color(condition), linewidth=0.7,
                    hatch=None if face is None else "////", zorder=2)
            ax.annotate(f"{value:.2f}  ($n$={len(sample)})",
                        (value, y + offset), textcoords="offset points",
                        xytext=(3, 0), va="center", fontsize=5.0, color=S.INK_2)

    ax.set_yticks([len(order) - i for i in range(len(order))])
    ax.set_yticklabels([D.SHORT[c] for c in order], fontsize=6.0)
    ax.set_ylim(0.35, len(order) + 1.15)
    ax.set_xlim(0, 1.42)
    ax.set_xticks([0, 0.25, 0.5, 0.75, 1.0])
    ax.set_xlabel("median per-block recall against the ten declared responders")
    S.recessive(ax, x=True, y=False)
    ax.tick_params(axis="y", length=0)

    handles = [
        plt.Line2D([], [], marker="s", color=S.MUTED, linestyle="none",
                   markersize=4, label="warm"),
        plt.Line2D([], [], marker="s", markerfacecolor="none",
                   markeredgecolor=S.MUTED, linestyle="none", markersize=4,
                   label="cold"),
    ]
    ax.legend(handles=handles, loc="upper center", ncol=2, fontsize=5.8,
              bbox_to_anchor=(0.5, 1.035))
    fig.tight_layout(pad=0.25)
    S.save(fig, "fig3_recall_by_cache", outdir)
    plt.close(fig)


# ------------------------------------------------------- fig 4: the declaration budget

def figure_4_declaration_budget(runs, outdir):
    fig, (top, bottom) = plt.subplots(2, 1, figsize=(S.COLUMN_IN, 2.85))

    # (a) the discovery stage's own elapsed time against the RTTs it has to cover.
    conditions = ["ns.fixed.timeout", "ns.disc.unpriv", "ns.naming.full",
                  "ns.budget.shared"]
    width = 0.34
    for index, condition in enumerate(conditions):
        for offset, cache_state, filled in ((-width / 2, "warm", True),
                                            (+width / 2, "cold", False)):
            sample = [r.replies_seen for r in runs if r.condition_id == condition
                      and r.cache_state == cache_state]
            elapsed = [r.raw["parse"]["discovery"]["elapsed_millis"]
                       for r in runs if r.condition_id == condition
                       and r.cache_state == cache_state]
            if not elapsed:
                continue
            value = D.median(elapsed)
            top.bar(index + offset, value, width=width * 0.92,
                    color=S.BLUE if filled else "none", edgecolor=S.BLUE,
                    linewidth=0.7, zorder=3)
            top.annotate(f"{value:.0f}", (index + offset, value),
                         textcoords="offset points", xytext=(0, 1.5),
                         ha="center", fontsize=5.2, color=S.INK_2)

    for rtt, label in zip(D.SEGMENT_RTT_MS, ("1 ms", "5 ms", "25 ms", "100 ms", "")):
        top.axhline(rtt, color=S.MUTED, linewidth=0.45, linestyle=(0, (1.6, 1.6)),
                    zorder=1)
        if label:
            top.annotate(label, (1.0, rtt), xycoords=("axes fraction", "data"),
                         textcoords="offset points", xytext=(2, -1.5), ha="left",
                         va="center", fontsize=5.0, color=S.MUTED,
                         annotation_clip=False)
    top.axhline(D.SEGMENT_RTT_MS[-1], color=S.ORANGE, linewidth=0.9,
                linestyle=(0, (3, 2)), zorder=2)
    top.annotate("$q_{high}$: the segment's slowest\nresponders answer at 508 ms",
                 (0.985, 0.90), xycoords="axes fraction", ha="right", va="top",
                 fontsize=5.4, color=S.ORANGE, linespacing=1.15)
    top.set_yscale("log")
    top.set_ylim(0.6, 60000)
    top.set_xticks(range(len(conditions)))
    top.set_xticklabels([D.SHORT[c] for c in conditions], fontsize=6.0)
    top.set_ylabel("discovery stage (ms)")
    top.set_title("(a) the declaration budget against the round trips it must cover",
                  loc="left", fontsize=6.4, color=S.INK, pad=2)
    S.recessive(top, y=True)

    # (b) what reached the wire, what the sweep attributed, what the artifact reported.
    #
    # `ns.naming.full` alone, because it is the only netsanity condition whose process
    # outlives the segment's slowest round trip by enough for the per-run capture to
    # be a fair witness: it lives 3.08 s against a 508 ms tail.  The discovery-only
    # conditions exit at 0.35-0.42 s and their captures close before the slow replies
    # land, so a low wire count there measures the capture window and not the sweep.
    groups = [("warm", "warm cache"), ("cold", "cold cache")]
    labels = []
    series = [
        ("ICMP echo replies on the wire", S.AQUA,
         lambda r: r.raw["capture"]["wire"]["icmp_echo_replies"]),
        ("attributed by the sweep", S.BLUE, lambda r: r.replies_seen),
        ("hosts in the artifact", S.VIOLET, lambda r: r.hosts_found),
    ]
    width = 0.24
    for index, (cache_state, _) in enumerate(groups):
        sample = [r for r in runs if r.condition_id == "ns.naming.full"
                  and r.cache_state == cache_state]
        for slot, (_, colour, getter) in enumerate(series):
            value = D.median([getter(r) for r in sample])
            x = index + (slot - 1) * width
            bottom.bar(x, value, width=width * 0.9, color=colour, linewidth=0,
                       zorder=3)
            bottom.annotate(f"{value:g}", (x, value), textcoords="offset points",
                            xytext=(0, 1.5), ha="center", fontsize=5.4,
                            color=S.INK_2)
        labels.append(f"{groups[index][1]}\n$n$={len(sample)}")
    bottom.axhline(10, color=S.INK_2, linewidth=0.7, linestyle=(0, (3, 2)), zorder=2)
    bottom.annotate("ten declared responders", (-0.45, 10),
                    textcoords="offset points", xytext=(0, 2.5), ha="left",
                    fontsize=5.4, color=S.INK_2)
    bottom.set_xticks(range(len(groups)))
    bottom.set_xticklabels(labels, fontsize=6.2)
    bottom.set_xlim(-0.55, len(groups) - 0.45)
    bottom.set_ylim(0, 19.5)
    bottom.set_yticks([0, 5, 10, 15])
    bottom.set_ylabel("count, median over runs")
    bottom.set_title("(b) ns full: the same replies arrive and are not attributed;\n"
                     "      only the warm run's neighbour table makes up the difference",
                     loc="left", fontsize=6.4, color=S.INK, pad=2)
    S.recessive(bottom, y=True)
    bottom.legend(handles=[plt.Line2D([], [], marker="s", color=c, linestyle="none",
                                      markersize=4, label=label)
                           for label, c, _ in series],
                  loc="upper right", ncol=1, fontsize=5.5,
                  handletextpad=0.4)

    handles = [
        plt.Line2D([], [], marker="s", color=S.BLUE, linestyle="none",
                   markersize=4, label="warm"),
        plt.Line2D([], [], marker="s", markerfacecolor="none", markeredgecolor=S.BLUE,
                   linestyle="none", markersize=4, label="cold"),
    ]
    top.legend(handles=handles, loc="upper left", ncol=2, fontsize=5.8,
               bbox_to_anchor=(0.005, 0.99))
    fig.tight_layout(pad=0.25, h_pad=1.1)
    S.save(fig, "fig4_declaration_budget", outdir)
    plt.close(fig)


# ------------------------------------------------------------- fig 5: the ARP covariate

def figure_5_arp(runs, outdir):
    fig, (top, bottom) = plt.subplots(2, 1, figsize=(S.COLUMN_IN, 2.4))

    t2 = [r for r in runs
          if r.condition_id == "nmap.sn.unpriv.T2" and r.cache_state == "warm"]
    xs = [r.arp_requests for r in t2]
    ys = [r.wall_clock for r in t2]
    recalls = [r.recall for r in t2]
    # Recall is a magnitude here, so it gets a sequential ramp in one hue rather than
    # a categorical assignment.
    ramp = plt.cm.get_cmap("Purples") if hasattr(plt.cm, "get_cmap") else None
    scatter = top.scatter(xs, ys, c=recalls, cmap="Purples", vmin=0.25, vmax=1.0,
                          s=6, linewidths=0.25, edgecolors=S.INK_2, zorder=3)
    bar = fig.colorbar(scatter, ax=top, pad=0.015, fraction=0.045)
    bar.set_label("per-run recall", fontsize=5.8)
    bar.ax.tick_params(labelsize=5.4, length=1.8)
    bar.outline.set_linewidth(0.4)

    top.annotate(
        f"$\\rho$(wall clock, ARP) = {rank_correlation(xs, ys):+.3f}\n"
        f"$\\rho$(recall, wall clock) = {rank_correlation(recalls, ys):+.3f}\n"
        f"$n$ = {len(t2)} warm runs",
        (0.97, 0.05), xycoords="axes fraction", va="bottom", ha="right",
        fontsize=5.6, color=S.INK_2, linespacing=1.25)
    top.set_yscale("log")
    top.set_xlabel("ARP requests emitted by the scanning host's kernel")
    top.set_ylabel("time (s)")
    top.set_title("(a) unprivileged $-$T2: the run length is the kernel's retry count",
                  loc="left", fontsize=6.4, color=S.INK, pad=2)
    S.recessive(top, x=True, y=True)

    markers = {"nmap.sn.unpriv.T3": "^", "nmap.sn.unpriv.T4": "v",
               "nmap.sn.unpriv.T5": "<"}
    for condition, mark in markers.items():
        sample = [r for r in runs
                  if r.condition_id == condition and r.cache_state == "warm"]
        xs = [r.arp_requests for r in sample]
        ys = [r.wall_clock for r in sample]
        bottom.scatter(xs, ys, marker=mark, s=5, alpha=0.6, linewidths=0,
                       color=S.VIOLET, zorder=3,
                       label=f"{D.SHORT[condition]}  $\\rho$={rank_correlation(xs, ys):+.2f}")
    bottom.set_xlabel("ARP requests emitted by the scanning host's kernel")
    bottom.set_ylabel("time (s)")
    bottom.set_title("(b) the same covariate at the three fast templates",
                     loc="left", fontsize=6.4, color=S.INK, pad=2)
    bottom.legend(loc="lower right", fontsize=5.6, ncol=1)
    S.recessive(bottom, x=True, y=True)

    fig.tight_layout(pad=0.25, h_pad=1.2)
    S.save(fig, "fig5_arp_versus_wall_clock", outdir)
    plt.close(fig)


def main():
    S.apply()
    runs = D.runs()
    print(f"{len(runs)} admissible runs from {D.RUNS}")
    outdir = D.FIGURES
    figure_1_pareto(runs, outdir)
    figure_2_distributions(runs, outdir)
    figure_3_recall_by_cache(runs, outdir)
    figure_4_declaration_budget(runs, outdir)
    figure_5_arp(runs, outdir)


if __name__ == "__main__":
    main()
