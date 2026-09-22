"""The collection's NDJSON, plus the stratum sidecar, as one table.

`load.py` reads the simulator's CSVs and validates the NDJSON; this module is the
collection analysis's view of the same file — one row per run, with the handful of
derived columns every hypothesis needs, and nothing computed that the protocol does not
name.

Two rules it exists to hold:

**Recall is computed against the testbed manifest's declared responder set**, carried
on every record at `oracle.manifest.addresses`, and not against whatever a tool
returned.  Every run in this collection found `192.168.64.1` as well — the bridge the
scanning Mac speaks through.  It is a real host and it is not a declared responder, so
it is not recall, and a tool that found it and nothing else would score zero here.

**The stratum comes from the sidecar**, never from the analysing machine's clock.  See
`strata.py` for why: the record stores no stratum and no timezone.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

HERE = Path(__file__).resolve().parent
STUDY = HERE.parent
DEFAULT_RUNS = STUDY / "data" / "runs.ndjson"
DEFAULT_SIDECAR = HERE / "strata.json"

SCHEMA_VERSION = 2

#: `REPRODUCIBILITY.md` — three blocks whose runs 2-or-3 to 12 ran on battery while
#: every record says `on_ac_power: true`, because `provenance.py` is collected once per
#: block and copied onto each run.  They are admissible under the protocol's exclusion
#: rules; the analysis reports whether dropping them moves anything.
FLAGGED_BLOCKS = (36, 74, 93)

#: The netsanity conditions, split by what the budget flag does to them.
NETSANITY_DISCOVERY = ("ns.disc.unpriv", "ns.fixed.timeout", "ns.budget.shared")
#: `PROTOCOL.md` H5: the split budget is the default, the shared budget is the ablation.
H5_SPLIT = "ns.disc.unpriv"
H5_SHARED = "ns.budget.shared"
#: H6 compares unprivileged netsanity against unprivileged nmap at its best template.
NMAP_UNPRIV = ("nmap.sn.unpriv.T2", "nmap.sn.unpriv.T3",
               "nmap.sn.unpriv.T4", "nmap.sn.unpriv.T5")
NMAP_PRIV = ("nmap.sn.priv.T2", "nmap.sn.priv.T3",
             "nmap.sn.priv.T4", "nmap.sn.priv.T5")
#: H1 and H2 are host-discovery claims.  `nmap.naming.broadcast` and `ns.naming.full`
#: serve H4, which carries no timing claim, and are kept out of the frontier.
DISCOVERY_CONDITIONS = NETSANITY_DISCOVERY + NMAP_UNPRIV + NMAP_PRIV


@dataclass(frozen=True)
class Run:
    run_id: str
    block_id: int
    sequence_index: int
    condition_id: str
    tool: str
    privilege: str
    stratum: str
    cache_state: str
    wall_clock: float
    self_reported: float | None
    exit_status: int
    parse_ok: bool
    parse_outcome: str | None
    excluded: bool
    exclusion_reason: str | None
    found: frozenset[str]
    truth: frozenset[str]
    started_at_unix: float
    finished_at_unix: float
    apparatus_commit: str
    flagged: bool
    arp_requests: int
    tcp_rst: int
    tcp_synack: int
    replies_seen: int | None
    hosts_found: int | None
    probes_sent: int | None
    budget_policy: str | None
    raw: dict

    @property
    def recall(self) -> float:
        return len(self.found & self.truth) / len(self.truth)

    @property
    def precision(self) -> float:
        return len(self.found & self.truth) / len(self.found) if self.found else 0.0

    def found_host(self, address: str) -> bool:
        return address in self.found


def load(runs_path: Path | str | None = None,
         sidecar_path: Path | str | None = None) -> list[Run]:
    runs_path = Path(runs_path) if runs_path else DEFAULT_RUNS
    sidecar_path = Path(sidecar_path) if sidecar_path else DEFAULT_SIDECAR
    if not sidecar_path.exists():
        raise SystemExit(
            f"{sidecar_path} is missing. The record stores no stratum; run "
            f"`python3 analysis/strata.py` first."
        )
    sidecar = json.loads(sidecar_path.read_text())
    strata = {int(k): v["stratum"] for k, v in sidecar["blocks"].items()}

    out: list[Run] = []
    with open(runs_path, encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            if record.get("dry_run"):
                continue
            if record["schema_version"] != SCHEMA_VERSION:
                raise SystemExit(
                    f"{runs_path}: record {record['run_id']} is schema "
                    f"{record['schema_version']}; this analysis was written against "
                    f"{SCHEMA_VERSION}"
                )
            discovery = (record["parse"] or {}).get("discovery") or {}
            wire = record["capture"]["wire"]
            exclusion = record.get("exclusion")
            out.append(Run(
                run_id=record["run_id"],
                block_id=record["block_id"],
                sequence_index=record["sequence_index"],
                condition_id=record["condition_id"],
                tool=record["tool"],
                privilege=record["privilege"],
                stratum=strata[record["block_id"]],
                cache_state=record["cache_state"],
                wall_clock=record["wall_clock_seconds"],
                self_reported=record.get("tool_self_reported_seconds"),
                exit_status=record["exit_status"],
                parse_ok=bool((record["parse"] or {}).get("ok")),
                parse_outcome=(record["parse"] or {}).get("outcome"),
                excluded=exclusion is not None,
                exclusion_reason=exclusion["reason"] if exclusion else None,
                found=frozenset(record["found_addresses"]),
                truth=frozenset(record["oracle"]["manifest"]["addresses"]),
                started_at_unix=record["started_at_unix"],
                finished_at_unix=record["finished_at_unix"],
                apparatus_commit=record["provenance"]["git_commit"][:7],
                flagged=record["block_id"] in FLAGGED_BLOCKS,
                arp_requests=wire["arp_requests"],
                tcp_rst=wire["tcp_rst"],
                tcp_synack=wire["tcp_synack"],
                replies_seen=discovery.get("replies_seen"),
                hosts_found=discovery.get("hosts_found"),
                probes_sent=discovery.get("probes_sent"),
                budget_policy=discovery.get("budget_policy"),
                raw=record,
            ))
    return out


def admissible(runs: list[Run], *, drop_flagged: bool = False) -> list[Run]:
    """Everything the protocol's exclusion rules admit.

    The two exclusions in the file are the two exclusions; nothing here reclassifies a
    run.  `drop_flagged` is the sensitivity arm for blocks 36, 74 and 93 and is never
    the default — they are admissible, and the analysis reports both.
    """
    kept = [r for r in runs if not r.excluded]
    if drop_flagged:
        kept = [r for r in kept if not r.flagged]
    return kept


def by_condition(runs: list[Run]) -> dict[str, list[Run]]:
    out: dict[str, list[Run]] = {}
    for run in runs:
        out.setdefault(run.condition_id, []).append(run)
    return out


def arm(runs: list[Run], cache_state: str) -> list[Run]:
    return [r for r in runs if r.cache_state == cache_state]


def paired_by_block(runs: list[Run], left: str, right: str) -> list[tuple[Run, Run]]:
    """Runs of two conditions from the same block, which is what McNemar pairs on.

    `PROTOCOL.md` section 7: the same hosts are observed by both systems within a
    block, so the per-host outcomes are paired.  A block missing either condition
    contributes nothing rather than being half-counted.
    """
    a = {r.block_id: r for r in runs if r.condition_id == left}
    b = {r.block_id: r for r in runs if r.condition_id == right}
    return [(a[k], b[k]) for k in sorted(set(a) & set(b))]


def truth_set(runs: list[Run]) -> frozenset[str]:
    """The declared responder set, which is constant across this collection."""
    sets = {r.truth for r in runs}
    if len(sets) != 1:
        raise SystemExit(f"the manifest's responder set is not constant: {len(sets)} variants")
    return next(iter(sets))
