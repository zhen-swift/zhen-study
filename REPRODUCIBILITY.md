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

Two tags, not one:

- **`study/binary-2026-09-12b`** freezes `netsanity-core` and `netsanity-cli`. It is the
  tag the appendix cites for the system under test, and the binary above is built from
  it. It does not move — and the `b` in its name is the record of one that did, which is
  why the superseded tag is left in place rather than deleted.
- **`study/collection-2026-09-13`**, cut on `47113b8` when collection started, the
  `master` commit that carries the finished driver, schema 2, the 2026-09-13 amendment
  and `collection.sh`. The frozen-package diff against `study/binary-2026-09-12b` at
  that commit is empty and the binary in the collection worktree hashes `b4220600…`. The apparatus keeps being built after the binary is frozen —
  the driver, the pilot's cooldown, the analysis — and the worktree has to move forward
  to reach it. Before it moves, this must be empty:

  ```bash
  git diff --stat study/binary-2026-09-12b <commit> -- \
      Packages/netsanity-core Packages/netsanity-cli
  ```

  That is the check that lets the apparatus advance while proving the measured source
  did not. Its output goes in this document when it is run.

  **Run six times, three on 2026-09-12 and three on 2026-09-13, for the pilot.** The
  worktree moved from `ad09ed1` (the tag) to `05b0870`, `30584fc`, `f9e2d6c`, `b6b4051`
  and `cb30871`, to pick up the driver, the apparatus fixes the pilot found, schema 2,
  and the two fixes the third attempt's first block found. Each time the command above
  printed nothing — zero lines of diff across both frozen packages — and
  `shasum -a 256` of the binary in the worktree read `b4220600…` before and after. The
  worktree is checked out detached at whichever apparatus commit collection runs from;
  `provenance.py` records that commit on every run, and the frozen packages at that
  commit are byte-identical to the tag's.

  **Run once more on 2026-09-14, during collection.** The host rebooted after the
  first five blocks and the testbed had to be rebuilt (above), which rewrites
  `testbed/manifest.json` and `testbed/gate-0.4.json`; those live in the tree the
  harness reads, so the worktree moved from `47113b8` (the collection tag) to the
  commit carrying them. The command printed nothing, and the binary hashed
  `b4220600…` before and after. Blocks 1 to 5 carry `47113b8` as their apparatus
  commit and every later block carries the rebuild's; the frozen packages are
  byte-identical at both.

  **And again on 2026-09-15**, after the host slept and the segment was re-calibrated
  (above): `1bf4371` to the commit carrying the re-measured manifest. The command
  printed nothing; the binary hashed `b4220600…` before and after.

  **And on 2026-09-16**, after the host lost power (below): `d286272` to the commit
  carrying the rebuilt manifest, worst error 1.36%. The command printed nothing; the
  binary hashed `b4220600…` before and after.

  **And on 2026-09-18.** The lid was closed for three seconds at 20:05 on 2026-09-17,
  unplugged, with block 68 in flight; the harness excluded run 9 as `host_asleep` and
  halted at 20:42, block 68 is partial, and with no driver holding an assertion the
  host idle-slept until the morning. Re-calibrated at 09:05, worst error 1.50%,
  identity fields unchanged, gate 0.4 met; `a77783a` to the commit carrying it. The
  command printed nothing; the binary hashed `b4220600…` before and after. The
  overnight window of the 18th and most of its morning window were lost.

  **And on 2026-09-18, a second time.** The cable came out at 12:23 with block 74 in
  flight, the battery was empty by 14:34 and the host shut down; back on AC at 16:33,
  netbed1 left `Broken` by the crash (`limactl stop -f` cleared it), all five machines
  brought up and re-calibrated. It took three `configure` passes: the first left r06 at
  −5.12% at the four-round limit, the second left r05 at +18.4% because the ~5 ms of
  extra delay that every rebuild has shown on the 25 ms pair's first round appeared
  for three rounds and vanished on the fourth, so the final setting was tuned against
  overhead that was no longer there. The third pass converged at 1.51% and an
  independent thirty-ping pass agreed on every responder. `5ec05e4` to the commit
  carrying it; the command printed nothing; the binary hashed `b4220600…` before and
  after. The rest of the afternoon window was lost.

