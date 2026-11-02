"""The collection's NDJSON and the stratum sidecar, as the paper's figures see it.

This module is the paper's own loader.  It re-uses `Study/analysis/collection.py`
rather than re-implementing the two rules that decide every number downstream —
recall is computed against the testbed manifest's declared responder set, and the
stratum comes from the sidecar and never from the analysing machine's clock.

`sys.dont_write_bytecode` is set before the import on purpose: `Study/` is read-only
for the paper, and an import that drops a `__pycache__` into it is a write.
"""

from __future__ import annotations

import sys
from pathlib import Path

PAPER = Path(__file__).resolve().parent.parent
REPO = PAPER.parent
STUDY = REPO / "Study"
RUNS = STUDY / "data" / "runs.ndjson"
SIDECAR = STUDY / "analysis" / "strata.json"
FIGURES = PAPER / "figures"

sys.dont_write_bytecode = True
sys.path.insert(0, str(STUDY / "analysis"))

import collection  # noqa: E402  (the import must follow the path and bytecode rules)

load = collection.load
admissible = collection.admissible
arm = collection.arm
by_condition = collection.by_condition
truth_set = collection.truth_set
paired_by_block = collection.paired_by_block

NETSANITY_DISCOVERY = collection.NETSANITY_DISCOVERY
NMAP_PRIV = collection.NMAP_PRIV
NMAP_UNPRIV = collection.NMAP_UNPRIV
DISCOVERY_CONDITIONS = collection.DISCOVERY_CONDITIONS

#: Every condition in the matrix, in the order the paper's tables use.
ALL_CONDITIONS = (
    "ns.fixed.timeout", "ns.disc.unpriv", "ns.budget.shared", "ns.naming.full",
    "nmap.sn.priv.T5", "nmap.sn.priv.T4", "nmap.sn.priv.T3", "nmap.sn.priv.T2",
    "nmap.sn.unpriv.T5", "nmap.sn.unpriv.T4", "nmap.sn.unpriv.T3",
    "nmap.sn.unpriv.T2", "nmap.naming.broadcast",
)

#: Short labels for the figures.  A 3.5 in column has no room for a condition id, and
#: a legend that abbreviates differently from the tables costs the reader a lookup, so
#: the paper's tables carry this same column.
SHORT = {
    "ns.disc.unpriv": "ns adaptive",
    "ns.fixed.timeout": "ns fixed-50",
    "ns.budget.shared": "ns shared",
    "ns.naming.full": "ns full",
    "nmap.sn.priv.T2": "priv T2",
    "nmap.sn.priv.T3": "priv T3",
    "nmap.sn.priv.T4": "priv T4",
    "nmap.sn.priv.T5": "priv T5",
    "nmap.sn.unpriv.T2": "unpriv T2",
    "nmap.sn.unpriv.T3": "unpriv T3",
    "nmap.sn.unpriv.T4": "unpriv T4",
    "nmap.sn.unpriv.T5": "unpriv T5",
    "nmap.naming.broadcast": "nmap broadcast",
}

#: The five round-trip times the programmable segment imposes, from
#: `Study/testbed/manifest.json`'s achieved column.
SEGMENT_RTT_MS = (0.93, 4.98, 24.92, 99.99, 507.9)

#: The two 500 ms responders, which are every miss netsanity makes in this collection.
SLOW_RESPONDERS = ("192.168.64.12", "192.168.64.13")


def runs():
    """Every admissible run, both arms, flagged blocks kept as the protocol admits."""
    return admissible(load(RUNS, SIDECAR))


def median(values):
    ordered = sorted(values)
    n = len(ordered)
    if n == 0:
        raise ValueError("no values")
    mid = n // 2
    return ordered[mid] if n % 2 else (ordered[mid - 1] + ordered[mid]) / 2


def quantile(values, q):
    ordered = sorted(values)
    if not ordered:
        raise ValueError("no values")
    pos = (len(ordered) - 1) * q
    low = int(pos)
    high = min(low + 1, len(ordered) - 1)
    return ordered[low] + (ordered[high] - ordered[low]) * (pos - low)


def bootstrap_median_ci(values, resamples=10000, seed=20260922):
    """A percentile bootstrap on the median, at the protocol's 10,000 resamples.

    The seed is fixed so the figure is byte-identical between runs; the analysis's own
    intervals are in `Study/analysis/out/results.json` and agree to the printed digits.
    """
    import random
    if len(values) < 2:
        point = values[0] if values else float("nan")
        return point, point, point
    rng = random.Random(seed)
    n = len(values)
    draws = []
    for _ in range(resamples):
        draws.append(median([values[rng.randrange(n)] for _ in range(n)]))
    draws.sort()
    return (median(values),
            draws[int(0.025 * resamples)],
            draws[int(0.975 * resamples) - 1])
