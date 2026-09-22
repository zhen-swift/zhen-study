"""Every figure, regenerated from the collected data.

`Study/figures/` holds the simulation's figures.  None of them is a measurement and
none of them may be reused or adapted as though it were, so everything this module
writes goes to `Study/figures/measured/` under names that cannot be confused with
them, and every caption says the file it was computed from.

Figure 1 is the speed/recall Pareto frontier — `PROTOCOL.md` section 7 makes it the
paper's central figure, and this is the first time it has been drawn from measurements
rather than from a model.

Run it:

    python3 analysis/figures_measured.py
"""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

import collection as C  # noqa: E402
import hypotheses as H  # noqa: E402
import stats as S  # noqa: E402

HERE = Path(__file__).resolve().parent
OUT = HERE.parent / "figures" / "measured"

# Three categorical slots, validated all-pairs in light mode: worst CVD deltaE 9.2,
# worst normal-vision deltaE 24.0.  Three and not more because a scatter puts every
# pair on screen at once and the fourth slot fails the floors.  Aqua sits below 3:1
# against the surface, so the relief rule applies and every point carries a visible
# label; the same numbers are in RESULTS.md as a table.
SERIES = {
    "netsanity": "#2a78d6",
    "nmap, privileged": "#eb6834",
    "nmap, unprivileged": "#1baf7a",
}
MARKERS = {"netsanity": "o", "nmap, privileged": "s", "nmap, unprivileged": "^"}
INK = "#0b0b0b"
INK_MUTED = "#52514e"
GRID = "#dedcd6"
SURFACE = "#fcfcfb"

SHORT = {
    "ns.disc.unpriv": "adaptive\n(split budget)",
    "ns.fixed.timeout": "fixed 50 ms\nretransmit",
    "ns.budget.shared": "shared budget",
    "ns.naming.full": "full pipeline\n(discovery + naming)",
    "nmap.sn.priv.T2": "-T2 root", "nmap.sn.priv.T3": "-T3 root",
    "nmap.sn.priv.T4": "-T4 root", "nmap.sn.priv.T5": "-T5 root",
    "nmap.sn.unpriv.T2": "-T2 user", "nmap.sn.unpriv.T3": "-T3 user",
    "nmap.sn.unpriv.T4": "-T4 user", "nmap.sn.unpriv.T5": "-T5 user",
}


def family(condition: str) -> str:
    if condition.startswith("ns."):
        return "netsanity"
    return "nmap, privileged" if ".priv." in condition else "nmap, unprivileged"


def _style(ax) -> None:
    ax.set_facecolor(SURFACE)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(GRID)
        ax.spines[side].set_linewidth(0.8)
    ax.tick_params(colors=INK_MUTED, labelsize=8, length=3, width=0.8)
    ax.grid(True, color=GRID, linewidth=0.6, alpha=0.9)
    ax.set_axisbelow(True)


def _save(fig, name: str) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for extension in ("png", "pdf"):
        fig.savefig(OUT / f"{name}.{extension}", dpi=200, bbox_inches="tight",
                    facecolor=SURFACE)
    plt.close(fig)
    print(f"  {OUT.relative_to(HERE.parent.parent)}/{name}.png / .pdf")


# ── Figure 1 — the Pareto frontier ────────────────────────────────────────────────

def _stagger(positions: list[tuple[float, float]], *, x_tolerance: float = 0.75,
             y_tolerance: float = 0.08) -> list[int]:
    """Label offsets that do not land on top of each other.

    Points are clustered by proximity in (log10 time, recall); within a cluster the
    labels step upward one slot at a time.  Eleven points do not need a solver, and a
    solver would put the label somewhere neither the reader nor the author expects.
    """
    order = sorted(range(len(positions)), key=lambda i: (-positions[i][1], positions[i][0]))
    slots = [0] * len(positions)
    clusters: list[list[int]] = []
    for index in order:
        x, y = positions[index]
        for cluster in clusters:
            cx, cy = positions[cluster[-1]]
            if abs(x - cx) < x_tolerance and abs(y - cy) < y_tolerance:
                cluster.append(index)
                break
        else:
            clusters.append([index])
    for cluster in clusters:
        for level, index in enumerate(cluster):
            slots[index] = level
    return slots


