"""The condition matrix from PROTOCOL.md section 2, expressed once, as data.

Both the harness and the analysis import this module, so a condition cannot exist in
the data that the protocol does not describe.

This module is also where a missing CLI flag becomes visible, because a condition
cannot be written without the flag it needs.  Two of the entries below are therefore
`BLOCKED`: they name the flag they are waiting for and they are excluded from a block
until it exists.  `--discovery-only` used to be one of them; 0.2 shipped it, so the
matched discovery configuration is now built from a real flag rather than from a
comment saying one is needed.
"""

from __future__ import annotations

from dataclasses import dataclass, field

READY = "ready"
BLOCKED = "blocked"
#: Described by the protocol, kept as data, and never run again.  Distinct from
#: `BLOCKED`, which is waiting for something: a withdrawn condition is not coming back,
#: and it stays in the matrix because a reader comparing the data against the protocol
#: should be able to see what was removed and find the amendment that removed it.
WITHDRAWN = "withdrawn"


@dataclass(frozen=True)
class Condition:
    """One cell of the matched-configuration table.

    `argv_template` carries `{placeholders}` filled by `render()`.  It is a template
    rather than a built list so that the matrix stays inspectable as data: a reviewer
    can read the exact command every condition will run without executing anything.
    """

    id: str
    tool: str                       # "netsanity" | "nmap"
    privilege: str                  # "user" | "root"
    argv_template: tuple[str, ...]
    hypotheses: tuple[str, ...]
    purpose: str
    status: str = READY
    requires: str | None = None     # the flag this condition is waiting on
    #: seconds observed for this condition in 0.2 / 0.3, used only to estimate how long
    #: a block takes.  A diagnostic, never a result.
    observed_seconds: float | None = None
    notes: str = ""
    parser: str = field(default="")

    def render(self, **substitutions) -> list[str]:
        if self.status != READY:
            raise ValueError(
                f"condition {self.id} is {self.status}: it needs {self.requires!r}, "
                f"which does not exist yet"
            )
        missing = [
            token for token in self.argv_template
            if "{" in token and not all(
                key in substitutions for key in _placeholders(token)
            )
        ]
        if missing:
            raise KeyError(f"condition {self.id} needs substitutions for {missing}")
        return [token.format(**substitutions) for token in self.argv_template]


def _placeholders(token: str) -> list[str]:
    out, rest = [], token
    while "{" in rest:
        _, _, rest = rest.partition("{")
        name, _, rest = rest.partition("}")
        out.append(name.split(":")[0].split("!")[0])
    return out


# `sudo -n` throughout: the privileged conditions must fail immediately rather than sit
# on a password prompt for seven days.  How root is arranged is PHASE0's outstanding
# decision (a root-owned launchd job, or a sudoers entry scoped to these two binaries
# and removed afterwards) and it goes in the reproducibility appendix either way.
_SUDO = ("sudo", "-n")

# Every netsanity condition writes its history somewhere disposable, and the path is
# an explicit `env` assignment in the argv rather than an inherited variable.
#
# `netsanity scan` persists every run.  Left alone it appends to one file for the whole
# collection window, and `LogHistoryStore` rewrites that file once it passes a line
# threshold — so one run in N pays for a full compaction INSIDE the wall clock the
# harness is measuring, and which run pays is a function of how long collection has been
# running.  nmap persists nothing, so the conditions would also not be matched on I/O.
# A systematic, drifting, self-inflicted penalty on the tool under test is not a thing
# to discover in the analysis.
#
# One store per run, not per block: an empty store makes every run's write the same
# constant amount of work.  A per-block store would have the first run insert and the
# rest update, which is a within-block trend in exactly the quantity being measured.
#
# `env VAR=path` in the argv rather than `subprocess(env=...)` for two reasons.  The
# recorded argv is then the whole truth about what ran, which is what reproducibility
# means here; and `sudo -n` resets the environment, so an inherited variable would reach
# the unprivileged conditions and silently not reach the privileged ones — the two
# halves of H3 and H6, differing in a way no field would have recorded.  The same form
# on both sides costs one extra `exec` (order of a millisecond) that nmap does not pay,
# which biases H1 AGAINST netsanity.  That direction is the acceptable one.
_NS = ("env", "NETSANITY_HISTORY={store}",
       "{netsanity}", "scan", "--cidr", "{cidr}", "--iface", "{iface}",
       "--json", "--quiet", "--no-color")

_NMAP = ("{nmap}", "-sn", "{cidr}", "-oX", "{nmap_xml}", "--reason")


