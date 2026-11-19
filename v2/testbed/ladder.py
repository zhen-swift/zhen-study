"""Study 2's four delay ladders, one per RTT dispersion, as data.

Study 1's segment (`testbed/plan.py`) carries five delays, 1, 5, 25, 100 and 500 ms, two responders each: a
dispersion of 500. Study 2 measures four dispersions, 1×, ~5×, ~50× and ~500× (`v2/PLAN.md`), and 500× must be
study 1's manifest exactly.

**The slowest host stays at 500 ms; only the spread changes** (JC, 2026-11-18). Each of study 1's delays `s` is
scaled in log space with the top fixed:

    rtt(s, d) = 500 · (s / 500) ^ (ln d / ln 500)        rounded to 0.1 ms

so at d = 500 every delay is study 1's, at d = 1 every delay is 500 ms, and in between the five levels keep study
1's shape. Holding the slowest host fixed keeps the wait any network-wide timeout must cover the same in every
manifest, so a result about dispersion (H2) is not also a result about the slowest round trip.

Composition and roles are study 1's, unchanged: the same ten responders with the same ICMP and TCP policy and the
same loss. Only `target_rtt_ms` differs.
"""

from __future__ import annotations

import dataclasses
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "testbed"))
import plan  # noqa: E402  study 1's composition, imported rather than copied

#: The dispersions study 2 measures (PLAN.md, phase 1).
DISPERSIONS = (1, 5, 50, 500)

#: Fixed by the anchor: the slowest delay in every manifest, which is study 1's slowest.
SLOWEST_MS = 500.0

#: Study 1's delay levels, read from its plan rather than restated.
STUDY1_LEVELS = tuple(sorted({r.target_rtt_ms for r in plan.RESPONDERS}))

RULE = "rtt(s, d) = 500 * (s / 500) ** (ln d / ln 500), rounded to 0.1 ms; s = study 1's target"


def scaled(s, d):
    """One of study 1's delays `s`, rescaled to dispersion `d` with the slowest delay fixed."""
    if d not in DISPERSIONS:
        raise ValueError(f"dispersion {d} is not one of {DISPERSIONS}")
    if d == 500:
        return float(s)  # exactly study 1's, not a float that rounds back to it
    k = math.log(d) / math.log(500.0)
    return round(SLOWEST_MS * (s / SLOWEST_MS) ** k, 1)


def ladder(d):
    """The five delay levels for dispersion `d`, fastest first."""
    return tuple(scaled(s, d) for s in STUDY1_LEVELS)


def responders(d):
    """Study 1's ten responders with their targets moved to dispersion `d`."""
    return tuple(dataclasses.replace(r, target_rtt_ms=scaled(r.target_rtt_ms, d))
                 for r in plan.RESPONDERS)


def machines(d):
    """Responders grouped into the machines that host them: the same grouping and names as study 1."""
    rs = responders(d)
    n = plan.RESPONDERS_PER_VM
    return [(f"netbed{i // n + 1}", rs[i:i + n]) for i in range(0, len(rs), n)]


def achieved_dispersion(d):
    lv = ladder(d)
    return lv[-1] / lv[0]


if __name__ == "__main__":
    for d in DISPERSIONS:
        print(f"{d:>4}×  " + "  ".join(f"{x:>6g}" for x in ladder(d))
              + f"   (max/min {achieved_dispersion(d):.1f})")
