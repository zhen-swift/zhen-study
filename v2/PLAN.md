# Study 2 — the plan

Written 2026-09-29, before anything is pre-registered. This is the design argument.
`PROTOCOL-v2.md` comes after it and is the thing that gets frozen.

Study 1 is complete, honest and finished. Nothing here revises it. Study 2 exists
because study 1 answered its own question and, in doing so, paid for the knowledge
that makes this one cheap.

---

## 1. The three questions study 1 cannot answer

**Does the advantage scale with RTT dispersion?** This is the central mechanism claim.
`THEORY.md` P1 says the adaptive per-host budget wins in proportion to how widely
round-trip times are spread, and predicts **no advantage at all** when dispersion is 1.
Study 1 holds exactly one dispersion — 500× by design, 546× as measured. A claim about
a curve, measured at one point on it, is not measured. It currently rests on
`Study/sim/`.

**What does losing root cost netsanity?** H3 was withdrawn on 2026-09-12 because
`EngineKind.privilegedBPF` was declared and nothing constructed it, so both arms ran
identical code. `BPFDiscoveryEngine` now exists and the comparison is real.

**Do the two refutations survive power?** H2's and H5's refutation conditions both fire
in the cold arm, and the cold arm is about nine runs per condition — a consequence of
the 2026-09-13 ruling to keep one flush per block. They are visible and underpowered.
With a balanced cold arm they either harden into findings or dissolve, and both
outcomes are worth more than the present ambiguity.

---

## 2. What study 1 bought, and how it pays for study 2

The expensive discovery in study 1 was not a result, it was two facts about the
apparatus:

| Study 1 result | What it licenses in study 2 |
|---|---|
| Time of day had nothing on it | Drop the diurnal factor — and with it the seven-day floor |
| Unprivileged `-T2` is bimodal, 1559 s median, CV 1.09 | Stop replicating it everywhere; it is 80% of a block |

A study 2 run without study 1 first would have had to measure both again. This is the
argument for having published study 1 rather than folding it in.

---

## 3. The factor design

Three factors. Time of day is not one of them.

| Factor | Levels | Why |
|---|---|---|
| **RTT dispersion** | 4: 1×, ~5×, ~50×, ~500× | The curve. 1× is the level where the theory predicts no advantage, which is what makes the design refutable |
| **Cache state** | 2: flush per run, flush per block | The arm where both refutations live, this time with power |
| Privilege | within-block conditions | H3 revived |

**4 × 2 × 30 blocks = 240 blocks.** Thirty per cell is the floor the analysis plan
already fixes.

Dispersion level is **randomised across blocks**, never run in batches. Batching aliases
any drift — thermal, a neighbour's Wi-Fi, anything slow — onto one level. Randomising
spreads it across all four, where it becomes noise instead of a confound.

### Conditions

Twelve, plus `-T2` on a reduced schedule.

```
netsanity   disc.unpriv · disc.priv (NEW, H3) · fixed.timeout ·
            budget.shared · naming.full
nmap root   -T3 · -T4 · -T5            (+ -T2, reduced)
nmap user   -T3 · -T4 · -T5            (+ -T2, reduced)
nmap        broadcast scripts
```

`ns.disc.priv` returns as a real condition. It must report `composite` and the wire
must show ARP, verified from a capture and not from the artifact — the failure that
cost H3 the first time.

---

## 4. Why this is days rather than weeks

Study 1 was calendar-bound by a floor that existed to sample the diurnal cycle. No
diurnal factor, no floor. Study 2 is compute-bound, and one condition dominates.

| | per block |
|---|---|
| unprivileged `-T2` | 1559 s |
| privileged `-T2` | 466 s |
| everything else | ~125 s |
| cooldowns | ~130 s |

| Schedule | Block average | 240 blocks |
|---|---|---|
| Study 1 shape, run continuously | 42 min | 7 days |
| **`-T2` in one block of four** | **~13 min** | **~2.5 days** |
| `-T2` dropped entirely | ~4 min | 16 h |

**The decision: full `-T2` coverage at the 500× level, one block in four elsewhere.**
Full coverage at 500× replicates study 1's conditions exactly, which is what makes the
two studies comparable at the point they share. Elsewhere `-T2` is a comparator, not a
result, and quarter replication carries it.