def figure1(runs: list[C.Run]) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(11.6, 5.0), facecolor=SURFACE)
    for ax, arm in zip(axes, ("warm", "cold")):
        subset = C.arm(runs, arm)
        summary = H.per_condition_summary(subset, arm)
        points = {c: summary[c] for c in C.DISCOVERY_CONDITIONS if c in summary}

        nmap_points = {c: (v["time"].median, v["recall_median"])
                       for c, v in points.items() if c.startswith("nmap")}
        frontier = H._frontier(nmap_points)
        if len(frontier) > 1:
            ordered = sorted(frontier, key=lambda c: nmap_points[c][0])
            ax.step([nmap_points[c][0] for c in ordered],
                    [nmap_points[c][1] for c in ordered],
                    where="post", color=INK_MUTED, linewidth=1.2, alpha=0.5, zorder=1)

        names = list(points)
        coordinates = [(np.log10(points[c]["time"].median), points[c]["recall_median"])
                       for c in names]
        slots = _stagger(coordinates)
        for condition, slot in zip(names, slots):
            stat = points[condition]
            group = family(condition)
            time_ci = stat["time_ci"]
            ax.plot([time_ci.low, time_ci.high], [stat["recall_median"]] * 2,
                    color=SERIES[group], linewidth=2.2, alpha=0.45,
                    solid_capstyle="round", zorder=2)
            ax.plot(stat["time"].median, stat["recall_median"],
                    marker=MARKERS[group], markersize=9, color=SERIES[group],
                    markeredgecolor=SURFACE, markeredgewidth=1.6, linestyle="none",
                    zorder=3)
            dy = 12 + 17 * slot
            ax.annotate(
                f"{SHORT[condition].replace(chr(10), ' ')}  n={stat['n']}",
                (stat["time"].median, stat["recall_median"]),
                textcoords="offset points", xytext=(0, dy), ha="center",
                fontsize=7, color=INK_MUTED, zorder=4,
                arrowprops=dict(arrowstyle="-", color=GRID, linewidth=0.7,
                                shrinkA=1, shrinkB=5) if slot else None)

        ax.set_xscale("log")
        ax.set_xlim(0.07, 12000)
        ax.set_xlabel("median wall clock, seconds (log)", fontsize=9, color=INK)
        ax.set_ylim(0.28, 1.42)
        ax.set_yticks([0.4, 0.6, 0.8, 1.0])
        _style(ax)
        counts = sorted(stat["n"] for stat in points.values())
        ax.set_title(
            f"{arm} cache — {len(subset)} runs, n per condition {counts[0]}-{counts[-1]}",
            fontsize=9.5, color=INK, pad=8, loc="left")
    axes[0].set_ylabel("median recall against the declared\nresponder set (10 hosts)",
                       fontsize=9, color=INK)

    handles = [plt.Line2D([], [], marker=MARKERS[k], color=v, linestyle="none",
                          markersize=8, markeredgecolor=SURFACE, label=k)
               for k, v in SERIES.items()]
    axes[1].legend(handles=handles, frameon=False, fontsize=8, loc="lower right",
                   labelcolor=INK_MUTED)
    fig.suptitle("Figure 1 — speed against completeness, measured",
                 fontsize=12.5, color=INK, x=0.055, ha="left", y=1.02)
    fig.text(0.055, -0.045,
             "Point: median wall clock and median per-run recall. Bar: bootstrap 95% "
             "interval on the median time, 10,000 resamples. Grey step: nmap's own "
             "frontier. Up and to the left dominates.\n"
             "Study/data/runs.ndjson, 1,580 runs, 120 complete blocks; the two "
             "excluded runs are dropped and the partial blocks' admissible runs are "
             "kept, as the protocol's exclusion rules have it.",
             fontsize=7.5, color=INK_MUTED, ha="left", va="top", linespacing=1.6)
    _save(fig, "fig1_pareto_measured")


# ── Figure 2 — every distribution ─────────────────────────────────────────────────

