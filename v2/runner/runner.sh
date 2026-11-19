#!/bin/bash
# Study 2's job runner on the Mac mini. No Claude, no tokens: it runs the jobs it is given, one at a time.
# Run by the LaunchDaemon dev.zhen.study2.runner as zhenstudy, kept alive; each pass runs at most one job.
#
#   /Users/Shared/zhen-study2/
#     repo/      the zhen-study clone, owned by the admin account, pinned by /study-run. Read-only to this runner
#     queue/     jobs waiting, one JSON file each, run in name order:
#                {"id": "...", "arm": "testbed|home", "minutes": 12, "argv": ["harness/collect.py", "--once", ...],
#                 "env": {"ZHEN_HISTORY": "..."}}
#     running/   the job in progress (at most one)
#     done/ failed/   finished jobs, each with its .log beside it
#     data/      what the harness writes; pulled to the MacBook by /study-sync
#     logs/runner.ndjson   one line per decision and per job, with zone, UTC offset and repo commit
#     PAUSE      if this file exists, nothing new starts
set -o pipefail   # not -u: macOS bash 3.2 treats an empty array as unset
S=/Users/Shared/zhen-study2
R="$S/repo"
export PATH=/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin PYTHONDONTWRITEBYTECODE=1
# repo/ belongs to the admin account and this runs as zhenstudy, so git refuses it ("dubious ownership") unless
# told otherwise. Command-scope config, inherited by every job, so the harness's provenance checks can read it too.
export GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=safe.directory GIT_CONFIG_VALUE_0="$R"
# Jobs run under Apple's python3, not Homebrew's (2026-11-19, S2). Homebrew's runs as an app (Python.app), and macOS
# hides hardware addresses from an app without Local Network permission and from everything it starts: under it,
# `arp -an` prints nothing, and zhen, which reads the same table, would lose its neighbour evidence and watch.
PY=/usr/bin/python3
cd "$S" || exit 1
mkdir -p queue running done failed data logs
log() { printf '%s\n' "$1" >> logs/runner.ndjson; }
now() { date '+%FT%T%z'; }

# A job left in running/ means the runner died mid-job: never re-run it silently, it may have half-written.
for j in running/*.json; do
  [ -e "$j" ] || continue
  mv "$j" failed/ && log "{\"t\":\"$(now)\",\"event\":\"interrupted\",\"job\":\"$(basename "$j")\"}"
done

[ -e PAUSE ] && { sleep 60; exit 0; }

zone="$(readlink /etc/localtime | sed 's#.*/zoneinfo/##')"
ntp="$(sntp -t 3 time.apple.com 2>/dev/null | awk 'END{print $1}')"
commit="$(git -C "$R" rev-parse --short HEAD 2>/dev/null || echo none)"

for j in queue/*.json; do
  [ -e "$j" ] || { sleep 60; exit 0; }            # empty queue
  arm="$(jq -r .arm "$j")"; mins="$(jq -r '.minutes // 30' "$j")"
  verdict="$("$PY" "$R/v2/runner/window.py" "$arm" "$mins" "$ntp")"; code=$?
  [ $code -eq 0 ] && break                         # this job may run now
  [ $code -eq 2 ] && { log "$verdict"; mv "$j" failed/; }
  j=""                                             # not now: try the next job (a testbed job can run by day)
done
[ -n "${j:-}" ] && [ -e "$j" ] || { sleep 60; exit 0; }

if [ "$arm" = home ]; then                         # the home network must still be the one config.json names
  want="$(jq -r .home.cidr "$R/v2/config.json")"; ifc="$(jq -r .home.interface "$R/v2/config.json")"
  ip="$(ipconfig getifaddr "$ifc")"
  "$PY" -c "import ipaddress,sys; sys.exit(ipaddress.ip_address('$ip') not in ipaddress.ip_network('$want'))" 2>/dev/null \
    || { log "{\"t\":\"$(now)\",\"event\":\"refused\",\"job\":\"$(basename "$j")\",\"why\":\"$ifc is ${ip:-down}, not in $want\"}"; mv "$j" failed/; exit 0; }
fi

name="$(basename "$j" .json)"; mv "$j" running/
log "{\"t\":\"$(now)\",\"event\":\"start\",\"job\":\"$name\",\"arm\":\"$arm\",\"zone\":\"$zone\",\"repo\":\"$commit\",\"window\":$verdict}"
envs=(); while IFS= read -r kv; do envs+=("$kv"); done < <(jq -r '.env // {} | to_entries[] | "\(.key)=\(.value)"' "running/$name.json")
args=(); while IFS= read -r a; do args+=("$a"); done < <(jq -r '.argv[]' "running/$name.json")
( cd "$R" && env "${envs[@]}" "$PY" "${args[@]}" ) > "running/$name.log" 2>&1; rc=$?
dest=done; [ $rc -eq 0 ] || dest=failed
mv "running/$name.json" "running/$name.log" "$dest/"
log "{\"t\":\"$(now)\",\"event\":\"end\",\"job\":\"$name\",\"exit\":$rc,\"to\":\"$dest\"}"