No parallelism. Two scans on one segment contaminate each other's wall clock. This is
not a resource problem and more cores do not help.

---

## 5. What going fast costs, stated before it is paid

**Thermal stops being dormant.** Study 1 recorded `thermal_pressure` as no-warning for
all 1,580 runs — with idle gaps letting the machine cool between blocks. Three days at
scan duty is a different machine. Keep the covariate, and the driver pauses rather than
pushes through when it moves.

**Drift and block order.** Handled by randomising dispersion, above. It is the only
mitigation and it is free.

**One window, fewer chances to be interrupted, more cost each time.** Study 1 absorbed
eight interruptions across nine days. A 2.5-day window has fewer opportunities to be
hit and less slack when it is.

---

## 6. The gate nobody would think to ask for

**The system under test has changed.** Study 1 measured `study/binary-2026-09-12b`.
Since then: the BPF engine, SYN scanning, banner probing, stack fingerprinting,
`discovered_via`, and the `lateReplies` counter that was declared and never incremented.

Study 2 measures a different binary. That is fine for study 2's own hypotheses and it is
**not** fine for comparing study 2's netsanity numbers against study 1's, which the
dispersion curve will invite a reader to do at the 500× point.

So, before collection: **prove the unprivileged discovery path is behaviourally
unchanged between the two tags**, or declare that it is not and stop comparing. The
composite engine is supposed to be root-only and the unprivileged path untouched —
supposed to be is exactly the phrasing that cost H3.

Everything else in phase 0 is already met and is not redone. The apparatus is proven;
the pilot exists to set the cooldown and confirm the new factors, not to rediscover the
harness.

---

## 7. Hypotheses, in outline

To be written properly, with refutation conditions fixed in advance, in `PROTOCOL-v2.md`.

- **H2, restated as a curve.** Not "adaptive timing dominates" but "the advantage grows
  with dispersion, and vanishes at dispersion 1". The vanishing endpoint is the half
  that makes it refutable, and it is the half study 1 could not test.
- **H3, revived.** Unprivileged netsanity's recall against privileged netsanity's, on
  the same segment in the same block, now that the two are different code.
- **H5, with power.** The split-versus-shared budget ablation, in a cold arm that can
  resolve it.
- **H6** is answered. Study 1 refuted it at 0.10 against a 0.25 threshold, and the
  finding underneath — that the privilege gap is a time gap, not a recall gap — is
  paper 1's contribution. Study 2 carries `nmap` as a comparator, not as a hypothesis.

H2 and H5 being defended by opposite configurations in the same arm is a **design**
tension, not a sample-size one. More cold runs give it resolution; they do not dissolve
it. It stays a declared limitation in both studies.

---

## 8. Sequence

| | Work | Time |
|---|---|---|
| 1 | `PROTOCOL-v2.md` — hypotheses, refutation conditions, factor design, frozen and dated | half a day |
| 2 | Manifest variants per dispersion level, each calibrated and recorded with designed **and** achieved ratios | an afternoon |
| 3 | Harness: dispersion and cache as factors, strata removed, `-T2` schedule, thermal pause | a day |
| 4 | The unchanged-unprivileged-path gate | half a day |
| 5 | Freeze, tag, pilot | a day |
| 6 | **Collection, unattended** | **~2.5 days** |
| 7 | Analysis | 3–5 days |

Roughly two weeks to a result, most of it not requiring anyone present.

Paper 1 goes for review in parallel. The two never block each other, and if a reviewer
asks for the dispersion curve, the answer is already collecting.

---

## 9. Open, and JC's to decide

- **Dispersion levels.** 1× / 5× / 50× / 500× is a proposal. The endpoints matter more
  than the spacing: 1× because the theory predicts nothing there, 500× because it
  replicates study 1.
- **Whether `ns.disc.priv` needs its own sudoers line.** The study 1 entry names
  `nmap`, `tcpdump` and `arp`. A privileged netsanity condition needs the binary added,
  and that is a standing root capability for the duration — the same trade, made again,
  knowingly.
- **Whether study 2 is a second paper or a revision of the first.** That is a question
  for the supervisor, and it is free to ask now rather than after collection.