def figure2(runs: list[C.Run]) -> None:
    conditions = sorted(C.by_condition(runs), key=lambda c: (family(c), c))
    fig, ax = plt.subplots(figsize=(10.0, 5.6), facecolor=SURFACE)
    rng = np.random.default_rng(S.BOOTSTRAP_SEED)
    for row, condition in enumerate(conditions):
        for arm, offset, alpha in (("warm", 0.13, 0.55), ("cold", -0.13, 0.95)):
            values = [r.wall_clock for r in runs
                      if r.condition_id == condition and r.cache_state == arm]
            if not values:
                continue
            jitter = rng.normal(0.0, 0.028, size=len(values))
            ax.plot(values, row + offset + jitter, linestyle="none", marker="o",
                    markersize=3.0 if arm == "warm" else 4.5,
                    color=SERIES[family(condition)], alpha=alpha,
                    markeredgecolor="none", zorder=2)
            ax.plot([np.median(values)], [row + offset], marker="|", markersize=14,
                    color=INK, markeredgewidth=1.4, linestyle="none", zorder=3)
    ax.set_yticks(range(len(conditions)))
    ax.set_yticklabels(conditions, fontsize=8)
    ax.set_xscale("log")
    ax.set_xlabel("wall clock, seconds (log) — one dot per run, tick at the median",
                  fontsize=9, color=INK)
    ax.set_ylim(-0.7, len(conditions) - 0.3)
    _style(ax)
    handles = [plt.Line2D([], [], marker="o", linestyle="none", markersize=4,
                          color=INK_MUTED, alpha=0.55, label="warm (upper row, 1,458 runs)"),
               plt.Line2D([], [], marker="o", linestyle="none", markersize=5.5,
                          color=INK_MUTED, label="cold (lower row, 122 runs)")]
    ax.legend(handles=handles, frameon=False, fontsize=8, loc="lower right",
              labelcolor=INK_MUTED)
    fig.suptitle("Figure 2 — the distributions the medians come from",
                 fontsize=12, color=INK, x=0.02, ha="left", y=1.02)
    fig.text(0.02, 0.975,
             "Unprivileged -T2 spans two orders of magnitude and its median describes "
             "nothing; the netsanity conditions span a few milliseconds. Colour is the "
             "tool family, not rank.",
             fontsize=7.5, color=INK_MUTED, ha="left", va="top")
    _save(fig, "fig2_distributions_measured")


# ── Figure 3 — recall by condition and cache arm ─────────────────────────────────

def figure3(runs: list[C.Run]) -> None:
    conditions = [c for c in C.DISCOVERY_CONDITIONS]
    fig, ax = plt.subplots(figsize=(10.0, 4.4), facecolor=SURFACE)
    width = 0.36
    for index, (arm, offset, alpha) in enumerate((("warm", -width / 2, 0.45),
                                                  ("cold", width / 2, 1.0))):
        for position, condition in enumerate(conditions):
            values = [r.recall for r in runs
                      if r.condition_id == condition and r.cache_state == arm]
            if not values:
                continue
            ax.bar(position + offset, np.median(values), width * 0.92,
                   color=SERIES[family(condition)], alpha=alpha,
                   edgecolor=SURFACE, linewidth=2.0, zorder=2)
            ax.annotate(f"{np.median(values):.2f}\nn={len(values)}",
                        (position + offset, np.median(values)),
                        textcoords="offset points",
                        xytext=(0, 26 if arm == "warm" else 3), ha="center",
                        fontsize=7, color=INK_MUTED, linespacing=1.15)
    ax.set_xticks(range(len(conditions)))
    ax.set_xticklabels([SHORT[c].replace("\n", " ") for c in conditions],
                       fontsize=7.5, rotation=20, ha="right")
    ax.set_ylabel("median recall", fontsize=9, color=INK)
    ax.set_ylim(0, 1.42)
    ax.set_yticks([0.0, 0.25, 0.5, 0.75, 1.0])
    _style(ax)
    handles = [plt.Line2D([], [], marker="s", linestyle="none", markersize=8,
                          color=INK_MUTED, alpha=0.45, label="warm cache"),
               plt.Line2D([], [], marker="s", linestyle="none", markersize=8,
                          color=INK_MUTED, label="cold cache")]
    ax.legend(handles=handles, frameon=False, fontsize=8, loc="upper left",
              labelcolor=INK_MUTED, ncols=2)
    fig.suptitle("Figure 3 — recall, warm against cold, with the cold arm's n on every bar",
                 fontsize=12, color=INK, x=0.02, ha="left", y=1.03)
    fig.text(0.02, 0.985,
             "The cold arm is small and unbalanced by design: one flush per block makes "
             "one run in thirteen cold, so n runs from 5 to 15 and no two conditions are "
             "ever cold in the same block.",
             fontsize=7.5, color=INK_MUTED, ha="left", va="top")
    _save(fig, "fig3_recall_by_cache_state")


# ── Figure 4 — the declaration budget, and what it costs ─────────────────────────

