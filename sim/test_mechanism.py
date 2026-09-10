"""Tests for the simulator.

Nothing the simulator produces is worth reading until these pass.  Every test here
checks a property of the *mechanism* that must hold whatever the cost model says, so
none of them can be satisfied by tuning the simulator toward a formula.

Run:  python3 -m unittest -v sim.test_mechanism      (from Study/)
   or python3 test_mechanism.py                      (from Study/sim/)
"""

from __future__ import annotations

import math
import random
import unittest

from mechanism import (ADDRESS_ORDER, FIXED, INSERTION_ORDER, SPLIT, TIE_BREAKS,
                       BurstyLoss, IndependentLoss, make_population, simulate,
                       trace_inflight)
import model


def population(n_addrs=254, n_hosts=9, q_low=0.049, q_high=0.6, seed=1):
    return make_population(n_addrs, n_hosts, q_low, q_high, random.Random(seed))


def independent(pop, rate, k, seed=7):
    return IndependentLoss(rate, list(pop.hosts), k, seed)


class Concurrency(unittest.TestCase):

    def test_inflight_never_exceeds_c_at_any_instant(self):
        """Reconstructed from the open and close instants, not read off a counter."""
        checked = 0
        for c in (1, 4, 17, 64, 240):
            for policy in (FIXED, SPLIT):
                for release in (True, False):
                    pop = population(seed=c)
                    loss = independent(pop, 0.15, 3, seed=c * 7)
                    curve = trace_inflight(policy, pop, loss, k=3, c=c,
                                           r=0.051, t=0.63, T=0.63,
                                           order_seed=99, release_on_reply=release)
                    peak = max(v for _, v in curve)
                    self.assertLessEqual(
                        peak, c,
                        f"{policy} release={release} c={c} peaked at {peak}")
                    self.assertGreaterEqual(min(v for _, v in curve), 0)
                    checked += 1
        self.assertEqual(checked, 20)

    def test_reported_peak_matches_the_reconstruction(self):
        pop = population()
        loss = independent(pop, 0.15, 3)
        for policy in (FIXED, SPLIT):
            res = simulate(policy, pop, loss, k=3, c=32, r=0.051, t=0.63, T=0.63,
                           order_seed=5)
            curve = trace_inflight(policy, pop, loss, k=3, c=32, r=0.051, t=0.63,
                                   T=0.63, order_seed=5)
            self.assertEqual(res.peak_inflight, max(v for _, v in curve))

    def test_no_slot_is_leaked(self):
        """simulate() raises if the accounting does not return to rest; drive it hard."""
        for c in (1, 3, 240):
            for k in (1, 2, 5):
                pop = population(seed=c + k)
                loss = independent(pop, 0.3, k, seed=c * k)
                for policy in (FIXED, SPLIT):
                    simulate(policy, pop, loss, k=k, c=c, r=0.051, t=0.63, T=0.63,
                             order_seed=c + k)


