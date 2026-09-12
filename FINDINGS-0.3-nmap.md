# 0.3 — Characterising nmap, the baseline

Nothing here is evidence for or against a hypothesis. It is a description of the
comparator, taken before any collection, so that the matched configuration in
`PROTOCOL.md` section 2 compares what it says it compares.

**Gate status: partially met, unchanged as of 2026-09-12.** The unprivileged half is
established, from three independent sources, one of which settles the ICMP question the
gate cares most about without a packet capture. The privileged half could not be run and
no capture could be taken, both for the same reason: `sudo` on this machine requires a
password and I cannot supply one. Three attempts are recorded, on 2026-09-06,
2026-09-08 and 2026-09-12, each in its own dated section, and all three refused
identically. What is missing is listed precisely at the end, and it is still one thing
rather than two.

The last section counts what the refusal costs: five of the fourteen conditions, H3
entirely, H6 entirely, and — through `tcpdump` rather than through either scanner —
the capture that every one of the fourteen needs.

---

## Versions and provenance, for the reproducibility appendix

```
$ nmap --version
Nmap version 7.991 ( https://nmap.org )
Platform: arm-apple-darwin25.6.0
Compiled with: nmap-liblua-5.4.8 openssl-3.6.3 libssh2-1.11.1 libz-1.2.12
               libpcre2-10.47 nmap-libpcap-1.10.6 nmap-libdnet-1.18.0 ipv6
Compiled without:
Available nsock engines: kqueue poll select
```

| | |
|---|---|
| install method | Homebrew, `homebrew/core` tap, poured from bottle (not built from source) |
| installed | 2026-08-30 17:31 local, receipt timestamp 1788132697 |
| path | `/opt/homebrew/bin/nmap` → `../Cellar/nmap/7.991/bin/nmap` |
| binary | Mach-O 64-bit arm64 |
| sha256 | `b522bd2f0ae39f389fcaa0263c8170938b6c4e33f9fda8c849934a05ea0b2f62` |
| host | macOS 26.6.2 build 25G83, Mac16,8, Apple M4 Pro |

It was already installed when this task began; it was not installed by me and no flags
were chosen. Recorded rather than reinstalled, because reinstalling would have changed
the thing being characterised.

## `nmap -sn` unprivileged: what it actually does

`nmap -sn 10.10.20.0/24` as a normal user runs and parses. XML and greppable output
both decode; the run stats block is intact.

**It sends TCP connect probes to ports 80 and 443, and nothing else.**

Two independent sources agree, which matters because one of them is nmap describing
itself:

*From nmap's own `--packet-trace`* — every probe line is a `CONN`, which is the
`connect()` path rather than a raw socket:

```
CONN (0.0016s) TCP localhost > 10.10.20.4:80  => Operation now in progress
CONN (0.0016s) TCP localhost > 10.10.20.1:80  => Operation now in progress
CONN (0.0017s) TCP localhost > 10.10.20.4:443 => Operation now in progress
CONN (0.0017s) TCP localhost > 10.10.20.1:443 => Operation now in progress
CONN (0.0102s) TCP localhost > 10.10.20.1:80  => Connected
```

*From the kernel's socket table, which is not nmap talking* — sampling
`netstat -an -p tcp` for `SYN_SENT` every 150 ms across a full `/24` sweep:

| destination port | observations |
|---|---|
| 80 | 232 |
| 443 | 69 |
| anything else | 0 |

301 observations, two ports. No ARP, no ICMP echo, no other TCP port.

The discovery reason nmap records for the one host it found is `syn-ack` — a TCP
handshake, not an ICMP echo reply.

**So the fallback H3 assumes is real on this build, and is narrower than "a small port
set": it is exactly two ports.**

## The ICMP question, settled without a capture

The two sources above establish what unprivileged nmap sends over TCP. They are silent
on the question the gate actually turns on: whether it emits any ICMP *as well*. A
capture would answer it directly and there is no unprivileged path to one on this
machine. There is, however, a third observer that answers a strictly stronger version
of the question, and it is the kernel rather than nmap.

