"""Mechanism-level simulator of the two sweep policies.

THE RULE THIS FILE EXISTS TO OBEY
---------------------------------
This module is written from the *mechanism* — probe, wait, resend, declare — and
never from the closed-form cost model in THEORY.md sections 4 and 5.  It does not
import ``model.py``, it does not name any quantity from that model, and no constant
in it was chosen to make a prediction come out right.  If the simulator were tuned
toward the formula, agreement between the two would prove algebra and nothing else.

The comparison happens elsewhere (``run_sim.py`` records both, ``analysis/``
summarises the residual).  Where simulation and model disagree, the disagreement is
the finding.  The simulator is never adjusted to match the model.

WHAT IS MODELLED
----------------
A sweep over ``n_addrs`` addresses of which ``h`` are live.  The scanner may have at
most ``c`` probes in flight at any instant.  A probe occupies a slot from the moment
it is transmitted until it is *closed*, which happens either because a reply matched
it or because its wait budget expired.  An address that is not yet found and whose
probe closed without a reply is re-queued, up to ``k`` transmissions in total.

Two policies differ in exactly one thing: how long the scanner waits, and what it
still considers matchable.

``fixed``  One budget serves both roles.  The scanner waits ``T`` for each
           transmission and a reply that arrives after its own transmission's window
           has closed is unattributable and therefore discarded.  This is the
           single-shared-budget baseline.

``split``  The retransmission interval is ``r`` (short, sized from the fast end of
           the RTT distribution).  Absence is not declared until ``t`` after the last
           transmission of the sweep.  Because every transmission carries its own
           identity (THEORY.md section 6), a reply that arrives long after its own
           ``r`` window closed is still attributable and is still counted, provided
           the scanner has not yet declared.

Both policies are handed *identical* host populations and *identical* loss
realisations.  The loss realisation is drawn before the simulation and indexed by
(address, transmission number) or by wall-clock instant, never by the order in which
a particular policy happens to consume random numbers.  That is deliberate: in the
scratch script the two policies drew from a shared stream in different orders, which
made every paired comparison noisier than it needed to be.

TIME
----
Continuous, event-driven, in seconds.  There is no tick.
"""

from __future__ import annotations

import heapq
import math
import random
from collections import deque
from dataclasses import dataclass, field

FIXED = "fixed"
SPLIT = "split"
POLICIES = (FIXED, SPLIT)

# Event kinds.  REPLY sorts before DEADLINE so that a reply landing exactly on its
# own deadline is matched rather than timed out; a scanner reading a socket sees the
# datagram before it consults the clock.
_REPLY = 0
_RELEASE = 1
_DEADLINE = 2

# How simultaneous events are ordered, which decides the order addresses re-enter the
# retransmission queue when a whole wave of budgets expires at once.
#
# "insertion" processes them in the order the probes were sent, so the retry queue
# stays FIFO in launch order.  That is what a scanner with one queue and one timer
# wheel does.
#
# "address" processes them in numerical address order, which is what the scratch
# script did as a side effect of putting the address in its heap tuple.  It is kept
# because the difference turns out to cost a whole wave, and a claim that large should
# be a measured condition rather than a remark.
INSERTION_ORDER = "insertion"
ADDRESS_ORDER = "address"
TIE_BREAKS = (INSERTION_ORDER, ADDRESS_ORDER)

# What a concurrency slot is actually for.
#
# HOLD_UNTIL_NEXT is the mechanism as written: a probe occupies a slot from the moment
# it is sent until the moment its replacement is due, so lengthening the gap to the next
# transmission lengthens the time the slot is occupied.
#
# HOLD_BASE separates the two.  A slot bounds how many probes are outstanding *awaiting
# a reply*, which is a property of the network — how much traffic is in the air — and an
# address that is merely waiting for its next scheduled transmission has nothing in the
# air at all.  So the slot is released after the base interval, and the address is queued
# for its next transmission at its scheduled instant whether or not a slot is free then.
#
# The distinction does not exist while every gap equals the base interval, which is why
# it has not mattered until now.  It decides the entire cost of spacing transmissions
# out, so it is a parameter rather than an assumption.
HOLD_UNTIL_NEXT = "until_next"
HOLD_BASE = "base"
SLOT_HOLDS = (HOLD_UNTIL_NEXT, HOLD_BASE)

