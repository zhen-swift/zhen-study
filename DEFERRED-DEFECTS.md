# Defects that ship in the measured binary

The study measures one build. A rebuild mid-collection does not cost a fix — it costs
the window, because every block before it and every block after it are then two
different systems, and `PROTOCOL.md`'s confound table already commits to "a rebuild
restarts the block". So from the freeze at `study/binary-2026-09-12` until the last
block lands, defects found in `netsanity-core` or `netsanity-cli` are written here and
left alone.

This is not a bug tracker. It is the list of things a reviewer is entitled to know were
already known and deliberately left in the thing that was measured.

**None of the four below is on the path any measured condition takes.** That claim is
made explicitly for each one, because "we knew and it did not matter" is only worth
reading if the second half is argued rather than asserted.

---

## 1. The `flock` return is unchecked, so `EINTR` proceeds unlocked

`Packages/netsanity-core/Sources/NetSanityCore/Persistence/LogHistoryStore.swift`,
`withLock`, line 234 at the tag.

```swift
flock(handle.fileDescriptor, exclusive ? LOCK_EX : LOCK_SH)
defer { flock(handle.fileDescriptor, LOCK_UN) }
return body()
```

The blocking `flock` can return -1. On this platform the case that matters is `EINTR`:
a signal delivered to the thread while it waits for the lock aborts the wait, and
nothing here notices. `body()` then runs the read-modify-write the lock exists to make
atomic, without the lock, and the `LOCK_UN` in the `defer` releases a lock that was
never taken.

The documentation immediately above it says a lock that cannot be taken is not fatal,
and that is a deliberate and correct decision for `ENOLCK` on a file system with no
locking. It is the wrong decision for `EINTR`, which is not "this file system cannot
lock" but "try again". The two are conflated because neither is looked at.

**Why it is not on the measured path.** Interruption needs a signal, and every
netsanity condition is a short non-interactive `scan` run by the harness with no signal
sent to it. It writes to a store created for that single run — `PROTOCOL.md`'s
2026-09-11 amendment — so there is no second writer to lose a race against even if the
lock were dropped. The failure needs a signal and a concurrent writer, and the
apparatus supplies neither.

**The fix, for after.** Loop on `EINTR`, treat every other error as the existing
lock-free fallback, and record which happened. Not attempted here.

## 2. Retention applies at the fold and nowhere else

`Packages/netsanity-core/Sources/NetSanityCore/Persistence/HistoryLedger.swift`:
`pruneEvents(asOf:)` at line 296 has exactly one caller, `fold(_:)` at line 287.

So events older than the retention window are dropped when a scan is recorded, and only
then. A store that is opened and read but never written keeps returning events the
policy says are gone: launch the app, set "keep events for 7 days", read a
three-week-old event, quit, and nothing has expired because nothing was recorded. The
prune is durable once it happens — `record` compacts rather than appends when
`prunedEvents > 0`, and the comment there explains why — but it happens on a schedule
driven by scanning rather than by time.

`CHANGELOG.md` claims *"Keep events for 30 days now keeps events for 30 days"*, and on
the read path it does not yet.

**Why it is not on the measured path.** Every netsanity condition runs against a store
created fresh for that run, so there is nothing in it older than the run itself and the
prune has nothing to find at any point in the seven-day window. The measured quantity
is discovery wall clock, and neither `pruneEvents` nor the compaction it triggers is
reached.

**The fix, for after.** Prune on load as well as on fold, which means the ledger needs
a clock rather than borrowing the timestamp of whatever run is being folded.

## 3. There is no two-process race test

`Packages/netsanity-core/Tests/NetSanityCoreTests/HistoryLogTests.swift`. The race
coverage is real and it is not nothing: *"Two writers racing on one file lose no run,
compaction included"* (line 241), *"A compaction cannot delete a run another store
recorded"* (line 319), and *"A second open of the same file is locked out, in the same
process"* (line 357), which pins the property the other two lean on — `flock` is per
open file description, so a second `open` from inside one program is excluded exactly
as a second process would be.

That argument is sound and it is written down at the test. What it does not cover is
everything that is per-process rather than per-descriptor: the file system's own
behaviour across processes, and any future change from `flock` to `fcntl` record locks
would silently keep all three tests passing while destroying the guarantee, because
POSIX record locks are per process and the same-process test would then be excluded by
nothing.

So the suite proves the store is safe against a second `LogHistoryStore`, and infers
rather than measures that it is safe against a second `netsanity`. The inference is
correct today. The test that would keep it correct does not exist.

**Why it is not on the measured path.** This is a missing test, not a defect in the
binary, and it is listed here because the same rule covers it: writing it would change
`netsanity-core`'s test target, and the freeze covers the package rather than only the
sources that link into the binary. No measured condition runs two netsanity processes
against one store; each run has its own.

**The fix, for after.** The project forbids subprocesses in the product, not in its
tests. A test that spawns two copies of the built CLI against one store path and checks
that both runs survive would close it.

## 4. Four `catch let error as ScanSetupError` clauses the compiler calls redundant

`Packages/netsanity-cli/Sources/netsanity/History/HistoryCommands.swift`, lines 90,
128, 165 and 215. Each `run()` catches a type that its `execute()` declares as a typed
`throws(ScanSetupError)`, so the pattern always matches and the release build emits
*"'as' test is always true"* four times.

Cosmetic, and recorded for one reason only: a reviewer who rebuilds from the tag will
see four warnings in the transcript and is owed a sentence saying they were there
before the study and change no behaviour. The typed-throws annotation was added after
the catch was written and made it redundant.

**Why it is not on the measured path.** No measured condition invokes `netsanity
history`.

**The fix, for after.** Drop the `as ScanSetupError` from the four clauses. One line
each.

---

## The rule this file exists to hold

Found from the freeze onward: write it here, name the file and the symbol, say why it
does or does not touch a measured condition, and stop. If something is found that *is*
on the measured path, that is not an entry in this file — it invalidates whatever has
been collected and the decision to rebuild is a decision about the study, taken with a
person, not an edit.
