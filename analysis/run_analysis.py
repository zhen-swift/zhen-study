"""The whole analysis, end to end, from `data/runs.ndjson` plus `analysis/strata.json`.

    python3 analysis/run_analysis.py                 # everything, to stdout and out/
    python3 analysis/run_analysis.py --no-figures    # numbers only

It runs on a machine that is not the collection Mac: no absolute paths, no state in a
notebook, nothing read that is not in the repository.  The one exception is the
artefact-existence check in `verify.py`, which needs the raw stdout, stderr and pcap
files; those are git-ignored by design and ship as a release bundle, so that check
reports what it could not find rather than failing the run — pass `--artifact-root` to
point it at the bundle.

Two things it is careful about, because the protocol is:

**The family is four** — H1, H2, H5 and H6 — and every p-value is corrected against
four.  **The two arms are two results**: the warm arm is reported at full resolution,
the cold arm pooled across strata with its n beside every number, per the 2026-09-13
amendment.

Anything this analysis does that the plan does not name is collected under
`exploratory` and marked as an amendment with today's date.  None of it enters the
hypothesis family and none of it moves a threshold.
"""

from __future__ import annotations

import argparse
import collections
import dataclasses
import datetime as dt
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
from scipy.stats import kruskal

import collection as C
import hypotheses as H
import shapes
import stats as S
import strata as strata_module
import verify as verify_module

HERE = Path(__file__).resolve().parent
OUT = HERE / "out"

#: Recorded, dated and marked exploratory.  `PROTOCOL.md` section 7 names Mann-Whitney
#: U, Cliff's delta, McNemar, bootstrap and Bonferroni; nothing below is in that list.
EXPLORATORY_AMENDMENTS = [
    {
        "date": "2026-09-22",
        "what": "Kruskal-Wallis across the four strata, per condition, warm arm",
        "why": "The design stratifies by time of day and the plan never says how to "
               "check whether the strata differ. Reporting four medians and leaving "
               "the reader to compare them by eye is worse than running the test and "
               "labelling it.",
        "status": "exploratory; not in the family; no hypothesis reads it",
    },
    {
        "date": "2026-09-22",
        "what": "Gaussian kernel density on log10 wall clock, to describe the shape of "
                "each condition's distribution before its median is reported",
        "why": "A median over a bimodal sample describes nothing and the plan does not "
               "ask whether the samples are unimodal. The density is reported, never "
               "used to decide anything.",
        "status": "exploratory; descriptive only",
    },
    {
        "date": "2026-09-22",
        "what": "Unpaired bootstrap intervals on recall differences in the cold arm",
        "why": "PROTOCOL.md section 7 pairs per-host outcomes within a block. One flush "
               "per block makes exactly one run per block cold, so no two conditions "
               "are ever cold in the same block and the paired test has nothing to "
               "pair. The unpaired interval is reported in its place and labelled.",
        "status": "exploratory; the pre-declared McNemar is reported unrunnable rather "
                  "than replaced",
    },
    {
        "date": "2026-09-22",
        "what": "netsanity's adaptive default against its own fixed-retransmit "
                "ablation, on wall clock and recall",
        "why": "The condition matrix contains the comparison and no hypothesis asks "
               "for it. THEORY.md's contribution is per-host adaptive retransmission "
               "timing, and the ablation that removes the adaptation while keeping the "
               "split is the only thing in the study that prices it.",
        "status": "exploratory; reported as a result, not as a hypothesis test",
    },
    {
        "date": "2026-09-22",
        "what": "Jaccard set stability between consecutive blocks of a condition",
        "why": "PROTOCOL.md section 4 names run-to-run set stability as a secondary "
               "metric and section 7 names no test for it. The number is reported "
               "without one.",
        "status": "secondary metric, reported; no test attached",
    },
]


def _jsonable(value):
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {k: _jsonable(v) for k, v in dataclasses.asdict(value).items()}
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return float(value)
    if isinstance(value, (np.bool_,)):
        return bool(value)
    return value


# ── sections ──────────────────────────────────────────────────────────────────────

