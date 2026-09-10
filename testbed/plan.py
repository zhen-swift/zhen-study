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


# Five delays spanning 1 ms to 500 ms — a dispersion of 500, which is the range the
# study needs and which no physical consumer network supplies. Two responders at each
# so a single machine's scheduling cannot be mistaken for a property of the delay.
RESPONDERS = (
    Responder("r01", 1.0),
    Responder("r02", 1.0),
    Responder("r03", 5.0),
    Responder("r04", 5.0),
    Responder("r05", 25.0),
    Responder("r06", 25.0),
    Responder("r07", 100.0),
    Responder("r08", 100.0),
    Responder("r09", 500.0),
    Responder("r10", 500.0),
)


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