# Where the declaration window is measured from.
#
# ANCHOR_LAST_SEND is the rule as written: the scanner stops listening t after its very
# last transmission, whichever transmission that was.
#
# ANCHOR_LAST_TIGHT measures instead from the last transmission that was NOT
# deliberately delayed, and gives the delayed one its own reply allowance rather than a
# fresh copy of the whole tail.  A final transmission sent INTO the tail window then
# does not push the end of the sweep out, because the sweep was going to spend that
# window waiting anyway.  It is the difference between spreading transmissions costing
# the spread and costing nothing.
ANCHOR_LAST_SEND = "last_send"
ANCHOR_LAST_TIGHT = "last_tight_send"
ANCHORS = (ANCHOR_LAST_SEND, ANCHOR_LAST_TIGHT)


# --------------------------------------------------------------------------------
# Population
# --------------------------------------------------------------------------------

@dataclass(frozen=True)
class Host:
    addr: int
    rtt: float          # seconds, one way of the pair, i.e. probe-to-reply latency


@dataclass(frozen=True)
class Population:
    n_addrs: int
    hosts: dict          # addr -> Host
    q_low: float
    q_high: float

    @property
    def n_hosts(self) -> int:
        return len(self.hosts)


def make_population(n_addrs, n_hosts, q_low, q_high, rng):
    """Live hosts placed at addresses drawn without replacement, with RTTs spread
    deterministically and log-uniformly across [q_low, q_high].

    The spread is deterministic rather than sampled so that the dispersion of a
    condition is exactly the number the condition says it is.  Sampling the RTTs
    would make dispersion a random variable and blur the independent variable the
    whole study turns on.
    """
    if n_hosts > n_addrs:
        raise ValueError("more hosts than addresses")
    addrs = rng.sample(range(n_addrs), n_hosts)
    addrs.sort()
    hosts = {}
    for i, a in enumerate(addrs):
        f = 0.0 if n_hosts == 1 else i / (n_hosts - 1)
        rtt = q_low * (q_high / q_low) ** f if q_high != q_low else q_low
        hosts[a] = Host(a, rtt)
    return Population(n_addrs=n_addrs, hosts=hosts, q_low=q_low, q_high=q_high)


# --------------------------------------------------------------------------------
# Retransmission spacing
# --------------------------------------------------------------------------------
#
# The split policy's retransmission interval answers one question — "how long before I
# ask again?" — and a low quantile of observed RTT answers it well when losses are
# independent.  It answers it badly when they are not, because it packs every
# transmission for a host into a span shorter than a Wi-Fi power-save outage, so one
# outage takes all of them and the host is declared absent.  That is correction C8.
#
# A spacing schedule decouples "how long before I ask again" from "how far apart are the
# k questions".  The wait after transmission j may differ from the wait after
# transmission j-1.  The wait after the LAST transmission is the base interval, not the
# gap: there is no further transmission to schedule, so holding the concurrency slot any
# longer buys nothing.  Matchability is unaffected either way — the declaration horizon
# governs that, not the probe's own wait.


class UniformSpacing:
    """Every gap is the base interval.  What the sweep does today."""

    label = "uniform"

    def __init__(self, base):
        self.base = base
        self.factor = 1.0
        self.jitter = 0.0

    def gaps(self, k):
        return [self.base] * max(0, k - 1)

    def wait(self, addr, attempt, k):
        return self.base


