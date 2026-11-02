#!/bin/bash
# The study 2 agent's only entry point. See v2/RUN.md.
#   start.sh install   once, by JC as zhenstudy: installs the hourly LaunchAgent and starts the first tick
#   start.sh tick      what launchd runs every hour
# While the run is stopped, a tick checks the stop's condition in shell and does not start Claude.
set -euo pipefail

REPO="$(cd "$(dirname "$0")/../.." && pwd)"
V2="$REPO/v2"
STATE="$V2/STATE"
WORK="$HOME/.zhen-study2"
LOCK="$WORK/agent.lock"
ID="dev.zhen.study2.agent"
PLIST="$HOME/Library/LaunchAgents/$ID.plist"
ZHEN="/usr/local/zhen-study2/zhen-0.8.0"
export PATH="/opt/homebrew/bin:$HOME/.local/bin:/Library/TeX/texbin:/usr/bin:/bin:/usr/sbin:/sbin"

mkdir -p "$WORK/logs" "$HOME/zhen-study2-private" "$HOME/Library/LaunchAgents"
chmod 700 "$HOME/zhen-study2-private"
log() { printf '%s %s\n' "$(date '+%F %T %Z')" "$*" >> "$WORK/logs/start.log"; }
set_state() { printf '%s\n%s\n' "$1" "$2" > "$STATE"; log "state -> $1"; }

case "${1:-tick}" in
install)
  gh auth setup-git
  sed -e "s#__REPO__#$REPO#g" -e "s#__HOME__#$HOME#g" "$V2/agent/$ID.plist" > "$PLIST"
  launchctl bootout "gui/$(id -u)/$ID" 2>/dev/null || true
  launchctl bootstrap "gui/$(id -u)" "$PLIST"
  echo "Installed $ID. The first tick is running; progress is in v2/LEDGER.md on branch study2."
  ;;

tick)
  shlock -f "$LOCK" -p $$ || { log "tick skipped: agent already running"; exit 0; }
  trap 'rm -f "$LOCK"' EXIT
  cd "$REPO"
  git pull --ff-only -q 2>>"$WORK/logs/start.log" || log "pull failed, continuing on local state"

  state="$(head -n1 "$STATE")"
  case "$state" in
    DONE|BLOCKED*)
      exit 0 ;;
    WAITING_FREEZE)
      pr="$(sed -n 2p "$STATE" | grep -Eo '[0-9]+' | head -n1)"
      if gh pr view "$pr" --json comments \
           --jq '.comments[] | select(.author.login == "JCTec") | .body' \
         | grep -Eqx '[[:space:]]*/freeze[[:space:]]*'; then
        set_state RUNNING "/freeze seen on PR $pr at $(date '+%F %T %Z'). S6 is next."
      else
        exit 0
      fi ;;
    WAITING_ROOT)
      if sudo -n -l "$ZHEN" >/dev/null 2>&1; then
        set_state RUNNING "zhen root grant present at $(date '+%F %T %Z'). S7 is next."
      else
        exit 0
      fi ;;
  esac

  export CLAUDE_CODE_OAUTH_TOKEN="$(cat "$HOME/.config/zhen/claude-token")"
  log "starting agent"
  claude -p "$(cat "$V2/agent/PROMPT.md")" \
    --settings "$V2/agent/settings.json" \
    --output-format stream-json --verbose \
    >> "$WORK/logs/agent-$(date +%F).ndjson" 2>&1 || log "agent exited non-zero: $?"
  log "agent exited"
  ;;

*)
  echo "usage: start.sh install | tick" >&2; exit 2 ;;
esac