**A process cannot send ICMP without holding a socket that can.** `lsof` lists the file
descriptors of a running process from the kernel's own tables, so sampling nmap's
descriptors across a sweep asks not "did an ICMP packet appear on the wire" but "was
nmap ever in a position to put one there".

*The positive control, which is what makes a negative result mean anything.* `/sbin/ping`
on this machine is mode `-r-xr-xr-x` — **no setuid bit** — so it runs with exactly the
privileges this account has. During `ping -c 5 10.10.20.1`, `lsof` reports:

```
ping    70104   jc    3u  IPv4 0x551d4f1af01a5521   0t0   ICMP *:*
```

Two things follow, and both are needed. `lsof` does report ICMP sockets when they
exist, so it is a working instrument. And an unprivileged process on macOS 26 *can*
open one — macOS grants `SOCK_DGRAM`/`IPPROTO_ICMP` without root, the same as Linux.
So if unprivileged nmap holds no ICMP socket, that is a choice its build made and not
a permission the system withheld.

*The measurement.* `nmap -sn 10.10.20.0/24`, descriptors sampled continuously for the
life of the process — **948 samples across a 20.61 s sweep**, roughly one every 22 ms,
yielding 4,548 observations of an IPv4 socket:

| socket | observations |
|---|---|
| TCP → :80 | 2,289 |
| TCP → :443 | 2,166 |
| TCP, unbound (`*:*`) | 45 |
| UDP → :53 | 46 |
| **ICMP, any** | **0** |
| **raw, any** | **0** |
| **`/dev/bpf*`, any** | **0** |

The only character device nmap opened for the whole run was `/dev/null`.

The UDP port 53 sockets are the resolver: `nmap -sn` reverse-resolves the address it
found. They are not a probe and should not be counted as one.

**Unprivileged nmap on this build never opens a socket capable of sending ICMP, never
opens a raw socket, and never opens a BPF device.** It therefore cannot emit ICMP and
cannot emit or observe ARP, which is the mechanism behind the recall gap below. The
`--packet-trace` output showing no ICMP is now corroborated by an observer that is not
nmap.

*Where this is weaker than a capture, stated plainly.* A socket opened and closed
entirely inside a 22 ms gap between samples would be missed. That is not a real
concern for a scan phase — nmap's ping sockets persist across the sweep the way ping's
did in the control, and 45 of the observations are of an unbound TCP socket held open
throughout — but it is the residual, and only a capture removes it. A capture would
also see frames this cannot: anything the kernel emits on nmap's behalf rather than
through a descriptor nmap holds. Neither residual is load-bearing for H3, which is a
claim about what nmap *probes with*.

## What that costs it, measured

Three interleaved runs each against `10.10.20.0/24`, wall clock measured around the
process:

| | run 1 | run 2 | run 3 | hosts found |
|---|---|---|---|---|
| `netsanity scan --discovery-only` | 0.71 s | 0.37 s | 0.43 s | 11, 11, 11 |
| `nmap -sn` unprivileged | 20.98 s | 12.61 s | 3.61 s | 1, 1, 1 |

The one host unprivileged nmap finds is `10.10.20.1`, the gateway — the only address on
this network with a web server on it. The ten it misses are every other host netsanity
sees:

```
10.10.20.2  10.10.20.3  10.10.20.8  10.10.20.50 10.10.20.51
10.10.20.52 10.10.20.54 10.10.20.57 10.10.20.59 10.10.20.60
```

nmap found nothing netsanity did not.

These are diagnostics, not results. They are one network, three runs, no blocking, no
randomised interleaving, and the comparison is not yet the matched one — but the size
of the gap is worth knowing before designing around it. Note also nmap's wall clock
spread: 3.6 s to 21.0 s across three consecutive runs of an identical command, a factor
of six. Whatever the pilot in 0.6 concludes about variance, nmap's is large and the
block count will have to absorb it.

## A finding about H3, not about nmap