class DegenerateRegime(unittest.TestCase):

    def test_zero_loss_zero_dispersion_finds_everything(self):
        q = 0.05
        pop = population(q_low=q, q_high=q)
        loss = independent(pop, 0.0, 3)
        b = q * 1.05
        f = simulate(FIXED, pop, loss, k=3, c=240, r=b, t=b, T=b, order_seed=42)
        s = simulate(SPLIT, pop, loss, k=3, c=240, r=b, t=b, T=b, order_seed=42)
        self.assertEqual(f.recall, 1.0)
        self.assertEqual(s.recall, 1.0)

    def test_zero_loss_zero_dispersion_sends_identical_probes(self):
        """With nothing to split, the two policies are the same policy: the same
        probes go to the same addresses at the same instants."""
        q = 0.05
        pop = population(q_low=q, q_high=q)
        loss = independent(pop, 0.0, 3)
        b = q * 1.05
        f = simulate(FIXED, pop, loss, k=3, c=240, r=b, t=b, T=b, order_seed=42,
                     record_outcomes=True)
        s = simulate(SPLIT, pop, loss, k=3, c=240, r=b, t=b, T=b, order_seed=42,
                     record_outcomes=True)
        self.assertEqual(f.probes_sent, s.probes_sent)
        self.assertEqual(f.last_send_seconds, s.last_send_seconds)
        for a in pop.hosts:
            self.assertEqual(f.outcomes[a].send_times, s.outcomes[a].send_times)

    def test_zero_loss_zero_dispersion_takes_the_same_time(self):
        """Equal to within the declaration rule, and the residual is accounted for
        exactly rather than waved at.

        Fixed ends when the last slot closes.  Split cannot declare until t after its
        last transmission.  When the final transmission of the sweep goes to a dead
        address the two instants coincide and the times are identical; when it goes to
        a live host that answers early, fixed closes a little sooner.  The difference
        is therefore exactly (last_send + t) - last_close and is bounded by one
        budget.  The technique confers no speed advantage at dispersion 1, which is
        the property being tested; asserting bit-equality instead would be asserting
        something that is not true of the mechanism.
        """
        q = 0.05
        b = q * 1.05
        seen_identical = 0
        for seed in range(40):
            pop = population(q_low=q, q_high=q, seed=seed)
            loss = independent(pop, 0.0, 3, seed=seed)
            f = simulate(FIXED, pop, loss, k=3, c=240, r=b, t=b, T=b, order_seed=seed)
            s = simulate(SPLIT, pop, loss, k=3, c=240, r=b, t=b, T=b, order_seed=seed)
            self.assertAlmostEqual(s.sweep_seconds,
                                   max(f.sweep_seconds, f.last_send_seconds + b),
                                   places=12)
            self.assertLessEqual(abs(s.sweep_seconds - f.sweep_seconds), b + 1e-12)
            self.assertLessEqual(f.sweep_seconds / s.sweep_seconds, 1.0 + 1e-12)
            if abs(s.sweep_seconds - f.sweep_seconds) < 1e-12:
                seen_identical += 1
        self.assertGreater(seen_identical, 0,
                           "expected some sweeps to end on a dead address")

    def test_dispersion_one_confers_no_advantage(self):
        """If the technique appears to help when there is no spread to exploit, the
        simulator is wrong.  Median speedup must not exceed 1."""
        q = 0.05
        b = q * 1.05
        speedups = []
        for seed in range(60):
            pop = population(q_low=q, q_high=q, seed=seed)
            loss = independent(pop, 0.02, 3, seed=seed)
            f = simulate(FIXED, pop, loss, k=3, c=240, r=b, t=b, T=b, order_seed=seed)
            s = simulate(SPLIT, pop, loss, k=3, c=240, r=b, t=b, T=b, order_seed=seed)
            speedups.append(f.sweep_seconds / s.sweep_seconds)
        speedups.sort()
        median = speedups[len(speedups) // 2]
        self.assertLessEqual(median, 1.0 + 1e-9, f"median speedup {median}")
        self.assertGreater(median, 0.9)


class RecallBound(unittest.TestCase):

    def test_a_host_is_found_only_if_some_transmission_survived(self):
        """The mechanism form of the 1 - loss^k bound, checked per host per run."""
        for policy in (FIXED, SPLIT):
            for rate in (0.05, 0.15, 0.4):
                pop = population()
                loss = independent(pop, rate, 3, seed=int(rate * 100))
                res = simulate(policy, pop, loss, k=3, c=240, r=0.051, t=2.0, T=2.0,
                               order_seed=3, record_outcomes=True)
                for a, out in res.outcomes.items():
                    if out.found_at is not None:
                        self.assertLess(out.lost_transmissions, out.transmissions,
                                        f"{policy} addr {a} found with every "
                                        f"transmission lost")

    def test_pooled_recall_is_bounded_by_one_minus_loss_to_the_k(self):
        """Pooled over replicates, with a generous budget so nothing else can bind."""
        k = 3
        for rate in (0.05, 0.15, 0.30):
            bound = model.recall_bound(rate, k)
            for policy in (FIXED, SPLIT):
                found = total = 0
                for seed in range(400):
                    pop = population(seed=seed)
                    loss = independent(pop, rate, k, seed=10_000 + seed)
                    res = simulate(policy, pop, loss, k=k, c=240,
                                   r=0.051, t=5.0, T=5.0, order_seed=seed)
                    found += res.hosts_found
                    total += res.n_hosts
                rec = found / total
                se = math.sqrt(bound * (1 - bound) / total)
                self.assertLessEqual(rec, bound + 4 * se + 1e-12,
                                     f"{policy} loss={rate} recall {rec} > "
                                     f"bound {bound}")
                self.assertGreaterEqual(rec, bound - 4 * se - 1e-12,
                                        f"{policy} loss={rate} recall {rec} did not "
                                        f"approach bound {bound}")

    def test_recall_approaches_the_bound_as_the_budget_grows(self):
        rate, k = 0.15, 3
        bound = model.recall_bound(rate, k)
        gaps = []
        for budget in (0.06, 0.12, 0.3, 0.8, 2.0):
            found = total = 0
            for seed in range(200):
                pop = population(seed=seed)
                loss = independent(pop, rate, k, seed=20_000 + seed)
                res = simulate(FIXED, pop, loss, k=k, c=240,
                               r=0.051, t=budget, T=budget, order_seed=seed)
                found += res.hosts_found
                total += res.n_hosts
            gaps.append(bound - found / total)
        for earlier, later in zip(gaps, gaps[1:]):
            self.assertLessEqual(later, earlier + 1e-12, gaps)
        self.assertLess(gaps[-1], 0.01, gaps)


class Monotonicity(unittest.TestCase):

    def test_fixed_recall_is_pathwise_monotone_in_the_budget(self):
        for seed in range(50):
            pop = population(seed=seed)
            loss = independent(pop, 0.15, 3, seed=30_000 + seed)
            previous = set()
            for T in (0.02, 0.06, 0.1, 0.2, 0.4, 0.8, 1.6):
                res = simulate(FIXED, pop, loss, k=3, c=240, r=0.051, t=T, T=T,
                               order_seed=seed, record_outcomes=True)
                current = {a for a, o in res.outcomes.items() if o.found_at is not None}
                self.assertTrue(previous <= current,
                                f"seed {seed} T={T} lost {previous - current}")
                previous = current

    def test_split_recall_is_pathwise_monotone_in_the_declaration_window(self):
        for seed in range(50):
            pop = population(seed=seed)
            loss = independent(pop, 0.15, 3, seed=31_000 + seed)
            previous = set()
            for t in (0.05, 0.1, 0.2, 0.4, 0.8, 1.6):
                res = simulate(SPLIT, pop, loss, k=3, c=240, r=0.051, t=t, T=0.63,
                               order_seed=seed, record_outcomes=True)
                current = {a for a, o in res.outcomes.items() if o.found_at is not None}
                self.assertTrue(previous <= current,
                                f"seed {seed} t={t} lost {previous - current}")
                previous = current

    def test_fixed_recall_is_pathwise_monotone_in_attempts(self):
        for seed in range(50):
            pop = population(seed=seed)
            loss = independent(pop, 0.25, 5, seed=32_000 + seed)
            previous = set()
            for k in (1, 2, 3, 4, 5):
                res = simulate(FIXED, pop, loss, k=k, c=240, r=0.051, t=1.0, T=1.0,
                               order_seed=seed, record_outcomes=True)
                current = {a for a, o in res.outcomes.items() if o.found_at is not None}
                self.assertTrue(previous <= current,
                                f"seed {seed} k={k} lost {previous - current}")
                previous = current

    def test_split_pooled_recall_is_monotone_in_attempts(self):
        """Split's transmission schedule shifts when k changes, so inclusion is not
        guaranteed pathwise; the pooled rate must still be non-decreasing."""
        rates = []
        for k in (1, 2, 3, 4, 5):
            found = total = 0
            for seed in range(200):
                pop = population(seed=seed)
                loss = independent(pop, 0.25, 5, seed=33_000 + seed)
                res = simulate(SPLIT, pop, loss, k=k, c=240, r=0.051, t=1.0, T=1.0,
                               order_seed=seed)
                found += res.hosts_found
                total += res.n_hosts
            rates.append(found / total)
        for earlier, later in zip(rates, rates[1:]):
            self.assertGreaterEqual(later, earlier, rates)


class Impossibility(unittest.TestCase):

    def test_a_host_slower_than_every_budget_is_never_found(self):
        pop = make_population(64, 4, 3600.0, 3600.0, random.Random(0))
        loss = IndependentLoss(0.0, list(pop.hosts), 3, 0)
        for policy in (FIXED, SPLIT):
            res = simulate(policy, pop, loss, k=3, c=16, r=0.05, t=1.0, T=1.0,
                           order_seed=0)
            self.assertEqual(res.hosts_found, 0, policy)
            self.assertEqual(res.recall, 0.0, policy)

    def test_a_host_just_inside_the_window_is_found(self):
        """The companion to the test above: proof that the previous result is the
        budget binding and not the simulator failing to find anything at all."""
        pop = make_population(64, 4, 0.9, 0.9, random.Random(0))
        loss = IndependentLoss(0.0, list(pop.hosts), 3, 0)
        for policy in (FIXED, SPLIT):
            res = simulate(policy, pop, loss, k=3, c=16, r=0.05, t=1.0, T=1.0,
                           order_seed=0)
            self.assertEqual(res.recall, 1.0, policy)


class ProbeBudget(unittest.TestCase):

    def test_probes_sent_never_exceeds_addresses_times_attempts(self):
        for n_addrs, n_hosts in ((254, 9), (254, 200), (64, 64), (1024, 3)):
            for k in (1, 3, 5):
                for policy in (FIXED, SPLIT):
                    pop = make_population(n_addrs, n_hosts, 0.049, 0.6,
                                          random.Random(n_addrs + k))
                    loss = independent(pop, 0.15, k, seed=n_addrs * k)
                    res = simulate(policy, pop, loss, k=k, c=min(240, n_addrs),
                                   r=0.051, t=0.63, T=0.63, order_seed=k)
                    self.assertLessEqual(res.probes_sent, n_addrs * k,
                                         f"{policy} N={n_addrs} k={k}")

    def test_a_found_host_stops_being_retransmitted_to(self):
        pop = population(q_low=0.01, q_high=0.01)
        loss = independent(pop, 0.0, 3)
        for policy in (FIXED, SPLIT):
            res = simulate(policy, pop, loss, k=3, c=240, r=0.051, t=0.63, T=0.63,
                           order_seed=1, record_outcomes=True)
            for a, out in res.outcomes.items():
                self.assertEqual(out.transmissions, 1, f"{policy} addr {a}")


class Determinism(unittest.TestCase):

    def test_same_seeds_reproduce_identical_results(self):
        pop_a = population(seed=11)
        pop_b = population(seed=11)
        loss_a = independent(pop_a, 0.15, 3, seed=13)
        loss_b = independent(pop_b, 0.15, 3, seed=13)
        for policy in (FIXED, SPLIT):
            a = simulate(policy, pop_a, loss_a, k=3, c=64, r=0.051, t=0.63, T=0.63,
                         order_seed=17)
            b = simulate(policy, pop_b, loss_b, k=3, c=64, r=0.051, t=0.63, T=0.63,
                         order_seed=17)
            self.assertEqual(
                (a.sweep_seconds, a.recall, a.probes_sent, a.peak_inflight,
                 a.last_send_seconds, a.time_to_first_host),
                (b.sweep_seconds, b.recall, b.probes_sent, b.peak_inflight,
                 b.last_send_seconds, b.time_to_first_host))

    def test_the_csv_writer_is_byte_identical_across_runs(self):
        import io
        import run_sim
        first = io.StringIO()
        second = io.StringIO()
        run_sim.emit(run_sim.smoke_conditions(), first)
        run_sim.emit(run_sim.smoke_conditions(), second)
        self.assertEqual(first.getvalue(), second.getvalue())
        self.assertGreater(len(first.getvalue().splitlines()), 5)


class LossRealisation(unittest.TestCase):

    def test_both_policies_see_the_same_loss_draws(self):
        """The scratch script drew loss inside the sweep, so the two policies consumed
        the same stream in different orders and every paired comparison carried noise
        that had nothing to do with the policies.  Draws are now indexed by
        (address, transmission), which makes the pairing exact."""
        pop = population()
        loss = independent(pop, 0.2, 3)
        a = [loss.is_lost(addr, i, 0.0)
             for addr in pop.hosts for i in (1, 2, 3)]
        b = [loss.is_lost(addr, i, 999.0)
             for addr in pop.hosts for i in (1, 2, 3)]
        self.assertEqual(a, b)

    def test_bursty_loss_reproduces_its_nominal_marginal_rate(self):
        for rate in (0.05, 0.15, 0.30):
            for burst in (0.05, 0.5):
                pop = make_population(4096, 4096, 0.05, 0.05, random.Random(0))
                loss = BurstyLoss(rate, burst, list(pop.hosts), horizon=20.0, seed=1)
                rng = random.Random(2)
                lost = sum(loss.is_lost(a, 1, rng.uniform(0, 20)) for a in pop.hosts)
                observed = lost / pop.n_hosts
                self.assertLess(abs(observed - rate), 0.03,
                                f"rate={rate} burst={burst} observed={observed}")

    def test_bursty_loss_is_correlated_in_time(self):
        """Two probes 10 ms apart share a fate far more often than two 10 s apart."""
        pop = make_population(4096, 4096, 0.05, 0.05, random.Random(0))
        loss = BurstyLoss(0.15, 0.5, list(pop.hosts), horizon=60.0, seed=3)
        near = sum(loss.is_lost(a, 1, 5.0) == loss.is_lost(a, 1, 5.01)
                   for a in pop.hosts) / pop.n_hosts
        far = sum(loss.is_lost(a, 1, 5.0) == loss.is_lost(a, 1, 25.0)
                  for a in pop.hosts) / pop.n_hosts
        self.assertGreater(near, 0.97)
        self.assertLess(far, near - 0.2)


class AgreesWithTheScriptItReplaces(unittest.TestCase):
    """The strongest validation available without a testbed: configured the way the
    scratch script was configured, this simulator must reproduce the scratch script.

    Any difference from it must be attributable to a named, deliberate change, and
    both named changes are exposed as parameters — the tie-break used to order
    simultaneous timeouts, and whether a slot is freed when its reply arrives.
    """

    N, H, K, C = 254, 9, 3, 240
    Q_LOW, Q_HIGH = 0.049, 0.6

    def _orders(self, count):
        for seed in range(count):
            q = list(range(self.N))
            random.Random(seed).shuffle(q)
            yield q

    def _stub(self, order):
        class Stub:
            def shuffle(self, x):
                x[:] = list(order)

            def random(self):
                return 1.0          # scratch tests `>= loss`, so never lost
        return Stub()

    def test_reproduces_the_scratch_script_sweep_for_sweep(self):
        import types

        import sweep_sim

        T = self.Q_HIGH * 1.05
        r = self.Q_LOW * 1.05
        t = T
        scratch_pop = sweep_sim.make_population(self.N, self.H, self.Q_LOW,
                                                self.Q_HIGH, 0.0, random.Random(1000))
        pop = make_population(self.N, self.H, self.Q_LOW, self.Q_HIGH,
                              random.Random(1000))
        loss = IndependentLoss(0.0, list(pop.hosts), self.K, 1)
        real = __import__("mechanism").random
        compared = 0
        for order in self._orders(60):
            got_scratch = sweep_sim.simulate("shared", self.N, scratch_pop, self.K,
                                             self.C, r, t, T, self._stub(order))
            mech = __import__("mechanism")
            mech.random = types.SimpleNamespace(Random=lambda _s: self._stub(order))
            try:
                mine = simulate(FIXED, pop, loss, k=self.K, c=self.C, r=r, t=t, T=T,
                                order_seed=0, release_on_reply=False,
                                tie_break=ADDRESS_ORDER)
            finally:
                mech.random = real
            self.assertAlmostEqual(mine.sweep_seconds, got_scratch["time"], places=9)
            self.assertEqual(mine.probes_sent, got_scratch["probes"])
            self.assertEqual(mine.peak_inflight, got_scratch["peak_inflight"])
            compared += 1
        self.assertEqual(compared, 60)

    def test_the_two_scheduler_choices_are_what_cost_the_extra_wave(self):
        """Either fix alone removes the wasted wave; the scratch made both mistakes."""
        T = self.Q_HIGH * 1.05
        r = self.Q_LOW * 1.05
        t = T
        pop = make_population(self.N, self.H, self.Q_LOW, self.Q_HIGH,
                              random.Random(1000))
        loss = IndependentLoss(0.0, list(pop.hosts), self.K, 1)
        waves = math.ceil(self.N * self.K / self.C)
        counts = {}
        import types
        mech = __import__("mechanism")
        real = mech.random
        for tie in TIE_BREAKS:
            for release in (True, False):
                spilled = 0
                for order in self._orders(60):
                    mech.random = types.SimpleNamespace(
                        Random=lambda _s, o=order: self._stub(o))
                    try:
                        res = simulate(FIXED, pop, loss, k=self.K, c=self.C, r=r, t=t,
                                       T=T, order_seed=0, release_on_reply=release,
                                       tie_break=tie)
                    finally:
                        mech.random = real
                    self.assertIn(round(res.sweep_seconds / T), (waves, waves + 1))
                    spilled += round(res.sweep_seconds / T) > waves
                counts[(tie, release)] = spilled
        self.assertGreater(counts[(ADDRESS_ORDER, False)], 0,
                           "expected the scratch's configuration to waste waves")
        self.assertEqual(counts[(ADDRESS_ORDER, True)], 0)
        self.assertEqual(counts[(INSERTION_ORDER, True)], 0)
        self.assertEqual(counts[(INSERTION_ORDER, False)], 0)

    def test_the_default_configuration_never_wastes_a_wave(self):
        """With the defaults, the fixed policy's sweep time is exactly the wave form.
        This is a property of the mechanism, checked without consulting model.py's
        transcription of it."""
        T = self.Q_HIGH * 1.05
        r = self.Q_LOW * 1.05
        waves = math.ceil(self.N * self.K / self.C)
        for seed in range(60):
            pop = make_population(self.N, self.H, self.Q_LOW, self.Q_HIGH,
                                  random.Random(seed))
            loss = IndependentLoss(0.02, list(pop.hosts), self.K, seed)
            res = simulate(FIXED, pop, loss, k=self.K, c=self.C, r=r, t=T, T=T,
                           order_seed=seed)
            self.assertAlmostEqual(res.sweep_seconds, waves * T, places=9)


if __name__ == "__main__":
    unittest.main(verbosity=2)