class GeometricSpacing:
    """Gap j is base * factor^(j-1): two transmissions close together to recover a
    dropped frame quickly, then a deliberately late one sized past an outage.

    factor = 1 degenerates to UniformSpacing exactly, which is what makes this a
    superset of current behaviour rather than a replacement for it.
    """

    label = "geometric"

    def __init__(self, base, factor):
        self.base = base
        self.factor = factor
        self.jitter = 0.0

    def gaps(self, k):
        return [self.base * self.factor ** j for j in range(max(0, k - 1))]

    def wait(self, addr, attempt, k):
        if attempt >= k:
            return self.base
        return self.base * self.factor ** (attempt - 1)


class LateSpacing:
    """Every gap is the base interval except the last, which is an absolute duration.

    The last gap is a wall-clock constant rather than a multiple of the base interval,
    and that is the point.  The base interval is sized from observed round trips, so on
    a fast wired network it collapses toward its floor — while a Wi-Fi power-save outage
    does not get shorter just because the wire got faster.  A schedule expressed as a
    multiple of RTT therefore stops spanning the outage exactly on the networks where it
    is cheapest to span it.  The quantity being defended against has its own timescale
    and the parameter should carry that timescale.
    """

    label = "late"

    def __init__(self, base, late):
        self.base = base
        self.late = max(base, late)
        self.factor = self.late / base if base else 1.0
        self.jitter = 0.0

    def gaps(self, k):
        if k <= 1:
            return []
        return [self.base] * (k - 2) + [self.late]

    def wait(self, addr, attempt, k):
        if attempt >= k:
            return self.base       # no further transmission to schedule
        return self.late if attempt == k - 1 else self.base


class Dithered:
    """Wraps a schedule and scales each gap by a per-host, per-transmission factor
    drawn once, before the sweep, from a seeded table.

    Drawn ahead of time and indexed by (address, transmission) rather than sampled
    inside the sweep, for the same reason the loss draws are: both policies and every
    spacing schedule must see the same numbers for the same transmission of the same
    address, or a paired comparison is not paired.

    Dither does nothing about the length of a host's transmission span, so it is not a
    fix for C8 on its own.  What it prevents is resonance: a fixed interval r against a
    power-save cycle of period P with r near P, or near P/n, puts every transmission at
    the same phase of the cycle, so a host that is asleep for the first is asleep for
    all of them however many are sent.
    """

    label = "dithered"

    def __init__(self, inner, jitter, addrs, max_attempts, seed):
        self.inner = inner
        self.base = inner.base
        self.factor = inner.factor
        self.jitter = jitter
        rng = random.Random(seed)
        self._table = {
            a: [rng.uniform(1.0 - jitter, 1.0 + jitter) for _ in range(max_attempts)]
            for a in addrs
        }

    def gaps(self, k):
        return self.inner.gaps(k)

    def wait(self, addr, attempt, k):
        gap = self.inner.wait(addr, attempt, k)
        # Only the deliberately-widened gap is scattered, which is what the shipped
        # implementation does: the base retransmission interval is a measurement and
        # scattering it would scatter the measurement.
        if gap == self.inner.base:
            return gap
        row = self._table.get(addr)
        if row is None:
            return gap
        return gap * row[min(attempt, len(row)) - 1]


# --------------------------------------------------------------------------------
# Loss
# --------------------------------------------------------------------------------

class IndependentLoss:
    """Per-transmission Bernoulli loss, independent across transmissions and hosts.

    THEORY.md section 14 lists this independence as an assumption, and names it as
    false under Wi-Fi power save.  BurstyLoss below is the alternative.
    """

    model = "independent"
    burst_seconds = 0.0

    def __init__(self, rate, addrs, max_attempts, seed):
        self.rate = rate
        rng = random.Random(seed)
        # Pre-drawn and indexed by (addr, attempt) so that both policies see the
        # same coin for the same transmission of the same address.
        self._table = {
            a: [rng.random() < rate for _ in range(max_attempts)] for a in addrs
        }

    def is_lost(self, addr, attempt, at):
        return self._table[addr][attempt - 1]