# A sequential ramp on one hue, because the three quantities in panel (b) are one
# pipeline read in order: what reached the wire, what the sweep attributed, what the
# artifact reported.  Categorical slots are reserved for the tool families in Figure 1
# and reusing them here would make colour mean two things in one paper.
PIPELINE = ["#b9d3f2", "#5f9ae0", "#1a5296"]
#: The testbed's five configured round-trip times, two responders at each.
TARGET_RTT_MS = [1.0, 5.0, 25.0, 100.0, 500.0]

BUDGET_ORDER = ["ns.fixed.timeout", "ns.disc.unpriv", "ns.naming.full", "ns.budget.shared"]


def figure4(runs: list[C.Run]) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(12.4, 5.0), facecolor=SURFACE,
                             gridspec_kw={"width_ratios": [1.15, 1.0]})

    # (a) how long the discovery stage ran, against the RTTs it had to cover.
    ax = axes[0]
    rows: list[tuple[float, str]] = []
    position = 0.0
    for condition in BUDGET_ORDER:
        for arm in ("warm", "cold"):
            subset = [r for r in runs if r.condition_id == condition
                      and r.cache_state == arm
                      and r.raw["parse"].get("discovery")]
            if not subset:
                continue
            elapsed = [r.raw["parse"]["discovery"]["elapsed_millis"] for r in subset]
            low, median, high = np.percentile(elapsed, [25, 50, 75])
            ax.barh(position, median, height=0.62,
                    color=SERIES["netsanity"], alpha=0.45 if arm == "warm" else 1.0,
                    edgecolor=SURFACE, linewidth=2.0, zorder=3)
            ax.plot([low, high], [position, position], color=INK, linewidth=1.2,
                    solid_capstyle="butt", zorder=4)
            ax.annotate(f"  {median:.0f} ms · recall "
                        f"{np.median([r.recall for r in subset]):.2f} · n={len(subset)}",
                        (median, position), va="center", fontsize=7.5, color=INK_MUTED,
                        zorder=5)
            rows.append((position, f"{SHORT[condition].replace(chr(10), ' ')}, {arm}"))
            position -= 1.0
        position -= 0.45

    for rtt in TARGET_RTT_MS:
        ax.axvline(rtt, color=GRID, linewidth=1.0, zorder=1)
        ax.annotate(f"{rtt:g} ms", (rtt, 1.85), rotation=90, fontsize=7,
                    color=INK_MUTED, ha="right", va="top", zorder=2)
    ax.axvline(500.0, color="#eb6834", linewidth=1.4, linestyle=(0, (4, 3)), zorder=2)
    ax.set_yticks([p for p, _ in rows])
    ax.set_yticklabels([t for _, t in rows], fontsize=8)
    ax.set_xscale("log")
    ax.set_xlim(0.7, 40000)
    ax.set_xticks([1, 10, 100, 1000])
    ax.set_ylim(min(p for p, _ in rows) - 0.8, 2.3)
    ax.set_xlabel("discovery stage, milliseconds (log) — parse.discovery.elapsed_millis",
                  fontsize=9, color=INK)
    _style(ax)
    ax.set_title("(a) the budget against the round-trip times it must cover",
                 fontsize=9.5, color=INK, loc="left", pad=8)

    # (b) wire, attributed, reported.
    ax = axes[1]
    labels: list[tuple[float, str]] = []
    group = 0.0
    for condition in ("ns.disc.unpriv", "ns.naming.full", "ns.budget.shared"):
        for arm in ("warm", "cold"):
            subset = [r for r in runs if r.condition_id == condition
                      and r.cache_state == arm and r.replies_seen is not None]
            if not subset:
                continue
            values = [
                np.median([r.raw["capture"]["wire"]["icmp_echo_replies"] for r in subset]),
                np.median([r.replies_seen for r in subset]),
                np.median([r.hosts_found for r in subset]),
            ]
            for index, (value, colour) in enumerate(zip(values, PIPELINE)):
                ax.bar(group + (index - 1) * 0.27, value, 0.25, color=colour,
                       edgecolor=SURFACE, linewidth=2.0, zorder=3)
                ax.annotate(f"{value:.0f}", (group + (index - 1) * 0.27, value),
                            textcoords="offset points", xytext=(0, 3), ha="center",
                            fontsize=7.5, color=INK_MUTED)
            labels.append((group, f"{arm}\nn={len(subset)}"))
            group += 1.0
        ax.annotate({"ns.disc.unpriv": "adaptive (split)",
                     "ns.naming.full": "full pipeline",
                     "ns.budget.shared": "shared budget"}[condition],
                    (group - 1.0, -2.55),
                    ha="center", fontsize=8, color=INK, annotation_clip=False)
        group += 0.55
    ax.set_xticks([p for p, _ in labels])
    ax.set_xticklabels([t for _, t in labels], fontsize=7.5, color=INK_MUTED)
    ax.set_ylabel("hosts or packets, median per run", fontsize=9, color=INK)
    ax.set_ylim(0, 16)
    _style(ax)
    handles = [plt.Line2D([], [], marker="s", linestyle="none", markersize=8,
                          color=PIPELINE[0], label="ICMP echo replies on the wire"),
               plt.Line2D([], [], marker="s", linestyle="none", markersize=8,
                          color=PIPELINE[1], label="replies the sweep attributed"),
               plt.Line2D([], [], marker="s", linestyle="none", markersize=8,
                          color=PIPELINE[2], label="hosts the artifact reported")]
    ax.legend(handles=handles, frameon=False, fontsize=7.5, loc="upper left",
              labelcolor=INK_MUTED)
    ax.set_title("(b) what reached the wire, what was attributed, what was reported",
                 fontsize=9.5, color=INK, loc="left", pad=8)

    fig.suptitle("Figure 4 — the declaration budget is shorter than the slowest host",
                 fontsize=12.5, color=INK, x=0.02, ha="left", y=1.02)
    fig.text(0.02, -0.055,
             "THEORY.md section 5 requires the declaration budget t to exceed the high "
             "quantile of the segment's round-trip times. The split budget declares at "
             "about 370 ms against a slowest responder at 500 ms.\n"
             "Cold, it reports 9 of 11 hosts. Warm, it reports 11 while attributing the "
             "same 8 replies — the two it did not hear come from the kernel neighbour "
             "table, which the block's flush empties. In ns.naming.full's 3.08 s cold "
             "runs the\nwire carries 13 echo replies and the artifact still reports 9: "
             "the late replies arrive inside the process and are not attributed. The "
             "shared budget declares at about 1 s and reports 11 in both arms.",
             fontsize=7.5, color=INK_MUTED, ha="left", va="top", linespacing=1.6)
    _save(fig, "fig4_declaration_budget")