`PROTOCOL.md` H3 and `THEORY.md` P6 do not say the same thing, and the measurement
makes the difference consequential.

> **H3.** Unprivileged netsanity achieves recall statistically indistinguishable from
> privileged netsanity **and from unprivileged `nmap -sn`** […]

> **P6.** Unprivileged netsanity recall ≈ privileged netsanity recall, **while
> unprivileged `nmap -sn` recall falls below both** for hosts answering ICMP but no
> probed TCP port.

P6 is what the mechanism predicts and what was observed: 11 against 1. H3's clause
asking for netsanity to be *indistinguishable from* unprivileged nmap asks for the
opposite, and on this network it is false by a factor of eleven — not marginally, and
not in a way more data will change.

H3's stated refutation condition is "refuted if unprivileged recall is significantly
below either comparator", which reads as being about *netsanity's* recall and is not
triggered. So the defect is in the hypothesis statement rather than in the claim
underneath it: the sentence says "indistinguishable from" where the whole point of the
privilege argument is that nmap is *worse*. As written, H3 is refuted by the very
result it is meant to demonstrate.

This wants an amendment before collection, not a reinterpretation afterwards. It is
recorded here and not acted on: editing a frozen protocol is not mine to do.

A second thing for whoever writes that amendment. Unprivileged nmap's weakness here is
not only the TCP fallback — it is that it cannot ARP. A privileged `nmap -sn` on a
local segment uses ARP and will find every host that has a MAC, which is all of them.
The privileged/unprivileged gap for nmap on a *local* network is therefore close to
total, and much larger than it would be across a router. The study is a local-network
study, so this is the regime it will be measuring in, and the paper should say which of
the two mechanisms it is attributing the gap to.

## What could not be verified, and exactly what is needed

One thing is missing, not two.

**`sudo nmap -sn` was not run.** `sudo` requires a password on this machine and I have
none: `sudo -n true` returns *"a password is required"*. Untested, therefore: that the
privileged invocation runs, that its output parses, and the ARP behaviour attributed to
it above — which is currently an inference from nmap's documented design plus the
observation that the unprivileged process opens no BPF device, not a measurement.

This is the half of the gate that remains open, and it is open on a credential rather
than on a method. `PHASE0.md` already assigns unattended root to JC and says the agent
does not touch credentials, so it stays here.

```
sudo nmap -sn 10.10.20.0/24 -oX /tmp/nmap-priv.xml --packet-trace 2>/tmp/nmap-priv.trace
```

That one command closes it: it establishes that the privileged invocation runs and
parses, and its trace shows ARP where the unprivileged trace showed `CONN`.

**No packet capture was taken, and it is no longer the blocker it was.** `/dev/bpf0` is
`crw------- root:wheel`, this account is not in `access_bpf` (the group does not exist
on this machine), and no ChmodBPF daemon is installed — so there is no unprivileged
path to a capture on macOS. What the capture was wanted for was the ICMP question, and
the descriptor evidence above answers it from the kernel with a working positive
control. The residual a capture would still remove is stated in that section and is
narrow.

If a capture is taken anyway when root is available, this is the pair:

```
sudo tcpdump -i en0 -n -w /tmp/nmap-unpriv.pcap 'host 10.10.20.8 and not port 22'
```

Run it in the background, run unprivileged `nmap -sn 10.10.20.0/24` against it, stop
it. It should show TCP SYNs to :80 and :443 and nothing else — if it shows ICMP, the
descriptor evidence above is wrong and that is worth knowing loudly.

## Provenance of the numbers in this document

Every count in the descriptor table is recomputable from the sampling loop:

```
nmap -sn 10.10.20.0/24 -oX nmap-unpriv.xml &
NP=$!; while kill -0 $NP 2>/dev/null; do lsof -nP -p $NP | awk 'NR>1'; done > lsof-nmap.txt
awk '$5 ~ /IPv4/ {print $8, $9}' lsof-nmap.txt | sort | uniq -c | sort -rn
```

