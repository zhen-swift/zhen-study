"""Mechanism-level simulator of the two sweep policies.

Written from the MECHANISM (probe, wait, resend, declare), never from the closed-form
cost model in THEORY.md section 5. If it agreed with the formula by construction it
would prove nothing; the point is to see whether the formula survives contact with a
simulation that does not know it exists.

Both policies see identical host populations, identical loss draws and identical RTT
draws — the only difference is the timing policy.
"""
import heapq, random, statistics
from dataclasses import dataclass

@dataclass
class Host:
    addr: int
    rtt: float          # seconds
    loss: float         # per-probe loss probability

def make_population(n_addrs, n_hosts, q_low, q_high, loss, rng):
    """Hosts spread log-uniformly between q_low and q_high — the dispersion is the
    independent variable the whole theory turns on."""
    addrs = rng.sample(range(n_addrs), n_hosts)
    hosts = {}
    for i, a in enumerate(addrs):
        # deterministic spread so dispersion is exact, not sampled
        f = 0 if n_hosts == 1 else i / (n_hosts - 1)
        rtt = q_low * (q_high / q_low) ** f
        hosts[a] = Host(a, rtt, loss)
    return hosts

def simulate(policy, n_addrs, hosts, k, c, r, t, T, rng):
    """Event-driven. A probe occupies one of c slots from send until reply or timeout.

    shared:每 attempt waits T; nothing is matchable after its own window.
    split:  every attempt waits r; a final window t during which late replies still
            count, because per-transmission tokens make them attributable.
    """
    budget = T if policy == "shared" else r
    now = 0.0
    free_slots = c
    pending = []            # (event_time, kind, addr, attempt, send_time)
    queue = list(range(n_addrs))
    rng.shuffle(queue)
    attempts_used = {a: 0 for a in range(n_addrs)}
    found = {}
    last_send = 0.0
    inflight_peak = 0
    inflight = 0

    def launch(addr, at):
        nonlocal free_slots, inflight, inflight_peak, last_send
        free_slots -= 1
        inflight += 1
        inflight_peak = max(inflight_peak, inflight)
        last_send = max(last_send, at)
        attempts_used[addr] += 1
        h = hosts.get(addr)
        # The reply either happens (after rtt) or the probe is lost.
        if h is not None and rng.random() >= h.loss:
            heapq.heappush(pending, (at + h.rtt, 0, addr, attempts_used[addr], at))
        heapq.heappush(pending, (at + budget, 1, addr, attempts_used[addr], at))

    while queue and free_slots > 0:
        launch(queue.pop(), now)

    retry_queue = []
    while pending:
        now, kind, addr, attempt, sent = heapq.heappop(pending)
        if kind == 0:                                    # a reply arrived
            if addr in found:
                continue
            late = (now - sent) > budget
            if late and policy == "shared":
                continue                                 # window closed, evidence discarded
            if late and policy == "split" and now > last_send + t:
                continue                                 # even the tail has expired
            found[addr] = now
        else:                                            # this attempt's window closed
            if addr in found:
                inflight -= 1; free_slots += 1
            else:
                inflight -= 1; free_slots += 1
                if attempts_used[addr] < k:
                    retry_queue.append(addr)
            while free_slots > 0 and (queue or retry_queue):
                nxt = queue.pop() if queue else retry_queue.pop(0)
                if nxt in found:
                    continue
                launch(nxt, now)

    # A split sweep is not finished until the declaration window has passed; a shared
    # sweep ends when the last attempt's window closes.
    end = (last_send + t) if policy == "split" else now
    return {
        "time": max(end, now),
        "recall": len(found) / len(hosts),
        "peak_inflight": inflight_peak,
        "probes": sum(attempts_used.values()),
    }

def closed_form(policy, n_addrs, n_hosts, k, c, r, t, T, q_high):
    """THEORY.md section 5, transcribed. Deliberately naive — the question is whether
    the simulation lands near it."""
    dead = n_addrs - n_hosts
    if policy == "shared":
        return (dead * k * T) / c
    return (dead * k * r) / c + t

if __name__ == "__main__":
    rng = random.Random(20260904)
    N, H, K, C = 254, 9, 3, 240
    Q_LOW = 0.049
    LOSS = 0.02
    print(f"{'q_high':>8} {'disp':>6} | {'shared t':>9} {'model':>7} | {'split t':>8} {'model':>7} | {'speedup':>8} | {'rec sh':>7} {'rec sp':>7}")
    print("-" * 92)
    for q_high in (0.049, 0.1, 0.2, 0.35, 0.6, 1.0, 2.0):
        disp = q_high / Q_LOW
        T = q_high * 1.05          # a fixed template must cover the tail to get recall
        r = Q_LOW * 1.05           # retransmit from the LOW quantile
        t = q_high * 1.05          # declaration window covers the tail, paid once
        sh, sp = [], []
        rec_sh, rec_sp = [], []
        for trial in range(40):
            pop = make_population(N, H, Q_LOW, q_high, LOSS, random.Random(1000 + trial))
            a = simulate("shared", N, pop, K, C, r, t, T, random.Random(5000 + trial))
            b = simulate("split",  N, pop, K, C, r, t, T, random.Random(5000 + trial))
            sh.append(a["time"]); sp.append(b["time"])
            rec_sh.append(a["recall"]); rec_sp.append(b["recall"])
        msh = statistics.median(sh); msp = statistics.median(sp)
        cf_sh = closed_form("shared", N, H, K, C, r, t, T, q_high)
        cf_sp = closed_form("split",  N, H, K, C, r, t, T, q_high)
        print(f"{q_high*1000:7.0f}m {disp:5.1f}x | {msh:8.3f}s {cf_sh:6.3f}s | {msp:7.3f}s {cf_sp:6.3f}s |"
              f" {msh/msp:7.2f}x | {statistics.mean(rec_sh):6.3f} {statistics.mean(rec_sp):6.3f}")
