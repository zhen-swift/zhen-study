"""The simulation grid, expressed once, as data.

A condition that is not in this file cannot appear in the data, and every column of
the output is a field of a Condition or an outcome of a sweep.  Nothing is aggregated
here and no statistic is computed here; this module only says what shall be run.

Six regimes, of which four are things a physical testbed on one household network
cannot reach:

  e1_dispersion   the independent variable the theory turns on, swept from 1x
  e2_frontier     speed against recall, every fixed budget against every split tail
  e3_density      live hosts from 1 address in 254 up to every address
  e4_scale        /24 through /16 at constant density and constant concurrency
  e5_bursty       loss correlated in time, the assumption section 14 admits is false
  e6_attempts     k from 1 to 5 crossed with five loss regimes
  e7_c3           the correction-C3 question, with enough replicates to see 0.004
  e8_scheduler    two scheduler choices that turn out to cost a whole wave

Budget convention, applied throughout and stated once: a fixed template must cover the
tail of the RTT distribution or it cannot reach the slow hosts at all, so T is sized
from q_high.  The split policy retransmits from the fast end, so r is sized from
q_low, and pays a declaration window t sized from the tail exactly once.  The 1.05
margin is the scratch script's and is kept so the two studies are comparable; it is
not a tuned parameter and nothing here depends on its value.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

MARGIN = 1.05

# The reference cell: a /24 with nine live hosts, as measured on the development
# network, 240 probes in flight, three transmissions per address.
N_ADDRS = 254
N_HOSTS = 9
CONCURRENCY = 240
ATTEMPTS = 3
Q_LOW = 0.049
DISPERSION = 12.0
LOSS = 0.02


@dataclass(frozen=True)
class Condition:
    experiment: str
    condition_id: str
    policies: tuple
    n_addrs: int
    n_hosts: int
    q_low: float
    q_high: float
    loss: float
    loss_model: str          # "independent" | "bursty"
    burst_seconds: float
    attempts_k: int
    concurrency_c: int
    retransmit_r: float
    declare_t: float
    fixed_budget_T: float
    release_on_reply: bool
    tie_break: str           # "insertion" | "address"
    slot_hold: str           # "until_next" | "base"
    horizon_anchor: str      # "last_send" | "last_tight_send"
    spacing_policy: str      # "uniform" | "late" | "spread_into_tail"
    spread_seconds: float    # nominal gap before the final transmission
    spacing_jitter: float    # per-host scatter on that gap, as a fraction
    reply_allowance: float   # what the late transmission is given, when anchored
    replicates: int

    @property
    def dispersion(self):
        return self.q_high / self.q_low

    @property
    def host_density(self):
        return self.n_hosts / self.n_addrs

    @property
    def waves_expected(self):
        return math.ceil(self.n_addrs * self.attempts_k / self.concurrency_c)


def _cell(experiment, cid, *, policies=("fixed", "split"),
          n_addrs=N_ADDRS, n_hosts=N_HOSTS, q_low=Q_LOW, dispersion=DISPERSION,
          loss=LOSS, loss_model="independent", burst_seconds=0.0,
          k=ATTEMPTS, c=CONCURRENCY, T=None, r=None, t=None,
          release_on_reply=True, tie_break="insertion", slot_hold="until_next",
          horizon_anchor="last_send", spacing_policy="uniform", spread=0.0,
          spacing_jitter=0.0, reply_allowance=None, replicates=200):
    q_high = q_low * dispersion
    return Condition(
        experiment=experiment,
        condition_id=cid,
        policies=tuple(policies),
        n_addrs=n_addrs,
        n_hosts=n_hosts,
        q_low=q_low,
        q_high=q_high,
        loss=loss,
        loss_model=loss_model,
        burst_seconds=burst_seconds,
        attempts_k=k,
        concurrency_c=c,
        retransmit_r=q_low * MARGIN if r is None else r,
        declare_t=q_high * MARGIN if t is None else t,
        fixed_budget_T=q_high * MARGIN if T is None else T,
        release_on_reply=release_on_reply,
        tie_break=tie_break,
        slot_hold=slot_hold,
        horizon_anchor=horizon_anchor,
        spacing_policy=spacing_policy,
        spread_seconds=spread,
        spacing_jitter=spacing_jitter,
        reply_allowance=(q_low * MARGIN if reply_allowance is None
                         else reply_allowance),
        replicates=replicates,
    )


# --------------------------------------------------------------------------------
# e1: dispersion
# --------------------------------------------------------------------------------

E1_DISPERSIONS = (1.0, 2.0, 4.0, 7.0, 12.0, 20.0, 41.0, 80.0)


def e1_dispersion():
    return [_cell("e1_dispersion", f"e1_d{d:g}", dispersion=d, replicates=200)
            for d in E1_DISPERSIONS]


# --------------------------------------------------------------------------------
# e2: the speed/recall frontier
# --------------------------------------------------------------------------------

E2_FIXED_BUDGETS = (0.05, 0.075, 0.1, 0.15, 0.2, 0.3, 0.45, 0.63, 0.9, 1.3)
E2_SPLIT_TAILS = (0.05, 0.1, 0.15, 0.2, 0.3, 0.45, 0.63, 0.9, 1.3)
E2_LOSS = 0.15
E2_REPLICATES = 300


def e2_frontier():
    out = []
    for T in E2_FIXED_BUDGETS:
        out.append(_cell("e2_frontier", f"e2_fixed_T{T*1000:.0f}ms",
                         policies=("fixed",), loss=E2_LOSS, T=T,
                         replicates=E2_REPLICATES))
    for t in E2_SPLIT_TAILS:
        out.append(_cell("e2_frontier", f"e2_split_t{t*1000:.0f}ms",
                         policies=("split",), loss=E2_LOSS, t=t,
                         replicates=E2_REPLICATES))
    return out


# --------------------------------------------------------------------------------
# e3: host density
# --------------------------------------------------------------------------------

# Deliberately dense near both ends: the sparse end is where the technique is claimed
# to work, and the crossover turns out to sit within a few addresses of saturation.
E3_HOSTS = (1, 2, 4, 9, 10, 11, 12, 13, 14, 15, 16, 20, 24, 32, 48, 64, 96, 128,
            160, 192, 224, 240, 248, 251, 252, 253, 254)


def e3_density():
    """Two sweeps, because at c = 240 on a /24 the concurrency window is nearly the
    whole address space and "density" is confounded with "the queue is one wave deep".
    The second sweep repeats it at c = 64, where the sweep is twelve waves deep and
    density is the only thing varying."""
    out = [_cell("e3_density", f"e3_h{h}", n_hosts=h, replicates=150)
           for h in E3_HOSTS]
    out += [_cell("e3b_density_c64", f"e3b_h{h}", n_hosts=h, c=64, replicates=150)
            for h in E3_HOSTS]
    return out


# --------------------------------------------------------------------------------
# e4: scale, at constant density and constant concurrency
# --------------------------------------------------------------------------------

E4_SCALES = (
    ("/24", 254, 150),
    ("/23", 510, 100),
    ("/22", 1022, 80),
    ("/20", 4094, 40),
    ("/18", 16382, 16),
    ("/16", 65534, 8),
)
E4_DENSITY = N_HOSTS / N_ADDRS


def e4_scale():
    out = []
    for label, n, reps in E4_SCALES:
        h = max(1, round(n * E4_DENSITY))
        out.append(_cell("e4_scale", f"e4_{label.strip('/')}",
                         n_addrs=n, n_hosts=h, replicates=reps))
    return out


# --------------------------------------------------------------------------------
# e5: correlated loss
# --------------------------------------------------------------------------------

E5_BURSTS = (0.0, 0.02, 0.05, 0.1, 0.25, 0.5, 1.0, 2.0)
E5_LOSS = 0.15


def e5_bursty():
    out = [_cell("e5_bursty", "e5_independent", loss=E5_LOSS,
                 loss_model="independent", burst_seconds=0.0, replicates=200)]
    for b in E5_BURSTS[1:]:
        out.append(_cell("e5_bursty", f"e5_burst{b*1000:.0f}ms", loss=E5_LOSS,
                         loss_model="bursty", burst_seconds=b, replicates=200))
    return out


# --------------------------------------------------------------------------------
# e6: attempts crossed with loss
# --------------------------------------------------------------------------------

E6_K = (1, 2, 3, 4, 5)
E6_LOSS = (0.0, 0.02, 0.05, 0.15, 0.30)


def e6_attempts():
    return [_cell("e6_attempts", f"e6_k{k}_l{int(l*100):02d}", k=k, loss=l,
                  replicates=200)
            for l in E6_LOSS for k in E6_K]


# --------------------------------------------------------------------------------
# e7: the correction-C3 question
# --------------------------------------------------------------------------------

E7_BUDGETS = (0.63, 0.9, 1.3, 2.0)
E7_REPLICATES = 1000


def e7_c3():
    out = []
    for release in (True, False):
        tag = "rel" if release else "hold"
        for T in E7_BUDGETS:
            out.append(_cell("e7_c3", f"e7_{tag}_fixed_T{T*1000:.0f}ms",
                             policies=("fixed",), loss=E2_LOSS, T=T,
                             release_on_reply=release, replicates=E7_REPLICATES))
        for t in E7_BUDGETS:
            out.append(_cell("e7_c3", f"e7_{tag}_split_t{t*1000:.0f}ms",
                             policies=("split",), loss=E2_LOSS, t=t,
                             release_on_reply=release, replicates=E7_REPLICATES))
    return out


# --------------------------------------------------------------------------------
# e8: two scheduler choices
# --------------------------------------------------------------------------------
#
# Neither of these is part of the technique.  Both are decisions an implementer makes
# without thinking about them, and the scratch script happened to make both the
# expensive way: it ordered simultaneous timeouts by address rather than by the order
# the probes went out, and it held a slot until the budget expired even after the host
# had answered.  Together they cost a whole wave of the fixed policy's budget, which
# is where THEORY.md's correction C2 got its speedup table.  Sweeping them here makes
# that a measured quantity instead of a remark.

E8_DISPERSIONS = (1.0, 2.0, 4.0, 7.0, 12.0, 20.0, 41.0, 80.0)


def e8_scheduler():
    out = []
    for tie in ("insertion", "address"):
        for release in (True, False):
            for d in E8_DISPERSIONS:
                out.append(_cell("e8_scheduler",
                                 f"e8_{tie}_{'rel' if release else 'hold'}_d{d:g}",
                                 dispersion=d, release_on_reply=release,
                                 tie_break=tie, replicates=100))
    return out


# --------------------------------------------------------------------------------
# e9: transmission spacing under correlated loss — correction C8's fix
# --------------------------------------------------------------------------------
#
# C8 measured the damage: three transmissions spaced by a low quantile of RTT span less
# than a Wi-Fi power-save outage, so one outage takes all three.  This sweeps the
# candidate repairs against the same burst table, in two cells that differ in the one
# thing the repair's price depends on — whether the tail budget has any slack in it.
#
#   deployment   a fast LAN answering in a millisecond, where the tail budget is its
#                250 ms floor and almost all of it is slack
#   study        the heterogeneous cell of C8, where a 600 ms host makes the tail
#                budget genuinely the tail and there is no slack at all
#
# Four schedules.  `uniform` is today.  `late400` delays the final transmission by a
# fixed 400 ms and extends the sweep to pay for it.  `spread` delays it by whatever the
# tail window can absorb and anchors the declaration instant to the last tight
# transmission, so it costs nothing.  `spread_dither` adds per-host scatter, which
# matters only against a periodic outage.

E9_CELLS = {
    # label:        (q_low,  q_high, r,       t,      reply allowance)
    "deployment": (0.001, 0.012, 0.025, 0.250, 0.012),
    "study":      (0.049, 0.600, 0.05145, 0.6174, 0.6174),
}

E9_OUTAGES = (("independent", 0.0), ("bursty", 0.05), ("bursty", 0.10),
              ("bursty", 0.25), ("bursty", 0.50), ("bursty", 1.00),
              ("bursty", 2.00), ("periodic", 0.10), ("periodic", 0.25),
              ("periodic", 0.50), ("periodic", 1.00))
E9_LOSS = 0.15
E9_REPLICATES = 400


def e9_spacing():
    out = []
    for cell, (ql, qh, r, t, allowance) in E9_CELLS.items():
        free = max(0.0, (t - allowance) / 1.25)     # what the tail window can absorb
        schedules = (
            ("uniform", "uniform", 0.0, 0.0, "last_send"),
            ("late400", "late", 0.400, 0.0, "last_send"),
            ("spread", "spread_into_tail", free, 0.0, "last_tight_send"),
            ("spread_dither", "spread_into_tail", free, 0.25, "last_tight_send"),
        )
        for model, outage in E9_OUTAGES:
            tag = "indep" if model == "independent" else f"{model[:4]}{outage*1000:.0f}"
            for name, policy, spread, jitter, anchor in schedules:
                out.append(_cell(
                    "e9_spacing", f"e9_{cell}_{tag}_{name}",
                    policies=("fixed", "split") if name == "uniform" else ("split",),
                    q_low=ql, dispersion=qh / ql, loss=E9_LOSS,
                    loss_model=model, burst_seconds=outage,
                    c=256, r=r, t=t, T=t,
                    slot_hold="base", horizon_anchor=anchor,
                    spacing_policy=policy, spread=spread, spacing_jitter=jitter,
                    reply_allowance=allowance, replicates=E9_REPLICATES))
    return out


ALL = (e1_dispersion, e2_frontier, e3_density, e4_scale, e5_bursty,
       e6_attempts, e7_c3, e8_scheduler, e9_spacing)


def all_conditions():
    out = []
    for fn in ALL:
        out.extend(fn())
    ids = [c.condition_id for c in out]
    if len(ids) != len(set(ids)):
        raise AssertionError("duplicate condition ids")
    return out
