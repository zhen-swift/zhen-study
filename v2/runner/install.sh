#!/bin/bash
# Installs study 2's runner on the Mac mini. Run as root (sudo -n under the temporary setup grant), by /study-setup.
# Idempotent: re-running it changes nothing that is already right.
set -euo pipefail
S=/Users/Shared/zhen-study2
[ "$(id -u)" = 0 ] || { echo "run as root" >&2; exit 1; }
id zhenstudy >/dev/null || { echo "zhenstudy is missing" >&2; exit 1; }
for d in queue running done failed data logs history; do mkdir -p "$S/$d"; done
chown zhenstudy:staff "$S"/{queue,running,done,failed,data,logs,history}
chmod 2775 "$S"/{queue,running,done,failed,data,logs,history}
P=/Library/LaunchDaemons/dev.zhen.study2.runner.plist
install -m 0644 -o root -g wheel "$S/repo/v2/runner/dev.zhen.study2.runner.plist" "$P"
launchctl bootout system/dev.zhen.study2.runner 2>/dev/null || true
launchctl bootstrap system "$P"
echo "runner installed: $(launchctl print system/dev.zhen.study2.runner | awk -F'= ' '/^\tstate/{print $2; exit}')"