def _nmap_condition(template: str, privileged: bool) -> Condition:
    """One cell of the timing sweep.

    nmap is swept across `-T2` … `-T5` because comparing against `-T3` alone is not
    honest (PROTOCOL.md section 6): the reviewer's first question about any scanner
    benchmark is whether the comparator was left on its defaults.
    """
    priv = "priv" if privileged else "unpriv"
    argv = (_SUDO + _NMAP if privileged else _NMAP) + (f"-{template}",)
    if privileged:
        hyp: tuple[str, ...] = ("H1", "H2")
    else:
        # H6 is the privilege-gap claim added by the 2026-09-08 amendment; H3 no longer
        # takes nmap as a comparator.
        hyp = ("H1", "H2", "H6")
    return Condition(
        id=f"nmap.sn.{priv}.{template}",
        tool="nmap",
        privilege="root" if privileged else "user",
        argv_template=argv,
        hypotheses=hyp,
        purpose=f"nmap host discovery, {priv}ileged, timing template -{template}",
        parser="nmap_xml",
        # A diagnostic for sizing, never a result.  Which of these were actually run
        # matters, so: privileged T3, T4 and T5 and unprivileged T3 were measured on the
        # programmable segment on 2026-09-12 under the gate 0.3 script, one run each.
        # Privileged T2 is an extrapolation and the rest are estimates.
        #
        # Every privileged template was 3.0 here before that, which was a guess and was
        # wrong by two orders of magnitude for -T2.  That template paces itself at about
        # one probe a second, so an ARP sweep of a /24 needs roughly 510s: it was killed
        # by a watchdog at 423s having sent 425 of the 508 requests the faster templates
        # need to finish, and 510 is that rate carried forward rather than anything
        # nmap's documentation says.  The unprivileged templates other than T3 are
        # scaled from it and from 0.3's four home-LAN runs, and are the least trustworthy
        # numbers here.
        #
        # The consequence is the point: a block is about twelve minutes rather than the
        # three the old numbers implied, and 120 blocks is a day of machine time rather
        # than three hours.  Still inside the seven-day floor, which is why this is a
        # correction and not a redesign — but a matrix that cannot fit is a design error
        # and the cheapest place to catch it is while reading the matrix.
        observed_seconds=(
            {"T2": 510.0, "T3": 8.1, "T4": 8.1, "T5": 5.1}[template] if privileged
            else {"T2": 60.0, "T3": 22.2, "T4": 22.2, "T5": 12.4}[template]
        ),
        notes=(
            "Unprivileged nmap on this build sends TCP connect probes to exactly ports "
            "80 and 443 and opens no ICMP, raw or BPF descriptor (FINDINGS-0.3)."
            if not privileged else
            "Privileged nmap on a local segment uses ARP, which every host with a MAC "
            "must answer. Confirming that on this machine is the open half of gate 0.3."
        ),
    )


