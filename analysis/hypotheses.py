"""H1, H2, H5 and H6, each against the refutation condition frozen before collection.

The family is four.  `PROTOCOL.md`'s 2026-09-08 amendment grew it from four to five by
splitting H3; the 2026-09-12 amendment withdrew H3 entirely — netsanity has no
privileged engine — and returned it to four.  H4 is a reported capability comparison
and carries no test.  Every p-value here is Bonferroni-corrected against four.

The cache-state amendment of 2026-09-13 governs how each result is reported: the two
arms are two results and not a covariate to be adjusted away.  The warm arm meets
n >= 30 per stratum for every condition; the cold arm cannot be stratified at all and
is analysed pooled, at about nine runs per condition, and **every cold-arm number
carries its n beside it**.  That is the amendment's own wording and this module obeys
it by making `n` a required field of every cold result rather than a courtesy.

Nothing here moves a threshold, chooses a statistic after seeing which one flatters, or
reclassifies a run.  The two exclusions in the file are the two exclusions.
"""

from __future__ import annotations

import collections
from dataclasses import dataclass, field

import numpy as np

import collection as C
import stats as S

# The refutation conditions, verbatim from `PROTOCOL.md` section 1 as amended.  They
# are strings in the source so that the report cannot paraphrase them into something
# easier to meet.
REFUTATION = {
    "H1": "Refuted if any nmap timing template matches netsanity's recall at equal or "
          "lower median time.",
    "H2": "Refuted if the Pareto frontier of nmap's templates contains a point "
          "netsanity does not match or beat.",
    "H5": "Refuted if recall drops, or if the reduction is within run-to-run noise.",
    "H6": "Refuted if the median per-block recall of unprivileged `nmap -sn` — at its "
          "best timing template — is less than 0.25 below unprivileged netsanity's on "
          "the pre-declared testbed composition, or if the difference is not "
          "significant under McNemar after Bonferroni correction.",
}

CLAIM = {
    "H1": "For host discovery alone on a heterogeneous /24, netsanity's median "
          "time-to-complete is lower than `nmap -sn` at every timing template that "
          "achieves equal or better recall.",
    "H2": "Per-host adaptive retransmission timing dominates fixed timing templates on "
          "a network whose round-trip times span orders of magnitude: for any nmap "
          "template, there exists a netsanity configuration that is both faster and at "
          "least as complete.",
    "H5": "Separating the retransmission budget from the absence-declaration budget "
          "reduces total sweep time without reducing recall, relative to a single "
          "shared budget.",
    "H6": "On a local segment, losing root costs `nmap -sn` substantially more recall "
          "than it costs netsanity.",
}

#: H6's threshold, fixed by the 2026-09-08 amendment and derived there from the
#: pre-declared testbed composition.  It is not an input to anything else.
H6_MARGIN = 0.25

#: `THEORY.md` C5: a Pareto test with no region of interest rewards a configuration for
#: answering instantly by finding nothing.  The region is stated before the frontier,
#: never after.  It is a simulation correction rather than a protocol amendment, so the
#: pre-declared condition is evaluated without it and the restricted frontier is
#: reported beside it.
REGION_OF_INTEREST = 0.95


@dataclass
class Verdict:
    hypothesis: str
    arm: str
    refuted: bool
    condition_met: bool
    n_note: str
    summary: str
    detail: dict = field(default_factory=dict)

    @property
    def wording(self) -> str:
        return ("refutation condition MET — refuted" if self.condition_met
                else "refutation condition NOT met — not refuted")


def _median_recall(runs: list[C.Run]) -> float:
    return float(np.median([r.recall for r in runs]))


def _median_time(runs: list[C.Run]) -> float:
    return float(np.median([r.wall_clock for r in runs]))


def per_condition_summary(runs: list[C.Run], arm_name: str) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for condition, rs in sorted(C.by_condition(runs).items()):
        times = [r.wall_clock for r in rs]
        recalls = [r.recall for r in rs]
        out[condition] = {
            "n": len(rs),
            "arm": arm_name,
            "time": S.quantiles(times),
            "time_ci": S.bootstrap_ci(times),
            "recall_median": float(np.median(recalls)),
            "recall_mean": float(np.mean(recalls)),
            "recall_ci": S.bootstrap_ci(recalls, np.mean),
            "recall_values": dict(sorted(collections.Counter(round(x, 2) for x in recalls).items())),
            "precision_median": float(np.median([r.precision for r in rs])),
        }
    return out


# ── H1 ────────────────────────────────────────────────────────────────────────────

