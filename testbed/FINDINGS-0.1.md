# 0.1 — Feasibility of the programmable segment

Nothing here is evidence. Every number is a diagnostic about an instrument, taken
before any hypothesis was touched.

The question was whether a chosen round-trip time and loss rate can be imposed on a
chosen address, repeatably, with real ICMP and a distinct hardware address per
responder, on this hardware. It can, with one constraint that shapes everything after
it.

---

## What was built

A vmnet segment at `192.168.64.0/24`, with the scanning Mac on it at `192.168.64.1`
via `bridge100`, and ten shaped responders on it at `.4` through `.13`.

Each responder is a network device in its own Linux network namespace inside a small
Ubuntu virtual machine, with `netem` on its egress applying that responder's delay.
The delay is imposed at the host that answers, which is what a genuinely slow device
does, and it needs nothing from macOS: no `pf`, no `dnctl`, no root on the Mac.

```
plan.py            the ten responders and their targets, as data
lima-responder.yaml one machine, two vmnet ports
netbed.py          up / configure / inventory
verify_gate.py     the gate, measured from the Mac and nowhere else
manifest.json      what the instrument actually is, written by `configure`
gate-0.1.json      what it did, written by `verify_gate.py`
```

## The constraint that shapes the design: two responders per machine

Not a preference. Two measurements, in this order:

**`vmnet` filters by source hardware address.** A guest with a macvlan child bearing
`02:00:5e:00:00:01` transmits ARP on the wire — confirmed with `tcpdump` inside the
guest, three requests leaving `lima0` with that source address — and the Mac never
answers. The Mac's neighbour entry for that address stays `(incomplete)`, and the
namespace cannot reach the Mac either. One port carries exactly one hardware address.

**Apple's Virtualization framework caps network devices per machine.** Bisected: 8, 6
and 4 vmnet devices are all refused with

> `VZErrorDomain Code=2 "Invalid virtual machine configuration. The number of network
> devices is greater than the maximum number supported."`

and 2 is accepted. lima adds one device of its own for transport, so the ceiling is
three devices, of which two can be responders.

Ten responders therefore need five machines. A testbed at the scale of a realistic /24
— twenty or thirty hosts — would need ten to fifteen, and that is the number to plan
around rather than discover in week two.

## Why not the alternatives

**Bridged onto `en0`.** That interface is Wi-Fi. 802.11 gives a station no
four-address mode, so a guest's frames bearing its own source address are dropped by
the driver or the access point; and the segment's own latency was measured at
152–305 ms in an earlier phase, which is larger than four of the five delays this
testbed exists to impose. Both reasons are independently fatal.

**`dnctl` and `pf` on the Mac.** Both binaries are present on macOS 26.6.2. Not
attempted, and it would not have helped: it shapes what the scanner sees rather than
what the device does, it needs root on the scanning host, and it supplies no hardware
addresses at all — the ten distinct MACs the gate asks for have to come from ten real
responders however the delay is applied.

## Two configuration facts that had to be measured

**The guests must be kept out of deep idle.** With the guest idle, the round trip from
the Mac has a median of 0.87 ms, a standard deviation of 1.0 ms and a p99 of 8.3 ms.
With one core kept busy, the median falls to **0.33 ms** and the deviation to 0.4. The
idle-exit path is roughly half a millisecond of jitter — larger than the smallest delay
this segment exists to impose, so without this the 1 ms responder is not merely noisy,
it is unmeasurable. Four spinners on four cores is *worse* than one, because the
softirq that answers the probe then competes for a core. It is one spinner per machine,
as a `systemd-run` transient unit.

**Open-loop shaping overshoots, so the responders are calibrated.** Setting `netem` to
(target − baseline) and trusting it gives +16.1% at a 1 ms target and +22.6% at 5 ms.
The overshoot is the virtio and vmnet path plus netem's own timer; it is not constant
and there is no reason to model it when it can be measured away. `configure` closes the
loop, adjusting `netem` until the measured median sits within 2% of target, and records
both the value it arrived at and the round trip that resulted. Convergence, measured:

| target | rounds | final `netem` | measured p50 | error |
|---|---|---|---|---|
| 1 ms | 1–2 | 0.702–0.732 ms | 0.997 / 1.019 ms | −0.30% / +1.90% |
| 5 ms | 3 | 3.805–3.816 ms | 5.051 / 5.076 ms | +1.02% / +1.52% |
| 25 ms | 1 | 24.643 ms | 24.998 / 24.975 ms | −0.01% / −0.10% |
| 100 ms | 1 | 99.659 ms | 100.061 / 100.048 ms | +0.06% / +0.05% |
| 500 ms | 1 | 499.681 ms | 500.019 / 499.986 ms | +0.00% / −0.00% |

Calibration is instrument calibration, not fitting: the manifest records the target and
the achieved value side by side, and every later stage of the study reads the achieved
column.

## The gate

Ten addresses, five delays from 1 ms to 500 ms, each within 10% of configuration on
three consecutive runs, with a distinct hardware address for each in the neighbour
table.

Measured medians, three consecutive runs, thirty probes per address per run
(`gate-0.1.json`):

| responder | target | run 1 | run 2 | run 3 |
|---|---|---|---|---|
| r01 | 1 ms | −1.20% | +0.40% | +0.70% |
| r02 | 1 ms | −0.50% | +2.80% | +5.00% |
| r03 | 5 ms | +1.72% | +1.56% | +1.54% |
| r04 | 5 ms | +1.28% | +0.94% | +1.22% |
| r05 | 25 ms | −0.23% | −0.21% | −0.27% |
| r06 | 25 ms | −0.19% | −0.20% | −0.14% |
| r07 | 100 ms | −0.06% | −0.04% | −0.06% |
| r08 | 100 ms | −0.07% | −0.06% | −0.05% |
| r09 | 500 ms | −0.02% | +0.01% | +0.00% |
| r10 | 500 ms | −0.02% | +0.01% | +0.00% |

