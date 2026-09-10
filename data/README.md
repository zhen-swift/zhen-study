# Simulation data

Four append-only CSV files, written by `Study/sim/` and read by `Study/analysis/`.
Nothing in `sim/` computes a statistic and nothing in `analysis/` produces evidence;
these files are the only place the two halves meet, which is what lets someone
recompute every number in the write-up without rerunning the simulation.

No file contains an aggregate. One row is one replicate, or one sweep, or one missed
host. Every mean, median, ratio, frontier and confidence interval in the analysis is
derived from these rows and none is trapped in the code that produced them.

Regenerate:

```
python3 sim/run_sim.py        # sim_results.csv          (~50 s)
python3 sim/diagnose_c3.py    # c3_*.csv                 (~35 s)
```

Both are deterministic: the same command produces byte-identical files.

---

## `sim_results.csv` — schema version 3

One row per (condition, replicate, policy). 105,488 rows over 256 conditions.
The two policies of a replicate share the same population, loss realisation and
visiting order, so any paired comparison is exact.

### Identity

| column | meaning |
|---|---|
| `schema_version` | Format version of this file; the loader refuses a file that mixes versions. |
| `experiment` | Which regime this row belongs to: `e1_dispersion`, `e2_frontier`, `e3_density`, `e3b_density_c64`, `e4_scale`, `e5_bursty`, `e6_attempts`, `e7_c3`, `e8_scheduler`, `e9_spacing`. |
| `condition_id` | The condition within that experiment; unique across the whole file. |
| `replicate` | Replicate index within the condition, from 0. |
| `policy` | `fixed` (one shared budget) or `split` (short retransmit interval, late declaration). |

### Condition parameters

Every parameter of the condition is repeated on every row, so no row needs its
condition looked up elsewhere.

| column | meaning |
|---|---|
| `n_addrs` | Addresses swept, N. |
| `n_hosts` | Live hosts among them, h. |
| `host_density` | h / N. |
| `q_low_seconds` | Fastest host's round-trip time. |
| `q_high_seconds` | Slowest host's round-trip time. |
| `dispersion` | q_high / q_low: the independent variable the theory turns on. |
| `loss_rate` | Marginal per-transmission loss probability. |
| `loss_model` | `independent` (Bernoulli per transmission), `bursty` (two-state memoryless outages, correlated in wall-clock time), or `periodic` (a duty cycle with a shared phase — the Wi-Fi power-save shape). |
| `burst_seconds` | Mean outage duration under the bursty model, or the exact outage length under the periodic one; 0 under the independent model. |
| `attempts_k` | Maximum transmissions per address, k. |
| `concurrency_c` | Probes in flight at any instant, c. |
| `retransmit_r_seconds` | Retransmission interval r; used by the split policy only. |
| `declare_t_seconds` | Declaration window t after the last transmission; used by the split policy only. |
| `fixed_budget_T_seconds` | The single shared budget T; used by the fixed policy only. |
| `release_on_reply` | 1 if a probe's slot is freed the instant its reply matches, 0 if it is held until the budget expires. |
| `tie_break` | How simultaneous events are ordered: `insertion` (the order probes were sent) or `address` (numerical address order). |
| `slot_hold` | What a concurrency slot is held for: `until_next` (until the next transmission is due) or `base` (only the base interval, so a long gap holds no slot). |
| `horizon_anchor` | Where the declaration window is measured from: `last_send` (the last transmission of any kind) or `last_tight_send` (the last transmission that was not deliberately delayed). |
| `spacing_policy` | How the k transmissions are spaced: `uniform` (every gap is the retransmit interval) or `spread_into_tail` (the final gap is widened). |
| `spread_seconds` | The nominal gap before the final transmission; 0 under `uniform`. |
| `spacing_jitter` | Per-host scatter applied to that gap, as a fraction of it. |
| `reply_allowance_seconds` | What the deliberately-late transmission is given to be answered, under `last_tight_send` anchoring. |
| `waves_expected` | ceil(N·k/c): how many rounds of c probes the sweep needs. |

### Seeds

Everything needed to replay this exact row. Seeds are derived from the *experiment*
name, not the condition, so all conditions in an experiment share a replicate's draws.

| column | meaning |
|---|---|
| `pop_seed` | Seeds the choice of which addresses are live. |
| `loss_seed` | Seeds the loss realisation. |
| `order_seed` | Seeds the order addresses are visited in. |

### Outcomes