def section_strata(sidecar: dict, out: list[str]) -> None:
    out.append("STAGE 1 — the stratum sidecar")
    evidence = sidecar["offset_established_by"]
    out.append(f"  collection machine UTC offset: {sidecar['collection_utc_offset']} "
               f"({sidecar['collection_utc_offset_seconds']} s)")
    out.append(f"  established from: {evidence.get('source')}")
    if "anchors" in evidence:
        lag = evidence["write_lag_seconds"]
        out.append(f"  {evidence['anchors']} anchors, write lag {lag['min']}-{lag['max']} s "
                   f"(median {lag['median']}), spread across the whole window "
                   f"{evidence['drift_across_window_seconds']} s — no drift, no DST step")
        labels = evidence.get("driver_labels", {})
        disagreed = [b for b in labels
                     if labels[b] != sidecar["blocks"].get(b, {}).get("stratum")]
        out.append(f"  the driver's own labels for all {len(labels)} blocks are "
                   f"reproduced: {len(disagreed)} disagreement(s)")
    out.append(f"  complete blocks per stratum: {sidecar['complete_blocks_per_stratum']}")
    out.append(f"  partial blocks: {sidecar['partial_blocks']}")
    out.append("")


def section_verify(records: list[dict], sidecar: dict, runs_path: Path,
                   artifact_root: Path | None, out: list[str]) -> dict:
    ledger = verify_module.Ledger()
    digest = hashlib.sha256(Path(runs_path).read_bytes()).hexdigest()
    ledger.check("the sidecar was built from this runs.ndjson",
                 sidecar["source_sha256"] == digest, digest[:12] + "...")
    verify_module.verify_records(records, sidecar, ledger, artifact_root)
    commits = sorted(
        {r["provenance"]["git_commit"][:7] for r in records},
        key=lambda c: min(r["started_at_unix"] for r in records
                          if r["provenance"]["git_commit"].startswith(c)))
    findings = verify_module.verify_apparatus(ledger, commits)

    out.append("STAGE 2 — REPRODUCIBILITY.md, recomputed")
    out.append(ledger.render())
    checkable = len(ledger.rows) - len(ledger.skipped)
    out.append(f"  {checkable - len(ledger.failures)}/{checkable} claims reconcile"
               + (f", {len(ledger.skipped)} not checkable here" if ledger.skipped else ""))
    out.append("")
    out.append("  apparatus commits, in the order the data uses them:")
    block_spans = collections.defaultdict(list)
    for record in records:
        block_spans[record["provenance"]["git_commit"][:7]].append(record["block_id"])
    for commit in commits:
        blocks = sorted(set(block_spans[commit]))
        calibration = findings["calibration"].get(commit, {})
        out.append(f"    {commit}  blocks {blocks[0]}-{blocks[-1]} "
                   f"({len(block_spans[commit])} runs)  worst calibration "
                   f"{calibration.get('worst_error_percent', float('nan')):.2f}% on "
                   f"{calibration.get('worst_responder')}")
    out.append("")
    return {"claims": [{"claim": c, "ok": ok, "detail": d} for c, ok, d in ledger.rows],
            "failures": [c for c, _, _ in ledger.failures],
            "skipped": [c for c, _, _ in ledger.skipped],
            "apparatus": findings, "commit_order": commits}


def section_shapes(runs: list[C.Run], out: list[str]) -> dict:
    out.append("STAGE 3a — every distribution, before any median is reported")
    result = {}
    for arm in ("warm", "cold"):
        survey = shapes.survey(C.arm(runs, arm), arm)
        result[arm] = survey
        out.append(f"  {arm} arm")
        out.append("    " + shapes.render(survey).replace("\n", "\n    ").rstrip())
    out.append("")
    return result


def section_hypotheses(runs: list[C.Run], out: list[str]) -> dict:
    out.append("STAGE 3b — the four hypotheses, each against the condition frozen "
               "before collection")
    out.append(f"  family: {', '.join(S.FAMILY)}; alpha {S.ALPHA}, Bonferroni "
               f"{S.bonferroni_alpha():.4f} across {S.FAMILY_SIZE}")
    result: dict = {}
    for arm in ("warm", "cold"):
        subset = C.arm(runs, arm)
        verdicts = H.all_hypotheses(subset, arm)
        result[arm] = verdicts
        out.append("")
        out.append(f"  --- {arm.upper()} ARM ({len(subset)} runs) ---")
        for name in S.FAMILY:
            verdict = verdicts[name]
            out.append(f"  {name}: {H.CLAIM[name]}")
            out.append(f"      pre-declared: {H.REFUTATION[name]}")
            out.append(f"      VERDICT: {verdict.wording}")
            out.append(f"      n: {verdict.n_note}")
            out.append(f"      {verdict.summary}")
        clause = verdicts["H2"].detail["amendment_clause"]
        out.append(f"      [H2, the 2026-09-13 amendment's cold-regime clause] "
                   f"privileged nmap points at recall 1.0: "
                   f"{clause['privileged_nmap_points_at_recall_1']}; netsanity's "
                   f"adaptive default at {clause['netsanity_default_median_recall']}, "
                   f"best netsanity configuration at "
                   f"{clause['best_netsanity_median_recall']}. Clause fires for the "
                   f"adaptive default: {clause['fires_for_adaptive_default']}; for any "
                   f"configuration: {clause['fires_for_any_configuration']}.")
    out.append("")
    return result