# ── Figure 5 — the covariate that sets unprivileged nmap's clock ─────────────────

def figure5(runs: list[C.Run]) -> None:
    fig, ax = plt.subplots(figsize=(8.4, 4.6), facecolor=SURFACE)
    templates = {"nmap.sn.unpriv.T2": "o", "nmap.sn.unpriv.T3": "^",
                 "nmap.sn.unpriv.T4": "s", "nmap.sn.unpriv.T5": "D"}
    for condition, marker in templates.items():
        subset = [r for r in runs if r.condition_id == condition]
        ax.plot([r.arp_requests for r in subset], [r.wall_clock for r in subset],
                linestyle="none", marker=marker, markersize=4.5,
                color=SERIES["nmap, unprivileged"], alpha=0.75,
                markeredgecolor="none", label=f"{SHORT[condition]} (n={len(subset)})")
    ax.set_yscale("log")
    ax.set_xlabel("ARP requests emitted by the scanning host's kernel during the run",
                  fontsize=9, color=INK)
    ax.set_ylabel("wall clock, seconds (log)", fontsize=9, color=INK)
    _style(ax)
    ax.legend(frameon=False, fontsize=8, loc="upper left", labelcolor=INK_MUTED)
    fig.suptitle("Figure 5 — unprivileged nmap's wall clock is the scanning host's "
                 "ARP retry count", fontsize=12, color=INK, x=0.02, ha="left", y=1.03)
    fig.text(0.02, 0.985,
             "Both axes come from the record: capture.wire.arp_requests and the "
             "harness's monotonic clock. Rank correlation +0.97 on -T2. The kernel "
             "resolving 244 empty addresses is\na property of the measurement "
             "environment, not of nmap, and it is not what the warm/cold label records.",
             fontsize=7.5, color=INK_MUTED, ha="left", va="top", linespacing=1.5)
    _save(fig, "fig5_arp_versus_wall_clock")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--runs", type=Path, default=None)
    parser.add_argument("--sidecar", type=Path, default=None)
    args = parser.parse_args(argv)

    runs = C.admissible(C.load(args.runs, args.sidecar))
    print(f"figures from {len(runs)} admissible runs:")
    figure1(runs)
    figure2(runs)
    figure3(runs)
    figure4(runs)
    figure5(runs)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
