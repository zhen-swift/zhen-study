# Study 2's harness

Python, stdlib only, run by the runner under Apple's `/usr/bin/python3` (3.9). Study 1's `harness/` is study 1's
instrument and is not edited; v2 imports two of its pieces unchanged: `capture.Capture` (one `sudo -n tcpdump`
per run, with its wire counts) and `runners.run_nmap` / `parse_nmap_xml`. Same rule as study 1: **the harness
never computes a statistic.** Records hold address sets and the manifest's addresses; recall is the analysis's.

| File | What |
|---|---|
| `conditions.py` | Phase 1's grid and phase 2's matched set, as data: id, tool, privilege, flags, history state, hypotheses |
| `zhen.py` | Runs zhen (wall clock taken here, monotonic) and parses its artifact (schema 4, 0.8.1) into the record, with a warning for every way the artifact differs from what the study relies on |
| `record.py` | The NDJSON records (`block`, `run`), validated on write and on read |
| `run_block.py` | One block = one job. The only thing the runner runs for phases 1 and 2 |
| `generate.py` | A phase's design → job files in `v2/jobs/<design>-<seed>/`, shuffled by the seed, with `design.json` |
| `privacy.py` | `/study-sync`'s privacy check: hardware and home addresses; hashes VM addresses in copies |
| `check.py` | Every problem and warning in a `runs.ndjson`. The S2 gate is a dry run with none |
| `contract.py` | zhen-core's study contract (G9) on the testbed. Row 5 deferred to the root run (below) |
| `diag/` | `llinfo.c`, zhen's neighbour-table read alone, and its result as root |
| `test_harness.py` | Parser, records, conditions, generator. `fixtures/` holds three artifacts from the contract run |

## Decisions (S2, Claude; open to JC until the freeze)

| | |
|---|---|
| **Discovery only** | Every zhen condition is `--discovery-only`: nmap `-sn` names nothing, and no hypothesis is about naming. `p2.zhen.product` differs from the default only by the IPv6 window |
| **History** | Each zhen run gets its own store through `ZHEN_HISTORY`. *Empty*: a path that does not exist yet. *Primed*: a copy of the block's primed store, made once per block by five scans of the testbed with the table flushed before each (so the store holds cold first contacts), before the block's first flush. Every primed condition in a block starts from the same bytes |
| **Phase 1** | 9 reach levels (`learned`; `fixed` 0.5, 1, 1.5, 2, 3 s; `history` at 0.90, 0.97, 0.99) × empty/primed = 18 conditions, all `--ipv6-window 0` (the wait is the factor), flush per run. `config.json` → `phase1.blocks_per_cell` = 20 per dispersion |
| **Phase 2** | default (primed), first scan (empty), root (primed), `--reach learned --no-neighbor-watch` (empty: study 1's binary had no history), all `--ipv6-window 0`; product default (primed, IPv6 window on); nmap root and user at -T3, -T4, -T5, and -T2 in blocks whose index in the cell is a multiple of 4 |
| **Cache** | `sudo -n /usr/sbin/arp -a -d` before every run (flush per run), or once per block after priming (flush per block). Each run records `cold` or `warm`, and the table's size before and after |
| **Thermal** | Before every run, `notifyutil -g com.apple.system.thermalpressurelevel`; above 0 the run waits (15 s polls), and the block stops after 15 min |
| **Testbed** | Each block starts with `netbed2.py apply --manifest d<D>.json`; the record carries the manifest's sha256 and addresses, and netbed2's `host_conditions` |
| **Captures** | One pcap per run in `/Users/Shared/zhen-study2/captures/`, **outside `data/`**: they hold the VMs' hardware addresses, and `/study-sync` copies `data/`. The record carries each pcap's path, sha256 and wire counts |
| **Root** | `sudo -n` for nmap (zhenstudy's grant) and, after S5, zhen. `sudo` drops `ZHEN_HISTORY` unless the root line keeps it (`Defaults!/usr/local/zhen-study2/zhen env_keep += "ZHEN_HISTORY"`); without it a root run reads `SUDO_USER`'s own store, and `run_block` warns when a primed run read no samples |
| **Dry run** | `--dry-run` runs every condition for real and writes under `data/dryrun/`, `dry_run: true`. Before S5, zhen as root is `--stub-root`: a stub artifact through the real parser, `stubbed: true` |

## macOS 27 and the neighbour table

macOS 27 gives the link-layer table to a non-Apple binary only when it runs as root (`diag/`, LEDGER.md
2026-11-19). Unprivileged zhen therefore runs without neighbour evidence or the watch: no hardware addresses, and
on the testbed the tcp-only and silent responders (r06, r08) are not found. That is measured, not worked around.
G9 row 5 (`neighbor_resolved`) is judged and shown in every contract run and left out of `passed`; it is re-run as
root after zhen's root line (S5) and must pass before the pilot (S6).