def h1(runs: list[C.Run], arm_name: str) -> Verdict:
    summary = per_condition_summary(runs, arm_name)
    ns = summary[C.H5_SPLIT]
    templates = {c: summary[c] for c in (C.NMAP_UNPRIV + C.NMAP_PRIV) if c in summary}

    offenders = []
    qualifying = []
    for name, stat in sorted(templates.items()):
        matches_recall = stat["recall_median"] >= ns["recall_median"]
        if matches_recall:
            qualifying.append(name)
            if stat["time"].median <= ns["time"].median:
                offenders.append(name)

    tests = {}
    for name in qualifying:
        a = [r.wall_clock for r in runs if r.condition_id == C.H5_SPLIT]
        b = [r.wall_clock for r in runs if r.condition_id == name]
        tests[name] = {
            "mann_whitney": S.mann_whitney(a, b),
            "median_difference_ci": S.bootstrap_difference(a, b),
        }

    condition_met = bool(offenders)
    return Verdict(
        hypothesis="H1", arm=arm_name, refuted=condition_met, condition_met=condition_met,
        n_note=f"netsanity n={ns['n']}; nmap templates n="
               f"{min(t['n'] for t in templates.values())}-{max(t['n'] for t in templates.values())}",
        summary=(
            f"netsanity (adaptive default) median {ns['time'].median:.3f} s at median "
            f"recall {ns['recall_median']:.2f}. "
            + (f"Templates matching that recall: {', '.join(qualifying)}; the fastest of "
               f"them is {min(qualifying, key=lambda c: templates[c]['time'].median)} at "
               f"{min(templates[c]['time'].median for c in qualifying):.3f} s."
               if qualifying else "No nmap template matches that recall.")
            + (f" Offending templates (equal or lower median time at matching recall): "
               f"{', '.join(offenders)}." if offenders else
               " No template matches that recall at equal or lower median time.")
        ),
        detail={"netsanity": ns, "templates": templates, "qualifying": qualifying,
                "offenders": offenders, "tests": tests},
    )


# ── H2 ────────────────────────────────────────────────────────────────────────────

def _frontier(points: dict[str, tuple[float, float]]) -> list[str]:
    """Non-dominated points, minimising time and maximising recall."""
    names = list(points)
    keep = []
    for name in names:
        t, r = points[name]
        dominated = any(
            (points[other][0] <= t and points[other][1] >= r)
            and (points[other][0] < t or points[other][1] > r)
            for other in names if other != name
        )
        if not dominated:
            keep.append(name)
    return sorted(keep, key=lambda n: points[n][0])


def h2(runs: list[C.Run], arm_name: str) -> Verdict:
    summary = per_condition_summary(runs, arm_name)
    points = {c: (summary[c]["time"].median, summary[c]["recall_median"])
              for c in C.DISCOVERY_CONDITIONS if c in summary}
    nmap_points = {c: v for c, v in points.items() if c.startswith("nmap")}
    ns_points = {c: v for c, v in points.items() if c.startswith("ns.")}

    nmap_frontier = _frontier(nmap_points)

    def unbeaten(candidates: dict[str, tuple[float, float]]) -> list[str]:
        """nmap frontier points for which no candidate is faster and at least as complete."""
        out = []
        for name in nmap_frontier:
            t, r = nmap_points[name]
            if not any(ct < t and cr >= r for ct, cr in candidates.values()):
                out.append(name)
        return out

    unbeaten_any = unbeaten(ns_points)
    unbeaten_default = unbeaten({C.H5_SPLIT: ns_points[C.H5_SPLIT]}) if C.H5_SPLIT in ns_points else []

    # The region-of-interest restatement THEORY C5 demands, reported beside the
    # pre-declared test and never in place of it.
    roi_nmap = {c: v for c, v in nmap_points.items() if v[1] >= REGION_OF_INTEREST}
    roi_ns = {c: v for c, v in ns_points.items() if v[1] >= REGION_OF_INTEREST}
    roi_frontier = _frontier(roi_nmap)
    roi_unbeaten = [n for n in roi_frontier
                    if not any(ct < roi_nmap[n][0] and cr >= roi_nmap[n][1]
                               for ct, cr in roi_ns.values())]

    # The 2026-09-13 cache-state amendment names a second, narrower clause for the cold
    # regime and commits the paper to the abstract if it fires: "If the cold arm shows
    # a privileged nmap point at recall 1.0 that netsanity does not match … H2 is
    # reported as refuted in the cold regime and the paper says so in the abstract."
    # It is evaluated here under both readings of "netsanity", because the two differ
    # on this data and the difference is the whole argument.
    priv_at_one = [c for c, (_, r) in nmap_points.items()
                   if c in C.NMAP_PRIV and r >= 1.0]
    default_recall = ns_points[C.H5_SPLIT][1] if C.H5_SPLIT in ns_points else None
    best_ns_recall = max((r for _, r in ns_points.values()), default=0.0)
    amendment_clause = {
        "privileged_nmap_points_at_recall_1": sorted(priv_at_one),
        "netsanity_default_median_recall": default_recall,
        "best_netsanity_median_recall": best_ns_recall,
        "fires_for_adaptive_default": bool(priv_at_one) and default_recall is not None
        and default_recall < 1.0,
        "fires_for_any_configuration": bool(priv_at_one) and best_ns_recall < 1.0,
    }

    condition_met = bool(unbeaten_any)
    ci = {c: {"time": summary[c]["time_ci"], "recall": summary[c]["recall_ci"]}
          for c in points}
    return Verdict(
        hypothesis="H2", arm=arm_name, refuted=condition_met, condition_met=condition_met,
        n_note="; ".join(f"{c} n={summary[c]['n']}" for c in sorted(points)),
        summary=(
            f"nmap's frontier: "
            + ", ".join(f"{n} ({nmap_points[n][0]:.3f} s, recall {nmap_points[n][1]:.2f})"
                        for n in nmap_frontier)
            + ". "
            + (f"Unmatched by any netsanity configuration: {', '.join(unbeaten_any)}."
               if unbeaten_any else
               "Every one of them is beaten by some netsanity configuration.")
            + (f" Unmatched by the adaptive default alone: {', '.join(unbeaten_default)}."
               if unbeaten_default else
               " The adaptive default alone beats every one of them.")
        ),
        detail={"points": points, "nmap_frontier": nmap_frontier,
                "unbeaten_by_any_netsanity": unbeaten_any,
                "unbeaten_by_default": unbeaten_default,
                "amendment_clause": amendment_clause,
                "region_of_interest": REGION_OF_INTEREST,
                "roi_nmap_frontier": roi_frontier, "roi_unbeaten": roi_unbeaten,
                "confidence_intervals": ci, "summary": summary},
    )