The binary is not rebuilt when the worktree moves. `swift build` inside the collection
worktree is not part of any procedure after the freeze, and the recorded sha256 is what
catches it if it happens anyway.

## Testbed bill of materials

The programmable segment is the primary testbed, per `PHASE0.md`'s amendment. Its
composition, per-responder shaping, calibration and achieved round-trip times are in
`testbed/manifest.json`, and `testbed/FINDINGS-0.1.md` records how it was built and what
it cost to make repeatable. Ten responders, worst calibration error 1.60% at the rebuild
of 2026-09-14 (1.22% at the rebuild of 2026-09-13 after the host lost power, 1.3% at the
pilot rebuild of 2026-09-12, 5.0% when first built) against a 10% tolerance. The
three-oracle agreement that gate 0.4 turns on is in `testbed/gate-0.4.json`, re-run
after every rebuild: three consecutive rounds, manifest and inventory and capture all
reporting the same ten addresses, no disagreements.

**The segment does not survive a host reboot, and collection has now crossed one.** The
namespaces, the `netem` shaping and the spinners are transient inside the guests, so a
rebuild is `netbed.py up`, `netbed.py configure` and `oracles.py`, in that order, and
the manifest is rewritten with fresh achieved times. The host rebooted at 09:22 on
2026-09-14 with five evening blocks of 2026-09-13 already in `runs.ndjson`; the rebuild
that morning produced a manifest whose addresses, hardware addresses, roles, target
times and open ports are identical to the one those five blocks were measured under —
checked field by field against the committed file — and only the achieved column
moved. `provenance.py` records the apparatus commit on every run, so which manifest a
block was measured under is readable from the data.

**A host sleep degrades the segment without destroying it, and that is worth checking
for rather than assuming.** The lid was closed at 02:34 on 2026-09-15 and the host slept
five and a half hours mid-block; the harness excluded the run as `host_asleep` and
halted, block 19 is partial, and the machines were still running when it woke. But
they were not calibrated any more: twenty pings per responder before anything was
touched put r02 at +10.45% against the 10% tolerance, r07 at +4.9%, r10 answering 17
of 20 with an 801 ms tail, and every responder's maximum several times its median —
the deep-idle jitter `testbed/FINDINGS-0.1.md` describes, back after the guests had
idled through the sleep. `netbed.py configure` and `oracles.py` were run again, worst
error 1.50%, identity fields unchanged, and the worktree moved to the commit carrying
the new manifest. So the restart after any sleep is the rebuild, not just deleting the
halt file: the halt file says the host slept, and the segment has to be re-measured
before a block is.

The physical segment is secondary and is `10.10.20.0/24`, the home LAN — a particular
network and not "whatever the laptop is on". `Study/README.md`'s note of 2026-09-09
records why that had to be written down.

## Block 36 ran on battery and the record says it did not

The power cable came out at 06:45:42 on 2026-09-16 with block 36 in flight (started
06:15:32). The driver waits for AC before *starting* a block and does not stop one; the
block's runs 3 to 12 ran from 06:55 to 07:07 on battery, the battery drained from 100%
to empty under the load by 08:41, the OS shut the host down (the driver's log shows
`signal 15` at 08:41:54), and it came back on AC at 09:12. The testbed was rebuilt the
same way as on 2026-09-14.

