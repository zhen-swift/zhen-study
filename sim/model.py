"""The closed-form cost models, transcribed from THEORY.md.

This module exists to be compared against simulated output.  It is never imported by
``mechanism.py`` and nothing in ``mechanism.py`` is tuned toward it.  The direction of
fitting is one-way by construction: the model is judged against the simulation, never
the other way round.

Four forms are carried, because the point of section 16's correction C1 is that the
first two are the wrong shape and the paper needs to know by how much:

  ``shared_naive``  section 4, verbatim: T_shared ~= ((N - h) * k * T) / c
  ``split_naive``   section 5, verbatim: T_split  ~= ((N - h) * k * q_low) / c + t
  ``shared_wave``   correction C1:       T_shared ~= ceil(N * k / c) * T
  ``split_wave``    correction C1's additive counterpart, in wave form:
                                          T_split  ~= ceil(N * k / c) * r + t
  ``split_wave_last`` the same with the final interval removed, which is what the
                    simulation actually produces:
                                          T_split  ~= (ceil(N * k / c) - 1) * r + t

The naive forms treat the sweep as a fluid: total probe-seconds divided by servers.
The wave forms treat it as what it is — a sequence of synchronised rounds, each of
which costs a whole budget however many slots it uses.  Which of them the simulation
prefers is an empirical question and this module takes no side.
"""

from __future__ import annotations

import math

SHARED_NAIVE = "shared_naive"
SPLIT_NAIVE = "split_naive"
SHARED_WAVE = "shared_wave"
SPLIT_WAVE = "split_wave"
SPLIT_WAVE_LAST = "split_wave_last"


def shared_naive(n_addrs, n_hosts, k, c, T, **_):
    """THEORY.md section 4.  Dead addresses only: the analysis assumed h << N and
    that live hosts are answered and retired early enough not to matter."""
    dead = n_addrs - n_hosts
    return (dead * k * T) / c


def split_naive(n_addrs, n_hosts, k, c, r, t, **_):
    """THEORY.md section 5.  q_low is the quantity the text names; r is the
    retransmission interval sized from it, and is what the simulator is actually
    given, so r is what is substituted here."""
    dead = n_addrs - n_hosts
    return (dead * k * r) / c + t


def shared_wave(n_addrs, k, c, T, **_):
    """Correction C1.  Every address is transmitted to k times; the transmissions are
    served c at a time; each round costs a whole T because the round cannot end before
    its slowest member's budget expires.  All N addresses, not N - h: a live host
    still occupies a slot for the round in which it is probed."""
    return math.ceil(n_addrs * k / c) * T


def split_wave(n_addrs, k, c, r, t, **_):
    """The same wave argument with the short interval, plus the declaration window
    paid once at the end rather than once per address."""
    return math.ceil(n_addrs * k / c) * r + t


def split_wave_last(n_addrs, k, c, r, t, **_):
    """The wave form with the last retransmission interval removed.

    The scanner never waits out the final wave's retransmission interval: the moment
    the last probe of the sweep goes out, the only thing left to wait for is the
    declaration window, and t subsumes r whenever t > r.  So the sweep costs the
    waiting time of the waves *before* the last one, plus t.

    This form is not in THEORY.md.  It was read off the residuals of split_wave, which
    were exactly -r in every dead-dominated condition, and is offered as the
    correction rather than as a fit: the coefficient was not estimated, it was
    identified.
    """
    return (math.ceil(n_addrs * k / c) - 1) * r + t


def predict(policy, form, *, n_addrs, n_hosts, k, c, r, t, T):
    """Dispatch. `policy` is mechanism.FIXED or mechanism.SPLIT; `form` is
    'naive' or 'wave'."""
    table = {
        ("fixed", "naive"): shared_naive,
        ("fixed", "wave"): shared_wave,
        ("fixed", "wave_last"): shared_wave,      # identical: the fixed policy has no
                                                  # declaration window to absorb one
        ("split", "naive"): split_naive,
        ("split", "wave"): split_wave,
        ("split", "wave_last"): split_wave_last,
    }
    try:
        fn = table[(policy, form)]
    except KeyError:
        raise ValueError(f"{policy}/{form}") from None
    return fn(n_addrs=n_addrs, n_hosts=n_hosts, k=k, c=c, r=r, t=t, T=T)


def recall_bound(loss_rate, k):
    """The ceiling any policy is subject to when loss is independent per
    transmission: a host is found only if at least one of its k transmissions and the
    reply to it survive.  THEORY.md section 2 with F_i(b) = 1.

    Under correlated loss this is not a bound at all, and the study reports the two
    regimes separately for exactly that reason.
    """
    return 1.0 - loss_rate ** k