# ── H5 ────────────────────────────────────────────────────────────────────────────

def paired_recall(runs: list[C.Run], left: str, right: str) -> dict:
    """McNemar on paired per-host outcomes, or the reason it cannot be run.

    `PROTOCOL.md` section 7 pairs per-host outcomes **within a block**.  One flush per
    block makes exactly one run per block cold, so in the cold arm no two conditions
    are ever cold in the same block and the paired test has nothing to pair.  That is a
    property of the retained design, not of this data, and the 2026-09-13 amendment did
    not notice it.  Where the pairing does not exist the test is reported unrunnable
    rather than quietly replaced.
    """
    pairs = C.paired_by_block(runs, left, right)
    truth = sorted(C.truth_set(runs))
    if not pairs:
        return {
            "runnable": False,
            "pairs": 0,
            "reason": ("no block holds both conditions in this cache arm; with one "
                       "flush per block exactly one run per block is cold, so the "
                       "within-block pairing PROTOCOL.md section 7 specifies does not "
                       "exist in the cold arm for any pair of conditions"),
            "mcnemar": None,
            "paired_difference_ci": None,
        }
    outcomes = [(a.found_host(h), b.found_host(h)) for a, b in pairs for h in truth]
    return {
        "runnable": True,
        "pairs": len(pairs),
        "observations": len(outcomes),
        "reason": None,
        "mcnemar": S.mcnemar(outcomes),
        "paired_difference_ci": S.bootstrap_paired_difference(
            [(a.recall, b.recall) for a, b in pairs]),
    }


def h5(runs: list[C.Run], arm_name: str) -> Verdict:
    split = [r for r in runs if r.condition_id == C.H5_SPLIT]
    shared = [r for r in runs if r.condition_id == C.H5_SHARED]
    if not split or not shared:
        raise SystemExit(f"H5 has no data in the {arm_name} arm")

    time_test = S.mann_whitney([r.wall_clock for r in split], [r.wall_clock for r in shared])
    time_ci = S.bootstrap_difference([r.wall_clock for r in split],
                                     [r.wall_clock for r in shared])

    recall = paired_recall(runs, C.H5_SPLIT, C.H5_SHARED)
    split_recall = _median_recall(split)
    shared_recall = _median_recall(shared)
    #: The unpaired interval is the fallback where the design supplies no pairs.  It is
    #: disclosed as a departure everywhere it is used and never replaces the paired test
    #: in an arm that can run it.
    unpaired_ci = S.bootstrap_difference([r.recall for r in split],
                                         [r.recall for r in shared])

    # "Recall drops" is a statement about recall, read off the recall, in both arms.
    # Reading it off McNemar's discordant counts would silently score the cold arm as
    # "does not drop" on a test that never ran.
    recall_drops = split_recall < shared_recall
    reduction_is_noise = time_ci.low <= 0.0 <= time_ci.high
    condition_met = recall_drops or reduction_is_noise

    mc = recall["mcnemar"]
    return Verdict(
        hypothesis="H5", arm=arm_name, refuted=condition_met, condition_met=condition_met,
        n_note=(f"split n={len(split)}, shared n={len(shared)}, "
                + (f"{recall['pairs']} paired blocks, {recall['observations']} paired "
                   f"host observations" if recall["runnable"]
                   else "no within-block pairs exist in this arm")),
        summary=(
            f"split {S.quantiles([r.wall_clock for r in split])} vs shared "
            f"{S.quantiles([r.wall_clock for r in shared])}; median difference "
            f"{time_ci}. Recall: split {split_recall:.2f}, shared {shared_recall:.2f}, "
            f"unpaired median difference {unpaired_ci}. "
            + (f"McNemar {mc.only_a} host(s) found only by split against {mc.only_b} "
               f"only by shared, p={mc.p:.3g} ({mc.method}). "
               if recall["runnable"] else
               "McNemar as pre-declared is unrunnable here: " + recall["reason"] + ". ")
            + ("Recall drops. " if recall_drops else "Recall does not drop. ")
            + ("The time reduction is within run-to-run noise."
               if reduction_is_noise else "The time reduction is outside run-to-run noise.")
        ),
        detail={"time_test": time_test, "time_ci": time_ci, "recall": recall,
                "split_recall": split_recall, "shared_recall": shared_recall,
                "unpaired_recall_difference_ci": unpaired_ci,
                "recall_drops": recall_drops, "reduction_is_noise": reduction_is_noise,
                "split_quantiles": S.quantiles([r.wall_clock for r in split]),
                "shared_quantiles": S.quantiles([r.wall_clock for r in shared])},
    )


