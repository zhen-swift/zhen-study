"""P3: does the split policy dominate EVERY fixed budget, or only the generous ones?

Sweep T across the range a fixed template would plausibly choose, at fixed dispersion,
with enough loss that recall actually varies. Report the (time, recall) pair for each,
and ask whether any fixed point is non-dominated by the split policy.
"""
import random, statistics
from sweep_sim import make_population, simulate

rng = random.Random(20260904)
N, H, K, C = 254, 9, 3, 240
Q_LOW, Q_HIGH, LOSS = 0.049, 0.600, 0.15     # 12x dispersion, lossy Wi-Fi present
TRIALS = 60

def run(policy, T, r, t):
    ts, recs = [], []
    for i in range(TRIALS):
        pop = make_population(N, H, Q_LOW, Q_HIGH, LOSS, random.Random(1000 + i))
        out = simulate(policy, N, pop, K, C, r, t, T, random.Random(7000 + i))
        ts.append(out["time"]); recs.append(out["recall"])
    return statistics.median(ts), statistics.mean(recs)

print(f"{'policy':<22} {'budget':>9} | {'median t':>9} {'recall':>7}")
print("-" * 56)
points = []
for T in (0.05, 0.1, 0.15, 0.2, 0.3, 0.45, 0.63, 0.9, 1.3):
    t_, rec = run("shared", T, Q_LOW * 1.05, Q_HIGH * 1.05)
    points.append(("fixed", T, t_, rec))
    print(f"{'fixed budget':<22} {T*1000:8.0f}m | {t_:8.3f}s {rec:7.3f}")

print()
split_pts = []
for tail in (0.3, 0.45, 0.63, 0.9, 1.3):
    t_, rec = run("split", Q_HIGH * 1.05, Q_LOW * 1.05, tail)
    split_pts.append(("split", tail, t_, rec))
    print(f"{'split (tail)':<22} {tail*1000:8.0f}m | {t_:8.3f}s {rec:7.3f}")

print()
print("Domination check — a fixed point survives if NO split point is both")
print("faster and at least as complete:")
survivors = []
for _, T, ft, frec in points:
    dominated = any(st <= ft and srec >= frec and (st < ft or srec > frec)
                    for _, _, st, srec in split_pts)
    if not dominated:
        survivors.append((T, ft, frec))
        print(f"  NON-DOMINATED: fixed T={T*1000:.0f}ms  t={ft:.3f}s  recall={frec:.3f}")
if not survivors:
    print("  none — every fixed budget is dominated. P3 holds in simulation.")
