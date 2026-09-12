# Reproducibility record

`PROTOCOL.md`'s deliverable list asks for "a reproducibility appendix: exact versions,
testbed bill of materials, and the commands to rebuild both systems". This is the
source that appendix is written from, kept current as collection proceeds so it cannot
be reconstructed from memory afterwards.

`frozen-binary.json` is the same freeze in a form the harness and the analysis can read.
If the two ever disagree, the JSON is the record and this document is the explanation.

---

## The system under test, frozen

| | |
|---|---|
| tag | `study/binary-2026-09-12b` |
| commit | `ad09ed1f78b6026022462abb676eab63a596c333` |
| `netsanity --version` | `0.4.0` |
| sha256 | `b4220600b75acd10b46d033cb315a9e5c035021494a93afe381e0014eff6e4ed` |
| size | 4,328,936 bytes |
| Mach-O UUID | `B08C5DC8-A0D0-3ADA-87D2-743804211691` |
| built from | `/Users/jc/Dev/InfinityCastle-collection` (worktree, detached at the tag) |
| binary path | `Packages/netsanity-cli/.build/release/netsanity` inside that worktree |

Rebuild:

```bash
git clone https://github.com/JCTec/netsanity && cd netsanity
git checkout study/binary-2026-09-12b
cd Packages/netsanity-cli && swift build -c release
```

**It supersedes `study/binary-2026-09-12`, and the paper should say why.** That tag
stood for about six hours and no block was ever collected under it. Five defects that
had been deliberately left in it were fixed and a sixth was found while checking the
fixes — `DEFERRED-DEFECTS.md` lists all six and what each one was. The rule that a
rebuild costs the window is about a rebuild *during* collection; before the first block
there is no window, and gate 0.3 had just established that collection could not start
anyway. A reader is owed that reasoning rather than a silently bumped hash.

One change is visible in the artifact: the unprivileged engine reports
`["icmp_sweep", "neighbor_table"]` where it reported `["arp_sweep", "icmp_sweep"]`,
because it never performed a layer-2 ARP sweep and a capture proved it. The document
shape is unchanged and the schema version is not bumped, since which names appear in a
capability list has always depended on which engine produced it.

| | |
|---|---|
| Swift | Apple Swift 6.3.3 (swiftlang-6.3.3.1.3 clang-2100.1.1.101), swift-driver 1.148.6 |
| target | `arm64-apple-macosx26.0` |
| macOS | 26.6.2, build 25G83 |
| hardware | Mac16,8, Apple M4 Pro |

The comparator's versions and provenance are in `FINDINGS-0.3-nmap.md` and are not
duplicated here: nmap 7.991, Homebrew bottle, sha256 recorded there. `provenance.py`
re-reads and re-hashes both binaries on every run, so the appendix's numbers and the
data's numbers are the same numbers.

The build emits four *"'as' test is always true"* warnings from
`History/HistoryCommands.swift`. They predate the study and change no behaviour;
`DEFERRED-DEFECTS.md` entry 4 says so, so that a reviewer rebuilding does not have to
wonder.

## What the checksum is for, and what it is not for

**It is not a claim that the build is reproducible. It is not.** Two `swift build -c
release` runs of this commit, at the same path, on this machine, minutes apart, produce
binaries of identical size that differ in 2,684 bytes:

| differing bytes | where | why |
|---|---|---|
| 16 | `LC_UUID` | the linker mints a fresh one per link |
| 212 | a 16-bit field at 106 sites in `__TEXT` | each shifted by a constant +96 between the two builds |
| 2,456 | inside `LC_CODE_SIGNATURE` (`dataoff` 4,293,824) | the ad-hoc signature hashes the pages the other two changed |

Building the same commit at a *different* path makes the binary 2,368 bytes longer as
well: the absolute build directory is embedded 212 times, the two paths differ by 11
characters, and 212 x 11 = 2,332 with the remaining 36 bytes going to alignment. So the
checksum is a property of the artifact and of where it was built, not of the source.

What the checksum is for is the question the study actually needs answered: **did every
block measure the same binary?** `provenance.py` records `netsanity_sha256` on every
run, so that question is answered from the data rather than from a promise. A binary
swapped mid-window is visible on the run it was swapped, and a run whose hash is not
the one above is not a run of this study.

A reviewer rebuilding from the tag will get a different hash and the same program. The
appendix must say that in the sentence next to the hash, because a published checksum
that a reviewer cannot match reads as either carelessness or something worse.

## Where collection runs from, and why it is a worktree

```bash
git worktree add /Users/jc/Dev/InfinityCastle-collection study/binary-2026-09-12
```

`provenance.py` derives the repository it inspects from its own file location, and a
dirty tree aborts the block. Those two together mean the harness cannot live in a
checkout anybody is working in: one untracked scratch file on `master` at 03:00 halts
the night. The worktree is checked out at the tag, nothing is edited in it, and app
work continues on `master` without touching it.

Two tags, not one, and the second does not exist yet:

- **`study/binary-2026-09-12b`** freezes `netsanity-core` and `netsanity-cli`. It is the
  tag the appendix cites for the system under test, and the binary above is built from
  it. It does not move — and the `b` in its name is the record of one that did, which is
  why the superseded tag is left in place rather than deleted.
- **A collection tag, cut at the start of stage 5**, on the `master` commit that carries
  the finished driver. The apparatus keeps being built after the binary is frozen —
  the driver, the pilot's cooldown, the analysis — and the worktree has to move forward
  to reach it. Before it moves, this must be empty:

  ```bash
  git diff --stat study/binary-2026-09-12 <collection-tag> -- \
      Packages/netsanity-core Packages/netsanity-cli
  ```

  That is the check that lets the apparatus advance while proving the measured source
  did not. Its output goes in this document when it is run.

The binary is not rebuilt when the worktree moves. `swift build` inside the collection
worktree is not part of any procedure after the freeze, and the recorded sha256 is what
catches it if it happens anyway.

## Testbed bill of materials

The programmable segment is the primary testbed, per `PHASE0.md`'s amendment. Its
composition, per-responder shaping, calibration and achieved round-trip times are in
`testbed/manifest.json`, and `testbed/FINDINGS-0.1.md` records how it was built and what
it cost to make repeatable. Ten responders, worst calibration error 5.0% against a 10%
tolerance. The three-oracle agreement that gate 0.4 turns on is in
`testbed/gate-0.4.json`: three consecutive rounds, manifest and inventory and capture
all reporting the same ten addresses, no disagreements.

The physical segment is secondary and is `10.10.20.0/24`, the home LAN — a particular
network and not "whatever the laptop is on". `Study/README.md`'s note of 2026-09-09
records why that had to be written down.

## Still open

- **Unattended root.** Gate 0.3's privileged half ran on 2026-09-12 with Touch ID and a
  person present, which is enough for a gate and not for collection: `run_block.py`
  invokes `sudo -n`, which fails whether or not Touch ID is configured, because `-n`
  means there is nobody to prompt. Four of the thirteen live conditions need root, and
  `tcpdump` needs it for every one of the thirteen. `PHASE0.md` assigns this to JC.
- **The collection tag and its diff check**, above.
- **The cooldown**, which the pilot sets and which is 15 s only as a default until then.
- **`-T2`'s cost.** Roughly 510 s for a `/24`, extrapolated from its capture rather than
  measured to completion, and by far the largest term in a block. The pilot should run
  it to the end once and replace the extrapolation.