Run 2026-09-06 against `10.10.20.0/24` from `10.10.20.8`, nmap 7.991, macOS 26.6.2
build 25G83. The sweep found one host up, `10.10.20.1`, reason `syn-ack`.


---

## 2026-09-08: a second attempt at the privileged half, and one new unprivileged run

### The privileged invocation was attempted and refused

The plan for this round was that a `sudo -v` immediately beforehand would leave a valid
timestamp, so the one command that closes the gate would simply run. It did not. Run at
the start of the session, before anything else, so the timestamp would be as fresh as it
was ever going to be:

```
$ sudo -n nmap -sn 10.10.20.0/24 -oX /tmp/nmap-priv.xml --packet-trace \
      2>/tmp/nmap-priv.trace
exit 1

$ cat /tmp/nmap-priv.trace
sudo: a password is required

$ ls /tmp/nmap-priv.xml
ls: /tmp/nmap-priv.xml: No such file or directory
```

`-n` is what makes this a clean negative rather than a hang: sudo fails immediately
instead of prompting. No XML was produced, so there is nothing to parse and nothing to
report about ARP.

The paired capture — `sudo -n tcpdump -i en0 -w /tmp/nmap-unpriv.pcap` with an
unprivileged sweep under it — was not attempted, because it needs the same thing and
would have failed the same way. `/dev/bpf*` is `crw------- root:wheel`, there is no
`access_bpf` group on this machine, and no ChmodBPF daemon is installed.

No further attempt was made, and none should be read into this document. Supplying,
reading around, or working around a password is outside what an agent does here, and
the failure is a credential boundary rather than a methodological one.

**So both open items are open for exactly the reason they were open before, and the two
commands that close them are unchanged.** They are listed verbatim at the end of the
previous section.

### One new unprivileged run, which was free

The harness's nmap XML parser had to be verified against real output rather than against
a fixture, so one unprivileged sweep was run under the exact argv the condition matrix
uses:

```
nmap -sn 10.10.20.0/24 -oX ... --reason -T3
```