Worst error across all three runs and all ten addresses: **+5.00%**, against a 10%
tolerance, and it is a 1 ms responder. Ten distinct hardware addresses, all agreeing
with what the guests report.

**GATE 0.1 MET.**

An earlier pass at fifty probes per address gave the same picture with a worst error of
+6.90%, also on a 1 ms responder. It is recorded here rather than discarded because it
is the run in which the hardware-address comparison bug was caught, and because two
independent passes agreeing is worth more than one.

## What is weakest, and should be said in the paper

**The 1 ms point is the median of a distribution whose spread is comparable to its
value.** At a 1 ms target the standard deviation across probes is 0.5–1.3 ms and the
p90 reaches 1.2 ms. The median lands within 10% on every run, which is what the gate
asks, but individual probes do not: this segment can place a responder's *typical*
latency at 1 ms and cannot make every probe arrive at 1 ms. Everything at 5 ms and
above is tight — p10 to p90 spans under 0.7 ms at 25, 100 and 500 ms.

For P1, which stratifies by dispersion, that matters at one end only: a dispersion of
500 built from 1 ms and 500 ms responders has a well-controlled numerator and a noisy
denominator, and the reported dispersion should be computed from measured medians
rather than from configured targets.

**The `pkill` and `arp` defects were found here rather than in collection.** Two
mistakes in this apparatus produced convincing wrong answers before being caught: a
`pkill -f netbed-spin` that matched the command line of the shell running it and killed
the session installing the spinner, and a hardware-address comparison that failed on
three of ten correctly-configured responders because macOS `arp` prints
`52:55:55:d:3b:4a` where Linux prints `52:55:55:0d:3b:4a`. Both are recorded in the
code at the point they bite.

## What was not verified

- **Loss.** `plan.py` carries a `loss_percent` per responder and `netbed.py` applies it
  through `netem loss`, but every responder in this run is at 0% and no loss rate has
  been measured against its configuration. The gate did not ask for it; 0.4 will.
- **Stability over hours or days.** Everything here was measured over roughly an hour.
  Whether ten machines and a calibration hold across a seven-day window is unknown, and
  a re-calibration step before each block is the obvious insurance.
- **Behaviour under a scan rather than under `ping`.** The responders have been probed
  one address at a time. A sweep puts 254 probes in flight at once, and whether five
  virtual machines answer that burst the way they answer a serial ping is not
  established.
- **The secondary physical testbed.** Untouched. `PROTOCOL.md` section 3 still
  describes it and it remains the external-validity arm.

---

## Re-planned for H6, 2026-09-10 — gate re-met

The 2026-09-08 amendment pre-declares the segment's composition, and the segment did
not have it. Ten responders that all answered ICMP and served nothing would have made
H6 unfalsifiable in the wrong direction: unprivileged nmap would find zero, the gap
would be 1.0, and the 0.25 threshold could not fail however weak the mechanism was. A
threshold derived from a composition the instrument does not have is not a threshold.

**The composition now.**

| role | count | responders |
|---|---|---|
| answers ICMP and serves 80 or 443 | 3 | r01, r03, r05 |
| answers ICMP only | 5 | r02, r04, r07, r09, r10 |
| ICMP filtered, serves 80 | 1 | r06 |
| answers neither | 1 | r08 |

Three of ten is above the declared quarter. `r06` is section 3's "host answering only
on TCP/80" and is the one host unprivileged nmap finds that an ICMP sweep does not —
without it H6 is a claim nothing on the segment can contradict. `r08` answers nothing
at either layer and is present only in ARP, which is what gives H3's
privileged-versus-unprivileged comparison something to be about. `r10` carries 15% loss
as the sleeping host, which is the host correction C8 is about.

ICMP is switched off with the responder's own namespace `icmp_echo_ignore_all` rather
than a firewall rule. One line, per namespace, and it leaves the host otherwise entirely
normal — it still answers ARP, which is precisely why a privileged scan finds it.

**Order matters, and getting it wrong cost a gate run.** The first attempt started the
TCP listeners after calibrating each responder's delay. A listener is a process, and a
process changes how idle the machine is — the same lever the CPU spinner pulls, for the
same reason. Calibrated quiet and then run busy, the 25 ms responder came out at
22.3 ms, and the gate failed on three responders for a reason that had nothing to do
with shaping. Listeners now start before anything is measured, including the baseline.
The ICMP filter goes on in the opposite order, after calibration, because calibration
measures delay by pinging and a filtered host cannot be pinged.

**A filtered host still has a delay, and it is still verified.** netem is on the
interface, so it delays that host's TCP handshakes exactly as much as it would have
delayed its pings. `verify_gate.py` measures `r06` by timing a TCP connect instead of a
ping. `r08` answers nothing and is recorded as unmeasurable rather than as a failure:
its delay is imposed and cannot be checked by any active probe, which is acceptable
because nothing in the study measures a round trip to a host that never answers one.

**Gate 0.1 re-met on the new composition.** Worst error 2.50% across three runs and ten
addresses against a 10% tolerance — better than the 5.0% the original composition
managed, because everything is now calibrated under the load it is measured under. Ten
distinct hardware addresses, all agreeing between the guest and the Mac's neighbour
table. The gate now also fails if a responder's ICMP state disagrees with the plan, or
if the declared quarter is not met: a segment that quietly stops being the pre-declared
one invalidates every number derived from that declaration, and nothing else would
notice.