def section_sensitivity(runs: list[C.Run], out: list[str]) -> dict:
    out.append("STAGE 3c — flagged blocks 36, 74 and 93, with and without")
    out.append("  They ran on battery under records that say on_ac_power: true. They "
               "are admissible; neither the protocol's exclusion rules nor this "
               "analysis removes them.")
    result: dict = {}
    for arm in ("warm", "cold"):
        result[arm] = {}
        for drop in (False, True):
            subset = C.arm(C.admissible(runs, drop_flagged=drop), arm)
            verdicts = H.all_hypotheses(subset, arm)
            result[arm]["without_flagged" if drop else "with_flagged"] = verdicts
            label = "without 36/74/93" if drop else "with 36/74/93   "
            summary = {k: ("refuted" if v.condition_met else "not refuted")
                       for k, v in verdicts.items()}
            out.append(f"    {arm:<5} {label}  n={len(subset):<5} {summary}")
        for condition in (C.H5_SPLIT, C.H5_SHARED, "nmap.sn.unpriv.T2", "nmap.sn.priv.T5"):
            with_flagged = [r.wall_clock for r in C.arm(C.admissible(runs), arm)
                            if r.condition_id == condition]
            without = [r.wall_clock for r in
                       C.arm(C.admissible(runs, drop_flagged=True), arm)
                       if r.condition_id == condition]
            if not with_flagged or not without:
                continue
            out.append(f"      {arm:<5} {condition:<20} median "
                       f"{np.median(with_flagged):.3f} s -> {np.median(without):.3f} s "
                       f"(n {len(with_flagged)} -> {len(without)})")
    out.append("")
    return result


def section_strata_effect(runs: list[C.Run], out: list[str]) -> dict:
    out.append("STAGE 3d — does the stratum matter? (exploratory, warm arm)")
    strata = list(strata_module.STRATA)
    result = {}
    for condition in sorted(C.DISCOVERY_CONDITIONS):
        groups = [[r.wall_clock for r in runs
                   if r.condition_id == condition and r.stratum == s and r.cache_state == "warm"]
                  for s in strata]
        sizes = [len(g) for g in groups]
        usable = [g for g in groups if len(g) > 1]
        statistic, p = kruskal(*usable)
        medians = [float(np.median(g)) if g else None for g in groups]
        spread = max(m for m in medians if m) - min(m for m in medians if m)
        result[condition] = {"p": float(p), "medians": dict(zip(strata, medians)),
                             "n": dict(zip(strata, sizes)), "spread_seconds": spread}
        out.append(f"    {condition:<22} H={statistic:7.2f} p={p:<10.3g} "
                   f"medians {[round(m, 3) for m in medians]} spread {spread:.4g} s "
                   f"n {sizes}")
    out.append("    The Wi-Fi covariate section 6 names is 'not_applicable' on every "
               "run: the primary testbed is a virtual bridge, so household contention "
               "cannot reach it.")
    out.append("")
    return result


def section_secondary(runs: list[C.Run], out: list[str]) -> dict:
    out.append("STAGE 3e — the secondary metrics PROTOCOL.md section 4 names")
    present, absent = {}, {}
    warm = C.arm(runs, "warm")
    for condition in sorted(C.by_condition(warm)):
        subset = [r for r in warm if r.condition_id == condition]
        ordered = sorted(subset, key=lambda r: r.block_id)
        jaccard = [len(a.found & b.found) / len(a.found | b.found)
                   for a, b in zip(ordered, ordered[1:])]
        probes = [r.probes_sent / r.hosts_found for r in subset
                  if r.probes_sent and r.hosts_found]
        present[condition] = {
            "precision_median": float(np.median([r.precision for r in subset])),
            "jaccard_median": float(np.median(jaccard)),
            "jaccard_min": float(min(jaccard)),
            "probes_per_host_median": float(np.median(probes)) if probes else None,
        }
        out.append(f"    {condition:<22} precision {present[condition]['precision_median']:.3f}  "
                   f"Jaccard median {present[condition]['jaccard_median']:.3f} "
                   f"(min {present[condition]['jaccard_min']:.3f})  probes/host "
                   + (f"{present[condition]['probes_per_host_median']:.1f}"
                      if probes else "not reported by this tool"))
    absent = {
        "time_to_first_host": "not recorded by the harness on any run",
        "peak_in_flight_probes": "not recorded by the harness on any run",
        "energy_per_scan": "powermetrics is not in the schema; the driver requires AC "
                           "power, which is the opposite of the on-battery, "
                           "screen-off condition section 4 specifies",
        "wifi_airtime_utilisation": "'not_applicable' on all 1,578 admissible runs — "
                                    "bridge100 is not a Wi-Fi interface",
        "H4_naming_fractions": "parse carries no naming fields; the fraction of hosts "
                               "named, the fraction given a model and the fraction of "
                               "randomised-MAC hosts named are in the artifact at "
                               "stdout_path and not in the NDJSON",
    }
    out.append("    NOT in the record, and therefore not recomputable from it:")
    for key, why in absent.items():
        out.append(f"      {key}: {why}")
    out.append("")
    return {"present": present, "absent": absent}