CONDITIONS: tuple[Condition, ...] = (
    # ── Discovery, matched workload ───────────────────────────────────────────────
    Condition(
        id="ns.disc.unpriv",
        tool="netsanity",
        privilege="user",
        argv_template=_NS + ("--discovery-only",),
        hypotheses=("H1", "H2", "H6"),
        purpose="netsanity host discovery with naming disabled, unprivileged",
        parser="netsanity_json",
        observed_seconds=0.5,
        notes=(
            "--discovery-only exists as of 0.2 and is a product flag with its own help "
            "text, not a study hack. Naming is ~85% of a default scan's wall clock on "
            "the development network, so without it H1 would charge netsanity seven "
            "times its discovery cost for work nmap never does."
        ),
    ),
    Condition(
        id="ns.disc.priv",
        tool="netsanity",
        privilege="root",
        argv_template=_SUDO + _NS + ("--discovery-only",),
        hypotheses=("H3",),
        purpose="netsanity host discovery with naming disabled, privileged",
        parser="netsanity_json",
        status=WITHDRAWN,
        requires="a privileged netsanity engine, which does not exist",
        observed_seconds=0.5,
        notes=(
            "Withdrawn 2026-09-12 with H3; see PROTOCOL.md's amendment of that date. "
            "netsanity has no privileged engine: EngineKind.privilegedBPF is declared "
            "and never constructed, ICMPSweepEngine is the only HostDiscovery "
            "conformance on Darwin and reports 'unprivileged' unconditionally, and "
            "README.md says the privileged helper is not built. Run under sudo it is "
            "byte-for-byte the same engine as ns.disc.unpriv, which a packet capture "
            "confirmed on 2026-09-12 -- 253 ARP and 20 ICMP against 253 and 19, the "
            "same nine hosts. So the pair would have confirmed parity on every block "
            "by construction, which is a tautology and not a result. "
            "The runners.py engine check would have excluded it every time: one "
            "condition in fourteen, 7.1%, against section 7's 5% ceiling. It is "
            "removed because it measures nothing; the exclusion rate going to zero is "
            "a consequence of that and not the reason for it."
        ),
    ),

    # ── Timing sweep ──────────────────────────────────────────────────────────────
    *(_nmap_condition(t, privileged=False) for t in ("T2", "T3", "T4", "T5")),
    *(_nmap_condition(t, privileged=True) for t in ("T2", "T3", "T4", "T5")),

    # ── Naming, H4 only: a capability comparison with no timing claim ─────────────
    Condition(
        id="ns.naming.full",
        tool="netsanity",
        privilege="user",
        argv_template=_NS,
        hypotheses=("H4",),
        purpose="netsanity full pipeline: discovery plus mDNS, SSDP and NetBIOS",
        parser="netsanity_json",
        observed_seconds=3.1,
        notes="No timing claim is attached to this condition; H4 is a capability "
              "comparison and the two systems attempt different tasks.",
    ),
    Condition(
        id="nmap.naming.broadcast",
        tool="nmap",
        privilege="user",
        argv_template=_NMAP + ("--script", "broadcast-dhcp-discover,broadcast-ping,"
                               "broadcast-dns-service-discovery"),
        hypotheses=("H4",),
        purpose="nmap's nearest equivalent to the naming pipeline",
        parser="nmap_xml",
        observed_seconds=25.0,
        notes="Documented in the paper as approximate. nmap's broadcast scripts are not "
              "the same task as name fusion and the protocol says so.",
    ),

    # ── The two ablations of our own mechanism ───────────────────────────────────
    #
    # Both were BLOCKED until 2026-09-09, when the flags they name shipped.  They are
    # kept together because they ablate different things and it is easy to conflate
    # them: `ns.fixed.timeout` removes the ADAPTIVITY of the retransmit interval while
    # keeping the two budgets separate; `ns.budget.shared` removes the SEPARATION and
    # keeps neither.  A result that moved under both would say the mechanism matters; a
    # result that moved under only one says which half of it does.
    Condition(
        id="ns.fixed.timeout",
        tool="netsanity",
        privilege="user",
        argv_template=_NS + ("--discovery-only", "--retransmit-timeout", "{fixed_ms}ms"),
        hypotheses=("H2",),
        purpose="netsanity with a fixed retransmit timeout, the ablation H2 needs",
        status=READY,
        requires=None,
        parser="netsanity_json",
        notes=(
            "H2 claims adaptive per-host timing dominates fixed templates. Without a "
            "way to pin netsanity's own retransmit timeout, the ablation compares "
            "netsanity to nmap's templates and never to netsanity's own fixed-timing "
            "behaviour, which is the comparison that isolates the mechanism. `--deadline` "
            "is not this flag: it bounds the whole scan, not the per-host retransmit "
            "interval. Unblocked 2026-09-09. The pinned value is NOT clamped into the "
            "adaptive path's 25-150 ms range, so `{fixed_ms}` is measured as written, "
            "and the artifact reports `budget_policy: fixed-retransmit` beside the "
            "interval so a reader can tell an imposed value from a measured one."
        ),
    ),
    Condition(
        id="ns.budget.shared",
        tool="netsanity",
        privilege="user",
        argv_template=_NS + ("--discovery-only", "--shared-budget"),
        hypotheses=("H5",),
        purpose="netsanity with one shared budget instead of the split, for H5",
        status=READY,
        requires=None,
        parser="netsanity_json",
        notes=(
            "H5 is an ablation of our own system: split retransmit/declaration budget "
            "versus a single shared one. This is the entry PROTOCOL.md section 2 row 4 "
            "requires. Unblocked 2026-09-09 by `--shared-budget`, which collapses both "
            "questions onto the tail's number — the sweep's pre-split behaviour. Note "
            "it does NOT change the spacing policy: the spread is still bought out of "
            "the same tail slack, so this ablates one variable rather than two. The "
            "artifact reports `budget_policy: shared` alongside the unchanged "
            "`spacing_policy`, which is what makes that checkable rather than asserted."
        ),
    ),
)

BY_ID = {c.id: c for c in CONDITIONS}


def ready() -> list[Condition]:
    """The conditions a block can actually run."""
    return [c for c in CONDITIONS if c.status == READY]


def blocked() -> list[Condition]:
    return [c for c in CONDITIONS if c.status == BLOCKED]


def withdrawn() -> list[Condition]:
    return [c for c in CONDITIONS if c.status == WITHDRAWN]


def for_hypothesis(name: str) -> list[Condition]:
    return [c for c in CONDITIONS if name in c.hypotheses]


def estimated_block_seconds(cooldown_seconds: float) -> float:
    """Roughly how long one block takes, from 0.2 and 0.3's observed wall clocks.

    A diagnostic for planning the collection window, not a result. It exists here
    because a matrix that cannot fit in seven days is a design error, and the cheapest
    time to notice is while reading the matrix.
    """
    return sum(
        (c.observed_seconds or 0.0) + cooldown_seconds for c in ready()
    )


if __name__ == "__main__":
    print(f"{len(ready())} ready, {len(blocked())} blocked, "
          f"{len(withdrawn())} withdrawn\n")
    for c in CONDITIONS:
        mark = {READY: " ", BLOCKED: "!", WITHDRAWN: "-"}[c.status]
        print(f"{mark} {c.id:28s} {c.tool:10s} {c.privilege:5s} {','.join(c.hypotheses)}")
        if c.status == BLOCKED:
            print(f"    BLOCKED on {c.requires}")
        elif c.status == WITHDRAWN:
            print(f"    WITHDRAWN: needs {c.requires}")
    for cooldown in (5.0, 15.0, 30.0):
        seconds = estimated_block_seconds(cooldown)
        print(f"\nat a {cooldown:.0f}s cooldown: ~{seconds:.0f}s per block, "
              f"~{seconds * 120 / 3600:.1f}h for 30 blocks x 4 strata")