| | |
|---|---|
| wall clock (nmap's own `<finished elapsed>`) | 21.96 s |
| hosts up | 1 — `10.10.20.1` |
| discovery reason | `syn-ack` |
| XML `exit` | `success` |

Consistent with the three runs above in every respect, and it is a fourth independent
observation of the variance. The four together — 3.61, 12.61, 20.98, 21.96 s — give a
standard deviation of 8.55 s on a mean of 14.79 s, a coefficient of variation of 0.58,
and a 95% interval on σ of **[4.8 s, 31.9 s]**: still a factor of seven, because four
samples buy very little. What that implies for the block count is computed in
`harness/run_block.py --sizing` and summarised in `FINDINGS-0.5-harness.md`; the short
version is that the protocol's n ≥ 30 per stratum is adequate for the hypothesis tests
and thin for a publishable interval around nmap's median.

`--reason` is now part of the matched nmap argv for a reason this document motivated:
the per-host discovery reason is how the privileged and unprivileged conditions are told
apart from the evidence rather than from the command line — `arp-response` where the
segment is local and root was held, `syn-ack` where it was not. When the privileged half
is finally run, that field is the measurement the ARP claim needs.

### The H3 defect has been amended

The contradiction between H3 and P6 recorded above was acted on on 2026-09-08.
`PROTOCOL.md` section 12 now carries an additive amendment that splits H3 into a parity
claim between privileged and unprivileged **netsanity**, and a new **H6** covering the
privilege gap against nmap with its own refutation condition and a pre-declared testbed
composition. Section 1 is untouched, deliberately. The scope note this document asked
for — that nmap's privilege gap is near-total on a local segment because it cannot ARP,
and much smaller across a router, so the claim is local-segment only and the abstract
must say so — is part of that amendment.

---

## 2026-09-12: a third attempt, now with the netsanity half and the capture

Attempted on the day the measured binary was frozen
(`study/binary-2026-09-12`, `REPRODUCIBILITY.md`), because the freeze is the last
thing that could be done without root and this gate is now the only thing between the
apparatus and a pilot. Three invocations, run in this order, nothing else in between.

**1. nmap, privileged.** The argv the condition matrix uses, against the programmable
segment rather than the home LAN, since the programmable segment is the primary
testbed:

```
$ sudo -n nmap -sn 192.168.64.0/24 -oX /tmp/nmap-priv.xml --reason -T3
sudo: a password is required
exit 1
```

**2. netsanity, privileged.** Never attempted before this date. It carries the
`env NETSANITY_HISTORY=` prefix that the 2026-09-11 amendment requires, written into
the argv rather than inherited, precisely because `sudo -n` resets the environment:

```
$ sudo -n env NETSANITY_HISTORY=/tmp/gate03-priv.ndjson \
      .../InfinityCastle-collection/Packages/netsanity-cli/.build/release/netsanity \
      scan 192.168.64.0/24 --discovery-only --json
sudo: a password is required
exit 1
```

**3. tcpdump.** Not a scan, just an enumeration of interfaces — the cheapest possible
test of whether a capture could be started at all:

```
$ sudo -n tcpdump -D
sudo: a password is required
exit 1
```

No file was created by any of the three. `/tmp/nmap-priv.xml` and
`/tmp/gate03-priv.ndjson` do not exist, and `tcpdump -D` wrote zero bytes to stdout.
So there is nothing to parse, nothing to report about ARP, and no capture.

### What this blocks, counted

The condition matrix is fourteen conditions, all fourteen now expressible — the two
that were `BLOCKED` on missing flags were unblocked on 2026-09-09. **Five of the
fourteen need root and none of the five can run:**

| condition | serves |
|---|---|
| `ns.disc.priv` | H3 |
| `nmap.sn.priv.T2` | H1, H2 |
| `nmap.sn.priv.T3` | H1, H2 |
| `nmap.sn.priv.T4` | H1, H2 |
| `nmap.sn.priv.T5` | H1, H2 |

**H3 is blocked entirely.** It is a paired comparison of privileged against
unprivileged netsanity in the same block, and one half of the pair does not run.

**H6 is blocked too, and less obviously.** Every condition H6 names is unprivileged, so
it looks runnable. It is not: H6 claims losing root costs nmap more recall than it
costs netsanity, and a privilege gap cannot be measured from one side of it. Without
`nmap.sn.priv.*` there is no privileged nmap recall to subtract from, and the
refutation condition — a gap of at least 0.25 — has nothing to be a gap in.

H1, H2, H4 and H5 could in principle be measured from the unprivileged conditions
alone. That is not an argument for starting: `run_block.py` treats a refused `sudo -n`
as a halt rather than a per-run exclusion, deliberately, because a study that quietly
drops five of its fourteen conditions overnight is worse than one that stops. The
reasoning is in `FINDINGS-0.5-harness.md`, under what stops a live block.

**The capture is blocked, and it is not only 0.3's problem.** `capture.py` runs
`tcpdump` per run, and a run without its capture is not evidence — the passive capture
is the oracle that separates a scanner miss from a sleeping device, which is the oracle
that decides recall. So the same refusal that blocks the five privileged conditions
also blocks all fourteen. Whatever arrangement is made for root has to cover `tcpdump`
and the neighbour-table flush, not only the two scanners.

### What unblocks it

Unchanged from 2026-09-06 and from 2026-09-08, and it is JC's, not the agent's.
`PHASE0.md` assigns unattended root under its two outstanding decisions and
`HARNESS.md` repeats it: either a root-owned launchd job for the privileged
conditions, or a sudoers entry scoped to exactly these binaries for the duration and
removed afterwards. Either way it goes in the reproducibility appendix, because it is
part of the method.

Three binaries need to be reachable, not one: `nmap`, the frozen `netsanity` at the
path in `frozen-binary.json`, and `tcpdump` — plus `arp` for the per-block cache flush.

No fourth attempt should be read into this document, and none was made. The boundary is
a credential and not a method, and it is the same boundary it was six days ago.
