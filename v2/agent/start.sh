#!/bin/bash
# The study 2 agent's entry point. See v2/RUN.md and v2/START.md.
#   sudo start.sh install   once, from the admin account: installs two LaunchDaemons that run as zhenstudy
#   start.sh tick           hourly (daemon dev.zhen.study2.agent): resumes the agent, or checks a stop's condition
#   start.sh collect        kept alive (daemon dev.zhen.study2.collect): runs the harness while the agent asks for it
# While the run is stopped, a tick checks the stop's condition in shell and does not start Claude.
set -euo pipefail

STUDY_USER="zhenstudy"
REPO="$(cd "$(dirname "$0")/../.." && pwd)"
V2="$REPO/v2"
ZHEN="/usr/local/zhen-study2/zhen-0.8.0"
DAEMONS="dev.zhen.study2.agent dev.zhen.study2.collect"
export PATH="/opt/homebrew/bin:/Library/TeX/texbin:/usr/bin:/bin:/usr/sbin:/sbin"

if [ "${1:-tick}" = install ]; then
  [ "$(id -u)" = 0 ] || { echo "install runs as root: sudo $0 install" >&2; exit 1; }
  home="$(dscl . -read "/Users/$STUDY_USER" NFSHomeDirectory | awk '{print $2}')"
  for f in claude-token gh-token; do
    [ -s "$home/.config/zhen/$f" ] || { echo "missing $home/.config/zhen/$f — run agent/tokens.sh first" >&2; exit 1; }
  done
  sudo -u "$STUDY_USER" -H mkdir -p "$home/.zhen-study2/logs" "$home/zhen-study2-private"
  sudo -u "$STUDY_USER" -H env GH_TOKEN="$(cat "$home/.config/zhen/gh-token")" /opt/homebrew/bin/gh auth setup-git
  for id in $DAEMONS; do
    sed -e "s#__REPO__#$REPO#g" -e "s#__HOME__#$home#g" -e "s#__USER__#$STUDY_USER#g" \
      "$V2/agent/$id.plist" > "/Library/LaunchDaemons/$id.plist"
    chown root:wheel "/Library/LaunchDaemons/$id.plist"; chmod 644 "/Library/LaunchDaemons/$id.plist"
    launchctl bootout "system/$id" 2>/dev/null || true
    launchctl bootstrap system "/Library/LaunchDaemons/$id.plist"
  done
  echo "Installed $DAEMONS. The first tick is running; progress is in v2/LEDGER.md on branch study2."
  exit 0
fi

[ "$(id -un)" = "$STUDY_USER" ] || { echo "run as $STUDY_USER" >&2; exit 1; }
WORK="$HOME/.zhen-study2"
mkdir -p "$WORK/logs"
log() { printf '%s %s\n' "$(date '+%F %T %Z')" "$*" >> "$WORK/logs/start.log"; }
set_state() { printf '%s\n%s\n' "$1" "$2" > "$V2/STATE"; log "state -> $1"; }
export GH_TOKEN="$(cat "$HOME/.config/zhen/gh-token")"

case "${1:-tick}" in
tick)
  LOCK="$WORK/agent.lock"
  shlock -f "$LOCK" -p $$ || { log "tick skipped: agent already running"; exit 0; }
  trap 'rm -f "$LOCK"' EXIT
  cd "$REPO"
  if [ "$(git branch --show-current)" != study2 ]; then
    git switch study2 2>/dev/null || git switch -c study2
    log "on branch study2"
  fi
  git pull --ff-only -q origin study2 2>>"$WORK/logs/start.log" || true

  state="$(head -n1 "$V2/STATE")"
  case "$state" in
    DONE|BLOCKED*) exit 0 ;;
    WAITING_FREEZE)
      pr="$(sed -n 2p "$V2/STATE" | grep -Eo '[0-9]+' | head -n1)"
      if gh pr view "$pr" --json comments \
           --jq '.comments[] | select(.author.login == "JCTec") | .body' \
         | grep -Eqx '[[:space:]]*/freeze[[:space:]]*'; then
        set_state RUNNING "/freeze seen on PR $pr at $(date '+%F %T %Z'). S6 is next."
      else exit 0; fi ;;
    WAITING_ROOT)
      if sudo -n -l "$ZHEN" >/dev/null 2>&1; then
        set_state RUNNING "zhen root grant present at $(date '+%F %T %Z'). S7 is next."
      else exit 0; fi ;;
  esac

  export CLAUDE_CODE_OAUTH_TOKEN="$(cat "$HOME/.config/zhen/claude-token")"
  log "starting agent"
  "$HOME/.local/bin/claude" -p "$(cat "$V2/agent/PROMPT.md")" \
    --settings "$V2/agent/settings.json" \
    --output-format stream-json --verbose \
    >> "$WORK/logs/agent-$(date +%F).ndjson" 2>&1 || log "agent exited non-zero"
  log "agent exited"
  ;;

collect)
  # The agent starts a collection by writing the harness argv, one argument per line, to collect.args,
  # and stops it by deleting the file. launchd restarts this every minute, so a crashed run resumes.
  ARGS="$WORK/collect.args"
  [ -s "$ARGS" ] || { sleep 60; exit 0; }
  cd "$REPO"
  args=(); while IFS= read -r a; do args+=("$a"); done < "$ARGS"
  log "collect: ${args[*]}"
  exec /usr/bin/python3 "${args[@]}"
  ;;

*) echo "usage: start.sh install | tick | collect" >&2; exit 2 ;;
esac
