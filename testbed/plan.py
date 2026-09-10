"""The programmable segment, expressed once, as data.

Ten responders across five target round-trip times spanning three orders of magnitude.
Two responders per virtual machine, which is not a taste: Apple's Virtualization
framework refuses a configuration with more than three network devices, one of which
lima uses for its own transport, and `vmnet` drops any frame whose source hardware
address is not the one it assigned to the port. So a responder needs a port, a port
needs a device, and a machine holds two. See `FINDINGS-0.1.md` for the measurements.

Nothing here is a hypothesis and no number in it is evidence. It is the composition of
an instrument, and `manifest.json` records what the instrument actually did rather than
what this file asked for.
"""

from __future__ import annotations

from dataclasses import dataclass

# Responders per virtual machine. Bounded by the framework, not chosen.
RESPONDERS_PER_VM = 2

# The vmnet shared segment the Mac is bridged onto. Discovered rather than configured;
# recorded here so a reader can see what the addresses in the manifest belong to.
SEGMENT = "192.168.64.0/24"


@dataclass(frozen=True)
class Responder:
    """One shaped address."""

    name: str
    #: Target round-trip time in milliseconds, as measured from the scanning Mac.
    #: What netem is actually set to is derived by calibration and differs from this.
    target_rtt_ms: float
    #: Per-probe loss applied to the REPLY path, as a percentage. Losing the reply and
    #: losing the request are the same event to a discovery scan, and netem shapes
    #: egress, so this is the honest description of what is imposed.
    loss_percent: float = 0.0
    #: Whether the host answers an ICMP echo request at all.
    #:
    #: Section 3 requires a host with ICMP filtered, and H6 turns on the difference
    #: between what ICMP reaches and what a TCP connect scan reaches. Imposed with the
    #: namespace's own `icmp_echo_ignore_all`, so the host is otherwise entirely normal
    #: — it still answers ARP, which is what a privileged scan would find it by.
    answers_icmp: bool = True
    #: TCP ports the responder accepts a connection on.
    #:
    #: Unprivileged nmap probes exactly 80 and 443, measured in 0.3. A responder serving
    #: neither is invisible to it; one serving either is not. That is the whole
    #: mechanism H6 predicts, so it is expressed here as data rather than left to what
    #: an image happens to have running.
    tcp_ports: tuple[int, ...] = ()

    @property
    def role(self):
        """How this responder reads in a composition table."""
        if self.answers_icmp and self.tcp_ports:
            return "icmp+web"
        if self.answers_icmp:
            return "icmp-only"
        if self.tcp_ports:
            return "tcp-only"
        return "silent"


# Five delays spanning 1 ms to 500 ms — a dispersion of 500, which is the range the
# study needs and which no physical consumer network supplies. Two responders at each
# so a single machine's scheduling cannot be mistaken for a property of the delay.
#
# ── The composition is pre-declared, and this is it ──────────────────────────────
#
# `PROTOCOL.md`'s H6 amendment fixes the testbed's composition before collection,
# because the size of the privilege gap is a property of what is on the segment rather
# than of either scanner: a segment where everything serves a web page shows no gap, and
# one where nothing does shows a gap of one. Neither is informative. The declaration is
# **at least one quarter must answer ICMP and serve port 80 or 443**, alongside the
# ICMP-filtered and TCP-only hosts section 3 already requires.
#
#   r01, r03, r05   answer ICMP and serve a port   3 of 10, so the quarter is met
#   r06             ICMP filtered, serves port 80  section 3's "TCP/80 only" host
#   r08             ICMP filtered, serves nothing  found by ARP alone, by neither scan
#   r10             answers, but sleeps            section 3's sleeping host, as loss
#
# The delay ladder is carried by the responders that answer ICMP, because a delay
# imposed on a host nothing can measure is not a point on the curve.
RESPONDERS = (
    Responder("r01", 1.0, tcp_ports=(80,)),
    Responder("r02", 1.0),
    Responder("r03", 5.0, tcp_ports=(443,)),
    Responder("r04", 5.0),
    Responder("r05", 25.0, tcp_ports=(80, 443)),
    # ICMP filtered but serving 80: the one host unprivileged nmap finds and an
    # ICMP-only sweep does not. Without it H6 is a claim nothing on the segment can
    # contradict.
    Responder("r06", 25.0, answers_icmp=False, tcp_ports=(80,)),
    Responder("r07", 100.0),
    # Answers nothing at either layer. Present in ARP, so a privileged scan finds it and
    # both unprivileged scans should not — which is what makes the privileged/
    # unprivileged comparison in H3 have something to be about.
    Responder("r08", 100.0, answers_icmp=False),
    Responder("r09", 500.0),
    # The sleeper, expressed as loss rather than as a duty cycle: netem's loss is what
    # this apparatus can impose repeatably, and correction C8 is about exactly this
    # host — the one whose three transmissions can all land inside one outage.
    Responder("r10", 500.0, loss_percent=15.0),
)

#: The fraction of responders that must answer ICMP and serve a probed port, from the
#: H6 amendment. Asserted below rather than trusted, because a composition that quietly
#: stops meeting its own declaration invalidates the threshold derived from it, and
#: nothing else in the apparatus would notice.
DECLARED_WEB_FRACTION = 0.25


def composition():
    """How many responders of each role, for the manifest and for the paper."""
    out = {}
    for responder in RESPONDERS:
        out[responder.role] = out.get(responder.role, 0) + 1
    return out


def _check_declaration():
    web = sum(1 for r in RESPONDERS if r.answers_icmp and r.tcp_ports)
    if web < DECLARED_WEB_FRACTION * len(RESPONDERS):
        raise AssertionError(
            f"composition breaks PROTOCOL.md's H6 declaration: {web} of "
            f"{len(RESPONDERS)} responders answer ICMP and serve a probed port, "
            f"and at least {DECLARED_WEB_FRACTION:.0%} must"
        )
    if not any(not r.answers_icmp for r in RESPONDERS):
        raise AssertionError("section 3 requires a host with ICMP filtered")
    if not any(not r.answers_icmp and r.tcp_ports for r in RESPONDERS):
        raise AssertionError("section 3 requires a host answering only on TCP")


_check_declaration()


def machines():
    """Responders grouped into the machines that will host them."""
    out = []
    for i in range(0, len(RESPONDERS), RESPONDERS_PER_VM):
        out.append((f"netbed{i // RESPONDERS_PER_VM + 1}",
                    RESPONDERS[i:i + RESPONDERS_PER_VM]))
    return out


#: How close a calibrated responder must sit to its target before the plan accepts it.
#: The gate in PHASE0.md asks for 10%; calibration is stopped at 2% so that the gate is
#: not being met by a tolerance chosen to meet it.
CALIBRATION_TOLERANCE_PERCENT = 2.0
CALIBRATION_ROUNDS = 4

#: Probes per calibration round. The interval between them scales with the target, so
#: that a 500 ms responder is never asked a second question before it has answered the
#: first while a 1 ms one is not measured at the pace of the slowest.
CALIBRATION_PROBES = 40


def probe_interval_seconds(target_rtt_ms):
    return max(0.1, 1.5 * target_rtt_ms / 1000.0)
