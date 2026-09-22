"""Look at every distribution before reporting a median.

A median over a bimodal sample is a number that describes nothing.  `PROTOCOL.md`
section 7 asks for medians and interquartile ranges and does not ask whether the
samples are unimodal, so this module answers that question first, and says what
separates the modes where they exist.

It **describes and does not adjudicate.**  Every automated verdict on multimodality
that this analysis tried first was worse than reading the histogram: a largest-gap rule
called the most obviously two-humped condition in the study unimodal, and a Gaussian
kernel at Silverman's bandwidth found five modes in a condition whose whole spread is
one second.  Picking whichever rule agreed with the plots would be choosing a statistic
after seeing which one flattered.  So what is computed here is a *profile* — quantiles,
dispersion, the density's peaks and the depth of the valleys between them, and the
covariates the wall clock tracks — and the shape is then stated in prose in
`RESULTS.md` against the figure, which is where a reader can check it.

`notable` is a reporting trigger and nothing else: it decides which conditions get a
paragraph, not what the paragraph says, and no hypothesis reads it.

Before anything in a mode is attributed to a *tool*, four fields decide whether it is
the apparatus: the harness's wall clock, the exit status, the parse status and the
tool's own self-reported duration.  A mode in which the tool exited non-zero, failed to
parse, or disagrees with the harness about how long it took is the apparatus.  A mode
in which all four agree, and which tracks a covariate of the *scanning host* rather
than of the tool, is the measurement environment: it belongs beside the number, not
inside it.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from scipy.stats import gaussian_kde

import collection as C
import stats as S

#: Covariates of the scanning Mac rather than of either tool.  `arp_requests` is how
#: many ARP requests the host's kernel emitted resolving the 244 empty addresses;
#: `FINDINGS-0.6-pilot.md` found it setting unprivileged `-T2`'s wall clock at r = 0.988
#: over eight runs and could not say what sets *it*.  It is on every record.
COVARIATES = {
    "arp_requests": lambda r: r.arp_requests,
    "tcp_rst": lambda r: r.tcp_rst,
    "tcp_synack": lambda r: r.tcp_synack,
    "sequence_index": lambda r: r.sequence_index,
    "recall": lambda r: r.recall,
}

#: A condition whose 90th percentile is at least twice its 10th gets prose and a
#: histogram in `RESULTS.md` instead of a bare median.  Stated here so that which
#: conditions got prose is a fact about the code rather than about the author's
#: attention.
NOTABLE_DISPERSION = 2.0


@dataclass
class Peak:
    location: float
    share: float
    valley_to_next: float | None


@dataclass
class Shape:
    condition: str
    arm: str
    n: int
    quantiles: S.Quantiles
    cv: float
    p10: float
    p90: float
    dispersion_ratio: float
    peaks: list[Peak]
    apparatus: dict
    correlations: dict[str, float] = field(default_factory=dict)

    @property
    def tail_ratio(self) -> float:
        """How far the worst run sits beyond the bulk.  A condition can be tight on
        p90/p10 and still have a tail that a median hides; both get reported."""
        return self.quantiles.maximum / self.p90 if self.p90 > 0 else float("inf")

    @property
    def notable(self) -> bool:
        return (self.dispersion_ratio >= NOTABLE_DISPERSION
                or self.tail_ratio >= NOTABLE_DISPERSION)

    @property
    def profile(self) -> str:
        peaks = ", ".join(
            f"{p.location:.3g} s ({p.share:.0%})"
            + (f" | valley {p.valley_to_next:.0%} of the lower peak" if p.valley_to_next is not None else "")
            for p in self.peaks)
        return (f"p10 {self.p10:.3g} s, p90 {self.p90:.3g} s, p90/p10 "
                f"{self.dispersion_ratio:.2f}x, max/p90 {self.tail_ratio:.2f}x, "
                f"CV {self.cv:.3f}; density peaks at {peaks}")


def _rank_correlation(x, y) -> float:
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    if x.size < 3 or x.std() == 0 or y.std() == 0:
        return float("nan")
    return float(np.corrcoef(np.argsort(np.argsort(x)), np.argsort(np.argsort(y)))[0, 1])


def density_peaks(values, *, floor: float = 0.10, grid_points: int = 2048) -> list[Peak]:
    """Peaks of a Gaussian kernel density on log10(wall clock), with valley depths.

    Log scale because the conditions span four orders of magnitude and a linear kernel
    would smooth a whole condition into one bin.  Silverman's bandwidth, because it is
    the default rule and choosing another after seeing the plots is exactly the move
    this analysis is not allowed to make.  Peaks below `floor` of the tallest are
    dropped as kernel ripple; what survives is reported with the fraction of the sample
    in its basin and the depth of the valley on its right, so a reader can see how
    separated the modes are instead of taking a mode count on trust.
    """
    x = np.log10(np.asarray(list(values), dtype=float))
    if x.size < 5 or x.std(ddof=1) == 0:
        return [Peak(float(10 ** np.median(x)), 1.0, None)]
    kde = gaussian_kde(x)  # Silverman is scipy's "silverman"; scott is the default
    kde.set_bandwidth("silverman")
    grid = np.linspace(x.min() - 0.5, x.max() + 0.5, grid_points)
    density = kde(grid)
    idx = [i for i in range(1, grid_points - 1)
           if density[i] > density[i - 1] and density[i] >= density[i + 1]]
    idx = [i for i in idx if density[i] >= floor * density.max()]
    if not idx:
        idx = [int(np.argmax(density))]
    peaks: list[Peak] = []
    for rank, i in enumerate(idx):
        if rank + 1 < len(idx):
            between = density[i:idx[rank + 1] + 1]
            valley = float(between.min() / min(density[i], density[idx[rank + 1]]))
            edge = grid[i + int(np.argmin(between))]
        else:
            valley, edge = None, grid[-1]
        low = grid[0] if rank == 0 else peaks[-1]._edge  # type: ignore[attr-defined]
        share = float(np.mean((x > low) & (x <= edge)))
        peak = Peak(float(10 ** grid[i]), share, valley)
        peak._edge = edge  # type: ignore[attr-defined]
        peaks.append(peak)
    return peaks


def apparatus_check(runs: list[C.Run]) -> dict:
    drift = [abs(r.wall_clock - r.self_reported) for r in runs if r.self_reported is not None]
    exits = sorted({r.exit_status for r in runs})
    parse_ok = sorted({r.parse_ok for r in runs})
    return {
        "exit_statuses": exits,
        "parse_ok": parse_ok,
        "parse_outcomes": sorted({r.parse_outcome for r in runs if r.parse_outcome}),
        "harness_minus_self_reported_median": float(np.median(drift)) if drift else None,
        "harness_minus_self_reported_max": float(max(drift)) if drift else None,
        "clean": exits == [0] and parse_ok == [True],
    }


def shape_of(runs: list[C.Run], condition: str, arm: str) -> Shape:
    rs = [r for r in runs if r.condition_id == condition]
    times = [r.wall_clock for r in rs]
    arr = np.asarray(times, dtype=float)
    p10, p90 = np.percentile(arr, [10, 90])
    return Shape(
        condition=condition, arm=arm, n=len(rs), quantiles=S.quantiles(times),
        cv=float(arr.std() / arr.mean()), p10=float(p10), p90=float(p90),
        dispersion_ratio=float(p90 / p10) if p10 > 0 else float("inf"),
        peaks=density_peaks(times), apparatus=apparatus_check(rs),
        correlations={name: _rank_correlation([getter(r) for r in rs], times)
                      for name, getter in COVARIATES.items()},
    )


def survey(runs: list[C.Run], arm: str, conditions=None) -> dict[str, Shape]:
    conditions = conditions or sorted(C.by_condition(runs))
    return {c: shape_of(runs, c, arm) for c in conditions
            if any(r.condition_id == c for r in runs)}


def render(survey_result: dict[str, Shape]) -> str:
    lines = []
    for condition, shape in survey_result.items():
        lines.append(f"{condition}  ({shape.arm}, n={shape.n})"
                     + ("   [notable: prose and a histogram]" if shape.notable else ""))
        lines.append(f"    {shape.quantiles}")
        lines.append(f"    {shape.profile}")
        ranked = sorted(shape.correlations.items(),
                        key=lambda kv: -abs(kv[1]) if kv[1] == kv[1] else 0)
        lines.append("    wall clock rank-correlates with: "
                     + ", ".join(f"{k} {v:+.3f}" for k, v in ranked if v == v))
        check = shape.apparatus
        lines.append(
            f"    apparatus: exits {check['exit_statuses']}, parse ok {check['parse_ok']}"
            + (f", |harness - self-reported| median "
               f"{check['harness_minus_self_reported_median']:.4f} s, max "
               f"{check['harness_minus_self_reported_max']:.4f} s"
               if check["harness_minus_self_reported_median"] is not None else "")
            + ("  — clean" if check["clean"] else "  — NOT clean"))
        lines.append("")
    return "\n".join(lines)