# ── H6 ────────────────────────────────────────────────────────────────────────────

def h6(runs: list[C.Run], arm_name: str) -> Verdict:
    ns = [r for r in runs if r.condition_id == C.H5_SPLIT]
    by_template = {c: [r for r in runs if r.condition_id == c] for c in C.NMAP_UNPRIV}
    by_template = {c: v for c, v in by_template.items() if v}
    medians = {c: _median_recall(v) for c, v in by_template.items()}
    best = max(medians, key=lambda c: (medians[c], -_median_time(by_template[c])))

    ns_recall = _median_recall(ns)
    gap = ns_recall - medians[best]

    recall = paired_recall(runs, C.H5_SPLIT, best)
    unpaired_ci = S.bootstrap_difference([r.recall for r in ns],
                                         [r.recall for r in by_template[best]])

    gap_too_small = gap < H6_MARGIN
    test = recall["mcnemar"]
    # The second disjunct needs McNemar.  Where the design supplies no pairs it cannot
    # be evaluated, and saying so is the only honest reading — not defaulting it to
    # "significant" (which would flatter H6) nor to "not significant" (which would
    # refute it on a test that never ran).
    not_significant = (not test.significant_bonferroni) if recall["runnable"] else None
    condition_met = gap_too_small or bool(not_significant)

    return Verdict(
        hypothesis="H6", arm=arm_name, refuted=condition_met, condition_met=condition_met,
        n_note=(f"netsanity n={len(ns)}, {best} n={len(by_template[best])}, "
                + (f"{recall['pairs']} paired blocks, {recall['observations']} paired "
                   f"host observations" if recall["runnable"]
                   else "no within-block pairs exist in this arm")),
        summary=(
            f"best unprivileged template by median per-block recall is {best} at "
            f"{medians[best]:.2f} (others: "
            + ", ".join(f"{c} {medians[c]:.2f}" for c in sorted(medians) if c != best)
            + f"). Unprivileged netsanity {ns_recall:.2f}. Gap {gap:+.2f} against the "
              f"pre-declared 0.25; unpaired median difference {unpaired_ci}. "
            + (f"McNemar {test.only_a} host(s) found only by netsanity against "
               f"{test.only_b} only by nmap, p={test.p:.3g} ({test.method}), Bonferroni "
               f"alpha {test.alpha_bonferroni:.4f}. " if recall["runnable"] else
               "McNemar as pre-declared is unrunnable here: " + recall["reason"] + ". ")
            + ("The gap is less than 0.25, so the refutation condition fires on its "
               "first disjunct alone. " if gap_too_small else "The gap reaches 0.25. ")
            + ("The second disjunct cannot be evaluated in this arm."
               if not_significant is None else
               ("The difference is not significant after correction."
                if not_significant else
                "The difference is significant after correction."))
        ),
        detail={"best_template": best, "template_median_recall": medians,
                "netsanity_recall": ns_recall, "gap": gap,
                "unpaired_recall_difference_ci": unpaired_ci, "recall": recall,
                "gap_too_small": gap_too_small,
                "not_significant": not_significant, "margin": H6_MARGIN},
    )


def all_hypotheses(runs: list[C.Run], arm_name: str) -> dict[str, Verdict]:
    return {"H1": h1(runs, arm_name), "H2": h2(runs, arm_name),
            "H5": h5(runs, arm_name), "H6": h6(runs, arm_name)}