class BurstyLoss:
    """Two-state continuous-time loss: a host is periodically unreachable for a
    stretch of wall-clock time rather than losing independent packets.

    This is the Wi-Fi power-save shape.  The chain alternates good/bad intervals
    with exponential holding times; the mean bad interval is ``burst_seconds`` and
    the stationary probability of being bad is ``rate``, so the marginal loss rate
    matches IndependentLoss and only the correlation differs.  Everything sent while
    the host is bad is lost; everything sent while it is good arrives.

    The realisation is a function of wall-clock instant, not of transmission index,
    so a policy that retransmits quickly and a policy that retransmits slowly see the
    same physical outage — which is the point.  A short retransmit interval that
    lands all k transmissions inside one outage should be *penalised* by this model,
    and if it is not, the model is not doing its job.
    """

    model = "bursty"

    def __init__(self, rate, burst_seconds, addrs, horizon, seed):
        self.rate = rate
        self.burst_seconds = burst_seconds
        rng = random.Random(seed)
        mean_bad = burst_seconds
        # Stationary P(bad) = mean_bad / (mean_bad + mean_good) = rate.
        mean_good = mean_bad * (1.0 - rate) / rate if rate > 0 else float("inf")
        self._intervals = {}
        for a in addrs:
            edges = []            # sorted instants where the state flips
            state_bad = rng.random() < rate
            first = state_bad
            s = 0.0
            # Start mid-interval: the host did not switch on when the sweep began.
            hold = mean_bad if state_bad else mean_good
            s += rng.expovariate(1.0 / hold) if hold != float("inf") else horizon * 2
            while s < horizon:
                edges.append(s)
                state_bad = not state_bad
                hold = mean_bad if state_bad else mean_good
                step = rng.expovariate(1.0 / hold) if hold != float("inf") else horizon * 2
                s += step
            self._intervals[a] = (first, edges)

    def is_lost(self, addr, attempt, at):
        first, edges = self._intervals[addr]
        # Number of flips strictly before `at`.
        lo, hi = 0, len(edges)
        while lo < hi:
            mid = (lo + hi) // 2
            if edges[mid] <= at:
                lo = mid + 1
            else:
                hi = mid
        return first if lo % 2 == 0 else not first


class PeriodicLoss:
    """Loss from a duty cycle rather than from a memoryless outage.

    Wi-Fi power save is not exponential.  A station wakes on the access point's DTIM
    beacon, which arrives on a fixed period, and sleeps between them; the outage is very
    nearly deterministic in both length and spacing.  BurstyLoss gets the correlation
    right and the shape wrong, and the shape is what decides whether dithering the
    retransmission interval buys anything: against an exponential outage whose phase is
    already random per host there is nothing for dither to de-synchronise.

    Parameterised by outage duration and marginal rate so it lines up with BurstyLoss:
    period = outage / rate, of which `outage` seconds are asleep.

    `shared_phase` decides whether every host wakes on the same beacon.  On a real
    network they largely do — one access point, one beacon schedule — which is the case
    where a scanner's own fixed interval can lock onto the cycle.
    """

    model = "periodic"

    def __init__(self, rate, outage_seconds, addrs, seed, shared_phase=True):
        self.rate = rate
        self.burst_seconds = outage_seconds
        self.period = outage_seconds / rate if rate > 0 else float("inf")
        self.outage = outage_seconds
        self.shared_phase = shared_phase
        rng = random.Random(seed)
        common = rng.uniform(0.0, self.period) if self.period != float("inf") else 0.0
        self._phase = {
            a: (common if shared_phase else rng.uniform(0.0, self.period))
            for a in addrs
        }

    def is_lost(self, addr, attempt, at):
        if self.period == float("inf"):
            return False
        position = (at + self._phase[addr]) % self.period
        return position < self.outage


# --------------------------------------------------------------------------------
# The sweep
# --------------------------------------------------------------------------------