| column | meaning |
|---|---|
| `sweep_seconds` | Wall-clock length of the sweep: when the last slot closed, or for the split policy the declaration horizon if that is later. |
| `recall` | hosts_found / hosts_total for this sweep. |
| `hosts_found` | Live hosts discovered. |
| `hosts_total` | Live hosts present; equals `n_hosts`. |
| `probes_sent` | Total transmissions; never exceeds n_addrs × k. |
| `peak_inflight` | Largest number of probes simultaneously in flight; never exceeds c. |
| `last_send_seconds` | Instant of the final transmission of the sweep. |
| `horizon_seconds` | Last instant at which a reply was still matchable. |
| `time_to_first_host_seconds` | When the first host was discovered; empty if none was. |
| `waves_observed` | Distinct instants at which any probe was transmitted. |

### Predictions and residuals

Functions of the condition's parameters alone, evaluated per row so a residual can be
taken without re-deriving the condition. They are predictions, not statistics.

| column | meaning |
|---|---|
| `recall_bound` | 1 − loss^k: the ceiling under independent loss. Not a bound under the bursty model. |
| `model_naive_seconds` | THEORY.md sections 4 and 5 as written: ((N−h)·k·T)/c for fixed, ((N−h)·k·r)/c + t for split. |
| `model_wave_seconds` | Correction C1's wave form: ceil(N·k/c)·T for fixed, ceil(N·k/c)·r + t for split. |
| `model_wave_last_seconds` | The wave form with the final retransmission interval removed: identical for fixed, (ceil(N·k/c) − 1)·r + t for split. |
| `residual_naive_seconds` | `sweep_seconds` − `model_naive_seconds`. |
| `residual_wave_seconds` | `sweep_seconds` − `model_wave_seconds`. |
| `residual_wave_last_seconds` | `sweep_seconds` − `model_wave_last_seconds`. |
| `residual_naive_ratio` | `sweep_seconds` / `model_naive_seconds`. |
| `residual_wave_ratio` | `sweep_seconds` / `model_wave_seconds`. |
| `residual_wave_last_ratio` | `sweep_seconds` / `model_wave_last_seconds`. |

---

## `c3_runs.csv` — schema version 1

One row per sweep in the correction-C3 diagnosis: 40,000 sweeps over two slot-release
rules, two policies, five budgets and 2,000 replicates.

| column | meaning |
|---|---|
| `schema_version` | Format version of this file. |
| `arm` | `new_release` (slot freed on reply) or `new_hold` (slot held to the budget). |
| `policy` | `fixed` or `split`. |
| `release_on_reply` | 1 or 0, matching the arm. |
| `budget_seconds` | T for the fixed arm, t for the split arm. |
| `replicate` | Replicate index, from 0. |
| `hosts_found` | Live hosts discovered. |
| `hosts_total` | Live hosts present. |
| `sweep_seconds` | Wall-clock length of the sweep. |
| `last_send_seconds` | Instant of the final transmission. |
| `horizon_seconds` | Last instant at which a reply was still matchable. |
| `probes_sent` | Total transmissions. |
| `peak_inflight` | Largest number of probes simultaneously in flight. |

## `c3_misses.csv` — schema version 1

One row per live host that was *not* found, carrying why. Shares the identity columns
of `c3_runs.csv`; recall is recomputable from that file alone, so this one is pure
attribution.

| column | meaning |
|---|---|
| `addr` | The address that was missed. |
| `rtt_seconds` | That host's round-trip time. |
| `transmissions` | Probes it actually received. |
| `lost_transmissions` | How many of those the loss process dropped. |
| `rejected_arrivals` | Replies that physically arrived but were no longer matchable. |
| `first_rejected_arrival_seconds` | When the earliest such reply landed; empty if none. |
| `category` | `all_transmissions_lost`, `reply_after_last_matchable_instant`, `never_transmitted`, or `unexplained`. The last two would each be a bug. |

## `c3_scratch_runs.csv` — schema version 1

The unmodified scratch script's own runs, at its original 60 replicates and at 2,000,
so the difference between the two is in the data rather than asserted in prose.

| column | meaning |
|---|---|
| `arm` | `scratch_as_written` (60 replicates) or `scratch_more_reps` (2,000). |
| `policy` | `shared` or `split`, the scratch script's own names. |
| `budget_seconds` | T for the shared arm, t for the split arm. |
| `replicate` | Replicate index, from 0. |
| `hosts_found` | Live hosts discovered. |
| `hosts_total` | Live hosts present. |
| `sweep_seconds` | Wall-clock length of the sweep as the scratch script reports it. |
