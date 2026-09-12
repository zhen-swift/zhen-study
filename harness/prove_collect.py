"""Gate 3: kill the driver inside a block and prove the data is still right.

`collect.py` claims it survives being stopped and restarted without losing or
double-counting a block. That claim is worth exactly as much as the test behind it, and
the test has to interrupt a block *part way through* — stopping between blocks proves
nothing, because nothing is in flight.

Timing cannot be used to land the cut. A dry block is about two tenths of a second
(`run_block.py` skips the cooldown when the tools are stubbed, deliberately, so the
apparatus check stays fast), so any `sleep` overshoots by dozens of blocks — which is
what the first two attempts at this test did. So the cut is taken on the *line count* of
the append-only file instead: thirteen lines to a block, so line 32 is six conditions
into block 2, and it lands there every time regardless of how fast the machine is.

Both the driver and its `run_block.py` child get SIGKILL, which is what a power cut
does. SIGTERM would let the driver shut down tidily and would test the tidy path, and
the tidy path is not the one that worries anybody.

Run:  python3 Study/harness/prove_collect.py <scratch-dir>
"""
import collections, json, os, signal, subprocess, sys, time
from pathlib import Path

SP = Path(sys.argv[1]); REPO = Path("/Users/jc/Dev/InfinityCastle")
PY = str(REPO / "Study/.venv/bin/python"); F = SP / "int3.ndjson"
for p in SP.glob("int3*"): p.unlink()

def start():
    return subprocess.Popen(
        [PY, str(REPO / "Study/harness/collect.py"), "--dry-run", "--out", str(F),
         "--log", str(SP / "int3.log"), "--status", str(SP / "int3-status.json"),
         "--alarm", str(SP / "int3-ALARM.txt"), "--cooldown", "0", "--poll", "1",
         "--blocks-per-stratum", "30", "--minimum-days", "1", "--daily-quota", "30"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, cwd=REPO)

def lines():
    try: return sum(1 for _ in open(F))
    except FileNotFoundError: return 0

def shape():
    c = collections.defaultdict(set)
    for l in open(F):
        r = json.loads(l); c[r["block_id"]].add(r["condition_id"])
    return {b: len(v) for b, v in sorted(c.items())}

def census():
    out = subprocess.run([PY, str(REPO / "Study/harness/collect.py"), "--census",
                          "--dry-run", "--out", str(F)], capture_output=True, text=True,
                         cwd=REPO)
    return json.loads(out.stdout)

def kill_all(proc):
    try: os.kill(proc.pid, signal.SIGKILL)
    except ProcessLookupError: pass
    subprocess.run(["pkill", "-9", "-f", f"run_block.py --blocks 1 --out {F}"])
    while subprocess.run(["pgrep", "-f", f"run_block.py --blocks 1 --out {F}"],
                         capture_output=True).returncode == 0:
        time.sleep(0.05)

# The census is read by total rather than by stratum name: the first version read
# `complete["morning"]`, which proved the driver on the morning it was written and
# failed on the afternoon it was re-run, with nothing wrong in the driver.
def complete(c): return c["total_complete"]

# Cut in six conditions into block 2, i.e. line 32 of a 13-line-per-block file.
TARGET = 2 * 13 + 6
proc = start()
deadline = time.time() + 60
while time.time() < deadline:
    n = lines()
    if n >= TARGET:
        break
    time.sleep(0.002)
print(f"cutting in at {lines()} lines (block 2 is {lines() - 26}/13 done)")
kill_all(proc)

after_kill = shape()
print("\nfile after the kill:")
for b, n in after_kill.items():
    print(f"  block {b}: {'COMPLETE' if n == 13 else f'PARTIAL ({n}/13)'}")
c1 = census()
print(f"  census counts   : {complete(c1)} complete, "
      f"partial={c1['partial_blocks']}, runs={c1['runs']}")

print("\nrestarting...")
proc2 = start()
deadline = time.time() + 60
while time.time() < deadline and lines() < TARGET + 3 * 13:
    time.sleep(0.05)
kill_all(proc2)

after_restart = shape()
print("\nfile after the restart:")
for b, n in after_restart.items():
    print(f"  block {b}: {'COMPLETE' if n == 13 else f'PARTIAL ({n}/13)'}")
c2 = census()
print(f"  census counts   : {complete(c2)} complete, "
      f"partial={c2['partial_blocks']}, runs={c2['runs']}")

print("\nchecks:")
ok = True
partial_ids = [b for b, n in after_kill.items() if n != 13]
def check(label, cond):
    global ok
    ok = ok and cond
    print(f"  [{'ok ' if cond else 'FAIL'}] {label}")

check("the kill left exactly one partial block", len(partial_ids) == 1)
check("the census refused to count it", c1["partial_blocks"] == partial_ids)
check("the partial block is unchanged after the restart",
      after_restart.get(partial_ids[0]) == after_kill[partial_ids[0]])
check("the restart never reused the interrupted block id",
      max(after_restart) > max(after_kill))
check("no completed block lost records",
      all(after_restart[b] == 13 for b in after_kill if after_kill[b] == 13))
check("complete count rose by exactly the blocks the restart finished",
      complete(c2) - complete(c1)
      == sum(1 for b in after_restart if b not in after_kill and after_restart[b] == 13))
check("every record still parses", c2["runs"] == sum(after_restart.values()))
print("\nGATE:", "met" if ok else "NOT met")