@dataclass
class HostOutcome:
    """Per-host bookkeeping, for miss attribution.  Recording why a host was missed
    is evidence; deciding what the pattern means is not this module's business."""
    addr: int
    rtt: float
    found_at: float | None = None
    found_on_attempt: int | None = None
    transmissions: int = 0
    lost_transmissions: int = 0
    send_times: list = field(default_factory=list)
    reply_arrivals: list = field(default_factory=list)   # arrivals that happened
    rejected_arrivals: list = field(default_factory=list)  # arrived, not matchable


@dataclass
class SweepResult:
    policy: str
    sweep_seconds: float
    recall: float
    hosts_found: int
    n_hosts: int
    probes_sent: int
    peak_inflight: int
    last_send_seconds: float
    horizon_seconds: float
    time_to_first_host: float | None
    waves_observed: int
    outcomes: dict = field(default_factory=dict)


def simulate(policy, pop, loss, k, c, r, t, T,
             order_seed, release_on_reply=True, record_outcomes=False,
             tie_break=INSERTION_ORDER, spacing=None,
             slot_hold=HOLD_UNTIL_NEXT, horizon_anchor=ANCHOR_LAST_SEND,
             reply_allowance=None):
    """Run one sweep.  Deterministic given its arguments.

    policy              FIXED or SPLIT
    pop                 Population
    loss                object with is_lost(addr, attempt, at)
    k                   maximum transmissions per address
    c                   concurrency: probes in flight at any instant
    r                   retransmission interval, SPLIT only
    t                   declaration window after the last transmission, SPLIT only
    T                   the single shared budget, FIXED only
    order_seed          seeds the address visiting order; shared across policies
    release_on_reply    close a probe's slot the instant its reply matches.  True is
                        what a real scanner does.  False reproduces the scratch
                        script, which held the slot until the budget expired even
                        after the host answered.  Exposed so the difference can be
                        measured rather than argued about.
    tie_break           INSERTION_ORDER or ADDRESS_ORDER; see above.
    spacing             a retransmission spacing schedule for the SPLIT policy; None
                        means UniformSpacing(r), which is what the sweep does today.
                        The FIXED policy is the baseline and always spaces at T.
    slot_hold           HOLD_UNTIL_NEXT or HOLD_BASE; see above.
    horizon_anchor      ANCHOR_LAST_SEND or ANCHOR_LAST_TIGHT; see above.
    reply_allowance     how long the deliberately-late transmission is given to be
                        answered, under ANCHOR_LAST_TIGHT.  Defaults to r.
    """
    if policy not in POLICIES:
        raise ValueError(policy)
    if k < 1 or c < 1:
        raise ValueError("k and c must be positive")

    if policy == SPLIT and spacing is None:
        spacing = UniformSpacing(r)
    if (T if policy == FIXED else r) <= 0:
        raise ValueError("wait budget must be positive")
    if tie_break not in TIE_BREAKS:
        raise ValueError(tie_break)
    if slot_hold not in SLOT_HOLDS:
        raise ValueError(slot_hold)
    if horizon_anchor not in ANCHORS:
        raise ValueError(horizon_anchor)
    if reply_allowance is None:
        reply_allowance = r

    def wait_for(addr, attempt):
        """When this transmission's replacement becomes due."""
        if policy == FIXED:
            return T
        return spacing.wait(addr, attempt, k)

    def hold_for(addr, attempt):
        """How long this transmission occupies a concurrency slot."""
        if policy == FIXED or slot_hold == HOLD_UNTIL_NEXT:
            return wait_for(addr, attempt)
        return min(r, wait_for(addr, attempt))

    n = pop.n_addrs
    hosts = pop.hosts

    order_rng = random.Random(order_seed)
    queue = list(range(n))
    order_rng.shuffle(queue)
    retry = deque()

    attempts = [0] * n
    open_probes = set()             # (addr, attempt) still occupying a slot
    found = {}                      # addr -> instant it became known present
    outcomes = {a: HostOutcome(addr=a, rtt=h.rtt) for a, h in hosts.items()} \
        if record_outcomes else {}

    heap = []
    seqno = 0
    free = c
    inflight = 0
    peak = 0
    probes_sent = 0
    last_send = 0.0
    last_tight_send = 0.0
    last_close = 0.0
    first_found = None
    wave_marks = set()

    def key(addr, a):
        return seqno if tie_break == INSERTION_ORDER else (addr, a)

    def launch(addr, at):
        nonlocal seqno, free, inflight, peak, probes_sent, last_send, last_tight_send
        attempts[addr] += 1
        a = attempts[addr]
        probes_sent += 1
        free -= 1
        inflight += 1
        if inflight > peak:
            peak = inflight
        if at > last_send:
            last_send = at
        if a < k and at > last_tight_send:
            last_tight_send = at
        wave_marks.add(round(at, 9))
        open_probes.add((addr, a))
        wait = wait_for(addr, a)
        host = hosts.get(addr)
        if host is not None:
            rec = outcomes.get(addr)
            if rec is not None:
                rec.transmissions += 1
                rec.send_times.append(at)
            if loss.is_lost(addr, a, at):
                if rec is not None:
                    rec.lost_transmissions += 1
            else:
                seqno += 1
                heapq.heappush(heap,
                               (at + host.rtt, _REPLY, key(addr, a), addr, a, at))
        seqno += 1
        hold = hold_for(addr, a)
        if hold < wait:
            heapq.heappush(heap, (at + hold, _RELEASE, key(addr, a), addr, a, at))
        heapq.heappush(heap, (at + wait, _DEADLINE, key(addr, a), addr, a, at))

    def refill(at):
        while free > 0 and (queue or retry):
            nxt = queue.pop() if queue else retry.popleft()
            if nxt in found:
                continue
            launch(nxt, at)

    def close(addr, a, at):
        nonlocal free, inflight, last_close
        if (addr, a) not in open_probes:
            return
        open_probes.discard((addr, a))
        free += 1
        inflight -= 1
        if at > last_close:
            last_close = at
        refill(at)

    refill(0.0)

    while heap:
        now, kind, _, addr, a, sent = heapq.heappop(heap)
        if kind == _REPLY:
            rec = outcomes.get(addr)
            if policy == FIXED:
                matchable = now <= sent + T
            elif horizon_anchor == ANCHOR_LAST_TIGHT:
                matchable = now <= max(last_tight_send + t,
                                       last_send + reply_allowance)
            else:
                # Per-transmission identity keeps an expired probe attributable; the
                # scanner stops matching only when it declares, which it does t after
                # its last transmission.  last_send is final by the time any reply is
                # processed after the transmission phase, and any reply processed
                # during it satisfies now <= last_send <= last_send + t regardless.
                matchable = now <= last_send + t
            if rec is not None:
                (rec.reply_arrivals if matchable else rec.rejected_arrivals).append(now)
            if matchable:
                if addr not in found:
                    found[addr] = now
                    if first_found is None:
                        first_found = now
                    if rec is not None:
                        rec.found_at = now
                        rec.found_on_attempt = a
                if release_on_reply:
                    close(addr, a, now)
        elif kind == _RELEASE:
            # The slot is given back; the address is not yet due for its next
            # transmission and does not enter the retry queue here.
            close(addr, a, now)
        else:
            was_open = (addr, a) in open_probes
            if addr not in found and attempts[addr] < k:
                retry.append(addr)
            if was_open:
                close(addr, a, now)
            else:
                refill(now)

    if policy == SPLIT:
        if horizon_anchor == ANCHOR_LAST_TIGHT:
            horizon = max(last_tight_send + t, last_send + reply_allowance)
        else:
            horizon = last_send + t
        sweep_end = max(last_close, horizon)
    else:
        horizon = last_send + T
        sweep_end = last_close

    if inflight != 0 or free != c or open_probes:
        raise AssertionError("slot accounting leaked: "
                             f"inflight={inflight} free={free} open={len(open_probes)}")

    n_hosts = pop.n_hosts
    return SweepResult(
        policy=policy,
        sweep_seconds=sweep_end,
        recall=(len(found) / n_hosts) if n_hosts else float("nan"),
        hosts_found=len(found),
        n_hosts=n_hosts,
        probes_sent=probes_sent,
        peak_inflight=peak,
        last_send_seconds=last_send,
        horizon_seconds=horizon,
        time_to_first_host=first_found,
        waves_observed=len(wave_marks),
        outcomes=outcomes,
    )