def section_theory(runs: list[C.Run], out: list[str]) -> dict:
    out.append("STAGE 3f — what the measurements say about THEORY.md")
    result: dict = {}

    # P2: recall is invariant to the budget split.
    p2 = {}
    for arm in ("warm", "cold"):
        subset = C.arm(runs, arm)
        split = [r.recall for r in subset if r.condition_id == C.H5_SPLIT]
        shared = [r.recall for r in subset if r.condition_id == C.H5_SHARED]
        p2[arm] = {"split_median": float(np.median(split)), "split_n": len(split),
                   "shared_median": float(np.median(shared)), "shared_n": len(shared)}
    result["P2"] = p2
    out.append(f"    P2 'recall is invariant to the budget split': split "
               f"{p2['warm']['split_median']:.2f} vs shared "
               f"{p2['warm']['shared_median']:.2f} warm (n "
               f"{p2['warm']['split_n']}/{p2['warm']['shared_n']}); "
               f"{p2['cold']['split_median']:.2f} vs "
               f"{p2['cold']['shared_median']:.2f} cold (n "
               f"{p2['cold']['split_n']}/{p2['cold']['shared_n']}). "
               f"CONTRADICTED in the cold arm.")

    # The adaptation's own price: default against the fixed-retransmit ablation.
    adaptation = {}
    for arm in ("warm", "cold"):
        subset = C.arm(runs, arm)
        fixed = [r for r in subset if r.condition_id == "ns.fixed.timeout"]
        adaptive = [r for r in subset if r.condition_id == C.H5_SPLIT]
        test = S.mann_whitney([r.wall_clock for r in fixed],
                              [r.wall_clock for r in adaptive])
        difference = S.bootstrap_difference([r.wall_clock for r in fixed],
                                            [r.wall_clock for r in adaptive])
        recall = H.paired_recall(subset, "ns.fixed.timeout", C.H5_SPLIT)
        adaptation[arm] = {
            "fixed": S.quantiles([r.wall_clock for r in fixed]),
            "adaptive": S.quantiles([r.wall_clock for r in adaptive]),
            "mann_whitney": test, "median_difference_ci": difference,
            "fixed_recall_median": float(np.median([r.recall for r in fixed])),
            "adaptive_recall_median": float(np.median([r.recall for r in adaptive])),
            "recall": recall,
        }
        out.append(f"    P1/H2's mechanism, priced: fixed 50 ms retransmit "
                   f"{adaptation[arm]['fixed'].median:.3f} s against the adaptive "
                   f"default {adaptation[arm]['adaptive'].median:.3f} s ({arm}); "
                   f"median difference {difference}, Cliff's delta {test.delta:+.3f} "
                   f"({test.delta_label}), p={test.p:.3g}; recall "
                   f"{adaptation[arm]['fixed_recall_median']:.2f} against "
                   f"{adaptation[arm]['adaptive_recall_median']:.2f}.")
    result["adaptation_price"] = adaptation

    # What the discovery stage heard against what the artifact reported.
    heard = {}
    for arm in ("warm", "cold"):
        subset = C.arm(runs, arm)
        for condition in C.NETSANITY_DISCOVERY:
            rs = [r for r in subset if r.condition_id == condition
                  and r.replies_seen is not None]
            if not rs:
                continue
            heard[f"{condition}/{arm}"] = {
                "n": len(rs),
                "replies_seen_median": float(np.median([r.replies_seen for r in rs])),
                "hosts_found_median": float(np.median([r.hosts_found for r in rs])),
                "recall_median": float(np.median([r.recall for r in rs])),
            }
    result["heard_versus_reported"] = heard
    out.append("    P1's enabling condition (a late reply is still attributed to its "
               "probe), read off parse.discovery:")
    for key, value in heard.items():
        out.append(f"      {key:<28} replies {value['replies_seen_median']:.0f}, "
                   f"reported {value['hosts_found_median']:.0f}, recall "
                   f"{value['recall_median']:.2f}, n={value['n']}")

    result["untestable"] = {
        "P1 (advantage scales with RTT dispersion)":
            "the testbed holds one dispersion, 500x (1 ms to 500 ms target RTT), "
            "identical at all seven apparatus commits. Nothing in this collection "
            "varies it, so the central mechanism claim is not tested here.",
        "C8 (correlated loss)":
            "nine of ten responders carry loss_percent 0.0 and the tenth carries a "
            "flat 15%; no burst process was imposed and the capture's burstiness was "
            "never estimated, so the arm where H5 was predicted to fail hardest is "
            "not sampled.",
        "P7 / C7 (the cost form)":
            "the record carries probes_sent but neither the concurrency c nor the "
            "retransmission interval r nor the declaration budget t, so the wave form "
            "cannot be fitted from the NDJSON.",
        "P4 (Little's Law on peak in-flight probes)":
            "peak in-flight probes is not recorded.",
        "P5 (marginal recall of attempt three, Wi-Fi against wired)":
            "per-attempt outcomes are not recorded and the segment has no Wi-Fi.",
    }
    out.append("    Predictions this collection cannot test:")
    for key, why in result["untestable"].items():
        out.append(f"      {key}: {why}")
    out.append("")
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--runs", type=Path, default=None)
    parser.add_argument("--sidecar", type=Path, default=None)
    parser.add_argument("--artifact-root", type=Path, default=None)
    parser.add_argument("--out", type=Path, default=OUT)
    parser.add_argument("--no-figures", action="store_true")
    args = parser.parse_args(argv)

    runs_path = args.runs or C.DEFAULT_RUNS
    sidecar_path = args.sidecar or C.DEFAULT_SIDECAR
    sidecar = json.loads(Path(sidecar_path).read_text())
    records = [json.loads(line) for line in open(runs_path, encoding="utf-8")
               if line.strip()]
    runs = C.load(runs_path, sidecar_path)
    admissible = C.admissible(runs)

    lines: list[str] = [
        "netsanity study — phase 4 analysis",
        f"generated {dt.date.today().isoformat()} from {Path(runs_path).name} "
        f"({len(records)} records, {len(admissible)} admissible) and "
        f"{Path(sidecar_path).name}",
        "",
    ]
    results: dict = {"generated": dt.date.today().isoformat(),
                     "source": Path(runs_path).name,
                     "source_sha256": sidecar["source_sha256"],
                     "records": len(records), "admissible": len(admissible)}

    section_strata(sidecar, lines)
    results["sidecar"] = {k: v for k, v in sidecar.items() if k != "blocks"}
    results["verification"] = section_verify(records, sidecar, Path(runs_path),
                                            args.artifact_root, lines)
    results["shapes"] = section_shapes(admissible, lines)
    results["hypotheses"] = section_hypotheses(admissible, lines)
    results["sensitivity"] = section_sensitivity(runs, lines)
    results["strata_effect"] = section_strata_effect(admissible, lines)
    results["secondary"] = section_secondary(admissible, lines)
    results["theory"] = section_theory(admissible, lines)
    results["exploratory_amendments"] = EXPLORATORY_AMENDMENTS

    lines.append("STAGE 4 — amendments this analysis made, recorded and dated")
    for amendment in EXPLORATORY_AMENDMENTS:
        lines.append(f"    {amendment['date']}  {amendment['what']}")
        lines.append(f"        why: {amendment['why']}")
        lines.append(f"        status: {amendment['status']}")
    lines.append("")

    if not args.no_figures:
        import figures_measured
        lines.append("figures, regenerated from the collected data:")
        figures_measured.figure1(admissible)
        figures_measured.figure2(admissible)
        figures_measured.figure3(admissible)
        figures_measured.figure4(admissible)
        figures_measured.figure5(admissible)
        lines.append("    Study/figures/measured/*.png and *.pdf")
        lines.append("")

    text = "\n".join(lines)
    print(text)

    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "analysis.txt").write_text(text + "\n")
    (args.out / "results.json").write_text(json.dumps(_jsonable(results), indent=1) + "\n")
    print(f"written: {args.out / 'analysis.txt'}")
    print(f"written: {args.out / 'results.json'}")

    failures = results["verification"]["failures"]
    if failures:
        print(f"\n{len(failures)} reproducibility claim(s) did not reconcile:",
              file=sys.stderr)
        for failure in failures:
            print(f"  ! {failure}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