**Every one of block 36's thirteen records carries `on_ac_power: true`.** `provenance.py`
is collected once per block, at 06:15:32 when the host was plugged in, and the same
document is copied onto every run — `collected_at_unix` is identical on all thirteen.
The covariate section 6 fixes was violated for ten runs and the record does not show
it; `pmset -g log` is the only evidence, and it is not a study artifact. So this
section is the evidence: **block 36 is admissible by the exclusion rules but its
runs 3 to 12 violate the plugged-in control, and the analysis should treat the block
as flagged.** The per-run covariate stays true for every other block, because the
driver refuses to start a block on battery and this is the only unplugging during
collection.

**Block 74 is the same case.** The cable came out at 12:23:46 on 2026-09-18 with block
74 in flight (started 12:00:34); its runs 3 to 12 ran on battery and all thirteen records
say `on_ac_power: true`. Same defect, same flag: admissible by the exclusion rules,
runs 3 to 12 in violation of the plugged-in control, block flagged for the analysis.

**And block 93.** Cable out at 13:34:33 on 2026-09-19 with block 93 in flight (started
13:11:22); runs 2 to 12 on battery, records say AC, the battery at 7% when AC returned
at 15:08:57. Flagged the same way. That makes three flagged blocks — 36, 74 and 93 —
all afternoon or morning, none overnight or evening.

The defect is in the apparatus, not in the frozen packages: per-block provenance is
right for the binary hashes and the git state, which cannot change mid-block, and wrong
for power, thermal pressure and uptime, which can. Whether to make the harness re-read
those three per run mid-collection — a worktree move, not a rebuild — is JC's call and
is not taken here.

## Unattended root, as installed

`Study/launchd/netsanity-study.sudoers` was installed by JC on 2026-09-12 at 13:41 as
`/etc/sudoers.d/netsanity-study`, mode 0440 root:wheel, and `sudo -n` for
`/opt/homebrew/bin/nmap`, `/usr/sbin/tcpdump` and `/usr/sbin/arp` succeeds without a
prompt from this account. It is a whole-binary grant to one user for three absolute
paths, and it is removed with `sudo rm /etc/sudoers.d/netsanity-study` when collection
ends. The file's own header carries the reasoning and belongs in the appendix verbatim.

## The pilot's settings, now in force

- **Cooldown: 10 s**, from `harness/settle.py` and `data/pilot-settle.json` — the
  longest scan-attributable traffic tail after a process exits is 6.1 s, on the kernel's
  fixed ARP retry schedule. `FINDINGS-0.6-pilot.md`.
- **nmap timeout: 3600 s.** Unprivileged `-T2` ran at 220 to 2546 s across the pilot's
  fourteen admissible runs of it, three attempts. The ceiling has never been reached and
  a run that reaches it is a finding, not a timeout.
- **A block flushed once is 15 to 46 minutes**, the range being unprivileged `-T2`.
  Seven such blocks across the second and third attempts spanned 916 to 2748 s, mean
  1839 s. 120 blocks is about 61 hours of machine time at the mean inside the seven-day
  window, five blocks per stratum per day at most 3.8 hours of each six-hour window.
  A block flushed before every run averaged 2494 s over four.
- **The host must be on AC.** Section 6 fixes the plugged-in state; the driver waits for
  it from `7ebad19`. A closed lid on battery sleeps the host under any assertion.
- **The host must be held awake from a full wake.** Idle sleep is set to one minute on
  this machine. The driver takes `caffeinate -u` for five seconds and then holds `-i`;
  a run in which the host slept is excluded as `host_asleep` and stops the block.

## Still open

- **Nothing before collection.** The collection tag is cut and its diff check is
  recorded above.
- **Cache state: ruled on 2026-09-13, one flush per block.** `PROTOCOL.md` section 12
  carries the amendment, the alternatives with their measured costs, and the statement
  that the cold arm is analysed pooled at about nine runs per condition. Nothing about
  it is open; it is listed here because the appendix must reproduce the amendment
  verbatim.
- **`conditions.estimated_block_seconds` was re-derived** from the third attempt's
  largest runs; it is 3352 s at a 10 s cooldown.