def trace_inflight(policy, pop, loss, k, c, r, t, T, order_seed,
                   release_on_reply=True, spacing=None,
                   slot_hold=HOLD_UNTIL_NEXT):
    """Re-run the sweep recording every slot open and slot close instant.

    Used only by the tests.  The invariant that matters is not "peak <= c" as
    reported by the simulator's own counter — a counter can agree with a bug — but
    that an independent reconstruction of the in-flight set from the transmission and
    closure instants never exceeds c at any instant.
    """
    events = []            # (instant, +1 open / -1 close)

    n = pop.n_addrs
    hosts = pop.hosts
    if policy == SPLIT and spacing is None:
        spacing = UniformSpacing(r)

    def wait_for(addr, attempt):
        if policy == FIXED:
            return T
        return spacing.wait(addr, attempt, k)

    def hold_for(addr, attempt):
        if policy == FIXED or slot_hold == HOLD_UNTIL_NEXT:
            return wait_for(addr, attempt)
        return min(r, wait_for(addr, attempt))

    order_rng = random.Random(order_seed)
    queue = list(range(n))
    order_rng.shuffle(queue)
    retry = deque()
    attempts = [0] * n
    open_probes = set()
    found = {}
    heap = []
    seqno = 0
    free = c
    last_send = 0.0

    def launch(addr, at):
        nonlocal seqno, free, last_send
        attempts[addr] += 1
        a = attempts[addr]
        free -= 1
        last_send = max(last_send, at)
        open_probes.add((addr, a))
        events.append((at, +1))
        wait = wait_for(addr, a)
        host = hosts.get(addr)
        if host is not None and not loss.is_lost(addr, a, at):
            seqno += 1
            heapq.heappush(heap, (at + host.rtt, _REPLY, seqno, addr, a, at))
        seqno += 1
        hold = hold_for(addr, a)
        if hold < wait:
            heapq.heappush(heap, (at + hold, _RELEASE, seqno, addr, a, at))
        seqno += 1
        heapq.heappush(heap, (at + wait, _DEADLINE, seqno, addr, a, at))

    def refill(at):
        while free > 0 and (queue or retry):
            nxt = queue.pop() if queue else retry.popleft()
            if nxt in found:
                continue
            launch(nxt, at)

    def close(addr, a, at):
        nonlocal free
        if (addr, a) not in open_probes:
            return
        open_probes.discard((addr, a))
        free += 1
        events.append((at, -1))
        refill(at)

    refill(0.0)
    while heap:
        now, kind, _, addr, a, sent = heapq.heappop(heap)
        if kind == _REPLY:
            matchable = (now <= sent + T) if policy == FIXED else (now <= last_send + t)
            if matchable:
                found.setdefault(addr, now)
                if release_on_reply:
                    close(addr, a, now)
        elif kind == _RELEASE:
            # The slot is given back; the address is not yet due for its next
            # transmission and does not enter the retry queue here.
            close(addr, a, now)
        else:
            was_open = (addr, a) in open_probes
            if addr not in found and attempts[addr] < k:
                retry.append(addr)
            if was_open:
                close(addr, a, now)
            else:
                refill(now)

    # Reconstruct the in-flight curve independently of any counter the simulator kept.
    # The list is already in causal order and non-decreasing in time: events are
    # processed in heap order, and a closure appends its own -1 before the refill it
    # triggers appends any +1 at the same instant.  It is deliberately NOT re-sorted;
    # re-sorting would destroy the close-then-open ordering at a tie and manufacture a
    # phantom overshoot that the scanner never has.
    curve = []
    cur = 0
    for at, delta in events:
        cur += delta
        curve.append((at, cur))
    return curve
