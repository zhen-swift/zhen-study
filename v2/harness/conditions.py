"""Study 2's conditions, as data: phase 1's grid and phase 2's matched set (PLAN.md).

The harness, the job generator and the analysis all read this module, so a condition cannot appear in the data
that the plan does not describe. Every zhen condition is `--discovery-only` (nmap `-sn` finds hosts and names
nothing) and points `ZHEN_HISTORY` at a store of its own; which store, and in what state, is the condition's
`history` field.

    python3 v2/harness/conditions.py        prints the matrix
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

V2 = Path(__file__).resolve().parents[1]
CONFIG = json.loads((V2 / "config.json").read_text())
FROZEN = json.loads((V2 / "frozen-binary-v2.json").read_text())

ZHEN = FROZEN["path"]
NMAP = "/opt/homebrew/bin/nmap"        # the path zhenstudy's grant names (SETUP.md)
CIDR = CONFIG["testbed"]["cidr"]
IFACE = CONFIG["testbed"]["interface"]

#: History states. `empty`: a store that does not exist yet, so the scan is a first scan and writes the store's
#: first lines. `primed`: a copy of the block's primed store (five scans of the same manifest, PLAN.md phase 1),
#: so every primed condition in a block starts from the same history.
EMPTY, PRIMED = "empty", "primed"
PRIMING_SCANS = 5

ZHEN_BASE = ("scan", "--cidr", CIDR, "--iface", IFACE, "--discovery-only", "--json", "--quiet", "--no-color")
#: Every zhen condition compared against nmap: `nmap -sn` on an IPv4 /24 sends nothing over IPv6 (PLAN.md).
MATCHED = ("--ipv6-window", "0")


@dataclass(frozen=True)
class Condition:
    id: str
    phase: int
    tool: str                       # "zhen" | "nmap"
    privilege: str                  # "user" | "root"
    flags: tuple = ()
    history: str | None = None      # zhen only: EMPTY | PRIMED
    hypotheses: tuple = ()
    purpose: str = ""
    #: nmap -T2 runs in one block in four (PLAN.md phase 2); the generator decides which.
    every_fourth_block: bool = False
    #: Seconds a run is expected to take, for sizing jobs only. Never a result.
    expected_seconds: float = 10.0
    notes: str = ""

    @property
    def root(self):
        return self.privilege == "root"

    def argv(self, *, nmap_xml=None):
        """The exact command. Root runs through `sudo -n`, so a missing grant fails at once, never on a prompt."""
        sudo = ["sudo", "-n"] if self.root else []
        if self.tool == "zhen":
            return sudo + [ZHEN, *ZHEN_BASE, *self.flags]
        if nmap_xml is None:
            raise ValueError(f"{self.id}: nmap needs the path of its XML")
        return sudo + [NMAP, "-sn", CIDR, "-oX", str(nmap_xml), "--reason", *self.flags]

    def as_record(self):
        d = asdict(self)
        d["flags"] = list(self.flags)
        d["hypotheses"] = list(self.hypotheses)
        return d


# ── Phase 1: explore (testbed, zhen only, unprivileged) ─────────────────────────────────────────────────────
#
# Reach × history, at every dispersion, the cache flushed before every run. The outputs are the recall-against-
# wait curve, whether P97 is right and whether the 1.5 s first-scan wait should move: they become phase 2's
# flags, never a rebuild. Every run is `--ipv6-window 0`, because the wait is the factor and the IPv6 window
# would add the same second or two to every condition.

REACH_LEVELS = (
    ("learned", ("--reach", "learned")),
    *((f"fixed{label}", ("--reach", value)) for label, value in
      (("0.5s", "500ms"), ("1s", "1s"), ("1.5s", "1500ms"), ("2s", "2s"), ("3s", "3s"))),
    *((f"history{p}", ("--reach", "history", "--reach-percentile", p)) for p in ("0.90", "0.97", "0.99")),
)

PHASE1 = tuple(
    Condition(id=f"p1.{reach}.{history}", phase=1, tool="zhen", privilege="user",
              flags=(*flags, *MATCHED), history=history,
              purpose=f"reach {reach}, {history} history",
              expected_seconds=6.0 if reach == "fixed3s" else 4.0)
    for reach, flags in REACH_LEVELS for history in (EMPTY, PRIMED)
)


# ── Phase 2: confirm (testbed, pre-registered at the freeze) ──────────────────────────────────────────────────

def _nmap(privileged, template):
    level = "root" if privileged else "user"
    # Largest observed in study 1's pilot (conditions.py there), for sizing only.
    seconds = ({"T2": 482.0, "T3": 8.4, "T4": 8.5, "T5": 4.6} if privileged
               else {"T2": 2546.0, "T3": 28.7, "T4": 23.3, "T5": 18.2})[template]
    return Condition(id=f"p2.nmap.{level}.{template}", phase=2, tool="nmap", privilege=level,
                     flags=(f"-{template}",), hypotheses=("H1", "H2"),
                     purpose=f"nmap -sn, {level}, -{template}", every_fourth_block=template == "T2",
                     expected_seconds=seconds)


PHASE2 = (
    Condition(id="p2.zhen.default", phase=2, tool="zhen", privilege="user", flags=MATCHED, history=PRIMED,
              hypotheses=("H1", "H2", "H3", "H7", "H8"),
              purpose="the default, history primed, matched to nmap (IPv6 window 0)"),
    Condition(id="p2.zhen.first", phase=2, tool="zhen", privilege="user", flags=MATCHED, history=EMPTY,
              hypotheses=("H1", "H7", "H8"),
              purpose="the default's first scan: empty history, matched"),
    Condition(id="p2.zhen.root", phase=2, tool="zhen", privilege="root", flags=MATCHED, history=PRIMED,
              hypotheses=("H3",),
              purpose="the default as root, history primed, matched; H3's pair is p2.zhen.default",
              notes="Needs zhen's root line (S5) to keep ZHEN_HISTORY through sudo (env_keep), or the run reads "
                    "another store; run_block checks the store it read."),
    Condition(id="p2.zhen.learned", phase=2, tool="zhen", privilege="user",
              flags=("--reach", "learned", "--no-neighbor-watch", *MATCHED), history=EMPTY,
              hypotheses=("H1", "H2"),
              purpose="study 1's mechanism inside 0.8.1 (the bridge), matched",
              notes="Empty history: study 1's binary had none."),
    Condition(id="p2.zhen.product", phase=2, tool="zhen", privilege="user", flags=(), history=PRIMED,
              purpose="the product default with its IPv6 window: the product's wall clock, outside the nmap "
                      "comparison", expected_seconds=6.0),
    *(_nmap(privileged, t) for privileged in (True, False) for t in ("T2", "T3", "T4", "T5")),
)

CONDITIONS = PHASE1 + PHASE2
BY_ID = {c.id: c for c in CONDITIONS}
assert len(BY_ID) == len(CONDITIONS), "duplicate condition id"


def for_phase(phase, *, block_index=0):
    """The conditions one block of `phase` runs. -T2 only in every fourth block of a cell."""
    pool = PHASE1 if phase == 1 else PHASE2
    return [c for c in pool if not c.every_fourth_block or block_index % 4 == 0]


if __name__ == "__main__":
    for c in CONDITIONS:
        hist = c.history or "-"
        print(f"{c.id:28s} {c.tool:5s} {c.privilege:5s} {hist:7s} {' '.join(c.flags):48s} {','.join(c.hypotheses)}")
    print(f"\nphase 1: {len(PHASE1)} per block; phase 2: {len(for_phase(2, block_index=1))} per block, "
          f"{len(for_phase(2, block_index=0))} with -T2")
