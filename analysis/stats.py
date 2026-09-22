"""The tests `PROTOCOL.md` section 7 names, and nothing else.

Mann-Whitney U two-sided at alpha = 0.05 with Cliff's delta, Bonferroni across the
hypothesis family, bootstrap confidence intervals at 10,000 resamples, and McNemar on
paired per-host outcomes.  A test that is not in the protocol does not get added here
without an amendment, and the amendments in `PROTOCOL.md` section 12 fix the family at
four: H1, H2, H5 and H6.

The bootstrap is seeded so that two runs of the analysis produce the same interval.
That is a reproducibility property, not a statistical one, and the seed is fixed here
rather than passed in so nobody can shop for one.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from scipy import stats as scipy_stats

#: `PROTOCOL.md` section 7.
ALPHA = 0.05
#: The 2026-09-12 amendment: H3 is withdrawn, the family returns to four.
FAMILY_SIZE = 4
FAMILY = ("H1", "H2", "H5", "H6")
BOOTSTRAP_RESAMPLES = 10_000
BOOTSTRAP_SEED = 20260922


def bonferroni_alpha(family_size: int = FAMILY_SIZE) -> float:
    return ALPHA / family_size


@dataclass
class Quantiles:
    n: int
    median: float
    q1: float
    q3: float
    iqr: float
    minimum: float
    maximum: float

    def __str__(self) -> str:
        return f"median {self.median:.3f} [IQR {self.q1:.3f}-{self.q3:.3f}] n={self.n}"


def quantiles(values) -> Quantiles:
    arr = np.asarray(list(values), dtype=float)
    if arr.size == 0:
        raise ValueError("no values")
    q1, med, q3 = np.percentile(arr, [25, 50, 75])
    return Quantiles(int(arr.size), float(med), float(q1), float(q3),
                     float(q3 - q1), float(arr.min()), float(arr.max()))


@dataclass
class MannWhitney:
    n_a: int
    n_b: int
    u: float
    p: float
    delta: float
    delta_label: str
    significant_uncorrected: bool
    significant_bonferroni: bool
    alpha_bonferroni: float


def cliffs_delta(a, b) -> tuple[float, str]:
    """(P(a > b) - P(a < b)), with Romano's thresholds for the label.

    Computed by ranking rather than by the O(nm) double loop, so that the 2,900-second
    conditions do not make the analysis slow enough that somebody skips running it.
    """
    a = np.asarray(list(a), dtype=float)
    b = np.asarray(list(b), dtype=float)
    n, m = a.size, b.size
    combined = np.concatenate([a, b])
    ranks = scipy_stats.rankdata(combined)
    rank_a = ranks[:n].sum()
    # U for a over b, from the rank sum; delta is U scaled onto [-1, 1].
    u_a = rank_a - n * (n + 1) / 2.0
    delta = (2.0 * u_a) / (n * m) - 1.0
    magnitude = abs(delta)
    if magnitude < 0.147:
        label = "negligible"
    elif magnitude < 0.33:
        label = "small"
    elif magnitude < 0.474:
        label = "medium"
    else:
        label = "large"
    return float(delta), label


def mann_whitney(a, b, *, family_size: int = FAMILY_SIZE) -> MannWhitney:
    a = np.asarray(list(a), dtype=float)
    b = np.asarray(list(b), dtype=float)
    result = scipy_stats.mannwhitneyu(a, b, alternative="two-sided")
    delta, label = cliffs_delta(a, b)
    corrected = bonferroni_alpha(family_size)
    return MannWhitney(
        n_a=int(a.size), n_b=int(b.size), u=float(result.statistic), p=float(result.pvalue),
        delta=delta, delta_label=label,
        significant_uncorrected=bool(result.pvalue < ALPHA),
        significant_bonferroni=bool(result.pvalue < corrected),
        alpha_bonferroni=corrected,
    )


@dataclass
class Interval:
    point: float
    low: float
    high: float
    n: int
    resamples: int = BOOTSTRAP_RESAMPLES

    def __str__(self) -> str:
        return f"{self.point:.4f} [{self.low:.4f}, {self.high:.4f}] (n={self.n})"


def bootstrap_ci(values, statistic=np.median, *, resamples: int = BOOTSTRAP_RESAMPLES,
                 seed: int = BOOTSTRAP_SEED) -> Interval:
    arr = np.asarray(list(values), dtype=float)
    if arr.size == 0:
        raise ValueError("no values")
    rng = np.random.default_rng(seed)
    draws = rng.integers(0, arr.size, size=(resamples, arr.size))
    stats_ = statistic(arr[draws], axis=1)
    low, high = np.percentile(stats_, [2.5, 97.5])
    return Interval(float(statistic(arr)), float(low), float(high), int(arr.size), resamples)


def bootstrap_difference(a, b, statistic=np.median, *,
                         resamples: int = BOOTSTRAP_RESAMPLES,
                         seed: int = BOOTSTRAP_SEED) -> Interval:
    """A 95% interval on statistic(a) - statistic(b), resampled independently."""
    a = np.asarray(list(a), dtype=float)
    b = np.asarray(list(b), dtype=float)
    rng = np.random.default_rng(seed)
    da = a[rng.integers(0, a.size, size=(resamples, a.size))]
    db = b[rng.integers(0, b.size, size=(resamples, b.size))]
    diff = statistic(da, axis=1) - statistic(db, axis=1)
    low, high = np.percentile(diff, [2.5, 97.5])
    return Interval(float(statistic(a) - statistic(b)), float(low), float(high),
                    int(min(a.size, b.size)), resamples)


def bootstrap_paired_difference(pairs, *, resamples: int = BOOTSTRAP_RESAMPLES,
                                seed: int = BOOTSTRAP_SEED) -> Interval:
    """A 95% interval on the median paired difference, resampling whole pairs.

    H6's refutation condition is a margin between two recalls observed on the same
    blocks, so the pair is the unit that gets resampled; resampling the two sides
    independently would throw away the pairing the design paid for.
    """
    arr = np.asarray([left - right for left, right in pairs], dtype=float)
    rng = np.random.default_rng(seed)
    draws = arr[rng.integers(0, arr.size, size=(resamples, arr.size))]
    medians = np.median(draws, axis=1)
    low, high = np.percentile(medians, [2.5, 97.5])
    return Interval(float(np.median(arr)), float(low), float(high), int(arr.size), resamples)


@dataclass
class McNemar:
    """Paired per-host outcomes: b is 'a found it, b did not', c is the reverse."""
    both: int
    only_a: int
    only_b: int
    neither: int
    p: float
    statistic: float
    method: str
    significant_uncorrected: bool
    significant_bonferroni: bool
    alpha_bonferroni: float
    pairs: int = 0
    note: str = field(default="")

    @property
    def discordant(self) -> int:
        return self.only_a + self.only_b


def mcnemar(outcomes, *, family_size: int = FAMILY_SIZE) -> McNemar:
    """`outcomes` is an iterable of (found_by_a, found_by_b) booleans, one per host
    observation — that is, per (block, declared responder) pair.

    The exact binomial form is used whenever the discordant count is small, because the
    chi-square approximation is not trustworthy there and the study's discordant counts
    are sometimes zero.  Which form ran is reported beside the p-value rather than
    chosen silently.
    """
    both = only_a = only_b = neither = 0
    for found_a, found_b in outcomes:
        if found_a and found_b:
            both += 1
        elif found_a and not found_b:
            only_a += 1
        elif found_b and not found_a:
            only_b += 1
        else:
            neither += 1
    discordant = only_a + only_b
    if discordant == 0:
        p, statistic, method = 1.0, 0.0, "exact binomial (no discordant pairs)"
        note = ("every paired observation agrees; the test has no evidence either way "
                "and a p of 1 here means 'nothing to separate', not 'the same'")
    elif discordant < 25:
        p = float(scipy_stats.binomtest(only_a, discordant, 0.5).pvalue)
        statistic = float(min(only_a, only_b))
        method = "exact binomial"
        note = ""
    else:
        statistic = (abs(only_a - only_b) - 1) ** 2 / discordant
        p = float(scipy_stats.chi2.sf(statistic, 1))
        method = "chi-square with continuity correction"
        note = ""
    corrected = bonferroni_alpha(family_size)
    return McNemar(both=both, only_a=only_a, only_b=only_b, neither=neither,
                   p=p, statistic=float(statistic), method=method,
                   significant_uncorrected=bool(p < ALPHA),
                   significant_bonferroni=bool(p < corrected),
                   alpha_bonferroni=corrected, note=note)


def gap_split(values, *, min_group: int = 5, gap_ratio: float = 6.0,
              depth: int = 2) -> list[list[float]]:
    """Split a sample where its order statistics leave an unusually large hole.

    `PROTOCOL.md` names no unimodality test, so this is **exploratory** and is labelled
    as one everywhere it appears: it decides nothing, fixes no threshold and enters no
    refutation condition.  It exists because a median over a bimodal sample is a number
    that describes nothing, and the analysis has to be able to say *which* conditions
    are in that state without a person eyeballing thirteen histograms and choosing.

    The rule is deliberately crude and completely transparent: sort, take the largest
    gap between neighbouring observations, and call it a split if it is more than
    `gap_ratio` times the median gap and leaves at least `min_group` observations on
    each side.  Recurse at most `depth` times.  A rule with one arithmetic step is a
    rule a reviewer can check by reading it; a mixture model fitted here would be a
    second set of assumptions arriving after the data.
    """
    arr = np.sort(np.asarray(list(values), dtype=float))
    if depth <= 0 or arr.size < 2 * min_group:
        return [arr.tolist()]
    gaps = np.diff(arr)
    if gaps.size == 0:
        return [arr.tolist()]
    median_gap = float(np.median(gaps))
    index = int(np.argmax(gaps))
    if median_gap <= 0 or gaps[index] <= gap_ratio * median_gap:
        return [arr.tolist()]
    if index + 1 < min_group or arr.size - (index + 1) < min_group:
        return [arr.tolist()]
    left = gap_split(arr[:index + 1], min_group=min_group, gap_ratio=gap_ratio,
                     depth=depth - 1)
    right = gap_split(arr[index + 1:], min_group=min_group, gap_ratio=gap_ratio,
                      depth=depth - 1)
    return left + right
