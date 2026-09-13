#!/bin/zsh
# The collection driver as one command: start, stop, status.
#
# `collect.py` is the driver and knows what to do; this script only knows where it
# lives and how it is started for the real thing, so that after a reboot or a crash the
# restart is `Study/harness/collection.sh start` and not a reconstruction of twelve
# flags from a log. Every flag below is the protocol's default, spelled out so the
# record shows what ran rather than what the defaults happened to be that day.
#
# Runs from the collection worktree, never from a checkout anybody works in:
# `provenance.py` aborts a block on a dirty tree, and it is right to.
#
# start   refuses if a driver is already running, or if COLLECTION-STOPPED.txt exists —
#         that file is a halt that a person has not yet acknowledged, and a driver that
#         restarts into a broken apparatus and quietly records nothing is the failure
#         the file exists to prevent. Deleting it is the acknowledgement.
# stop    SIGTERM: the driver finishes its current wait and exits 0, releasing its
#         caffeinate assertion. A block in flight is finished first. Writes
#         COLLECTION-PAUSED so the watchdog knows this was on purpose.
# status  the census, from the data.
set -u
W=/Users/jc/Dev/InfinityCastle-collection
D=$W/Study/data
PY=/usr/bin/python3
BIN=$W/Packages/netsanity-cli/.build/release/netsanity

case "${1:-status}" in
  start)
    if pgrep -f "$W/Study/harness/collect.py" >/dev/null; then
      echo "a driver is already running (pid $(pgrep -f "$W/Study/harness/collect.py" | head -1))"; exit 1
    fi
    if [ -f "$D/COLLECTION-STOPPED.txt" ]; then
      echo "COLLECTION-STOPPED.txt exists; read it, fix the cause, delete it, then start:"; sed 's/^/  /' "$D/COLLECTION-STOPPED.txt"; exit 1
    fi
    if [ -n "$(git -C "$W" status --porcelain)" ]; then
      echo "the collection worktree is dirty; a block would abort on provenance:"; git -C "$W" status --short; exit 1
    fi
    rm -f "$D/COLLECTION-PAUSED"
    nohup "$PY" "$W/Study/harness/collect.py" \
      --out "$D/runs.ndjson" \
      --log "$D/collect.log" \
      --status "$D/collect-status.json" \
      --alarm "$D/COLLECTION-STOPPED.txt" \
      --cidr 192.168.64.0/24 --iface bridge100 \
      --netsanity "$BIN" \
      --cooldown 10.0 \
      --control-host 192.168.64.4 --control-host 192.168.64.6 \
      --blocks-per-stratum 30 --minimum-days 7 \
      --flush-policy block \
      > "$D/collect.launchd.out" 2> "$D/collect.launchd.err" &
    echo "driver started, pid $!  (apparatus $(git -C "$W" rev-parse --short HEAD))"
    ;;
  stop)
    pid=$(pgrep -f "$W/Study/harness/collect.py" | head -1)
    if [ -z "$pid" ]; then echo "no driver running"; exit 0; fi
    date '+%Y-%m-%dT%H:%M:%S stopped on request' > "$D/COLLECTION-PAUSED"
    kill -TERM "$pid" && echo "SIGTERM sent to $pid; it finishes the current block or wait, then exits"
    ;;
  status)
    if pgrep -f "$W/Study/harness/collect.py" >/dev/null; then echo "driver: running (pid $(pgrep -f "$W/Study/harness/collect.py" | head -1))"; else echo "driver: not running"; fi
    [ -f "$D/COLLECTION-STOPPED.txt" ] && echo "HALTED: $(head -3 "$D/COLLECTION-STOPPED.txt" | tr '\n' ' ')"
    [ -f "$D/COLLECTION-PAUSED" ] && echo "paused: $(cat "$D/COLLECTION-PAUSED")"
    if [ -f "$D/collect-status.json" ]; then
      "$PY" - "$D/collect-status.json" <<'PYEOF'
import json, sys
s = json.load(open(sys.argv[1]))
print(f"state: {s['state']} — {s['detail']}  (as of {s['updated']})")
print(f"runs {s['runs']}, excluded {s['excluded_runs']} ({s['exclusion_rate']*100:.2f}%"
      f"{', OVER CEILING' if s['exclusion_over_ceiling'] else ''}), partial blocks {s['partial_blocks']}")
print("complete per stratum:", "  ".join(f"{k} {v}/{s['target_per_stratum']}" for k, v in s['complete'].items()),
      f" | days {s['distinct_days']}/{s['protocol_minimum_days']}")
PYEOF
    else
      echo "no status file yet"
    fi
    ;;
  *) echo "usage: collection.sh {start|stop|status}"; exit 2 ;;
esac
