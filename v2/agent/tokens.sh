#!/bin/bash
# Stores the study agent's two tokens for zhenstudy, without echoing them. Run by JC, as zhenstudy:
#   sudo -u zhenstudy -H bash ~zhenstudy/Dev/InfinityCastle/zhen-study/v2/agent/tokens.sh
#
# Claude: run `claude setup-token` (as zhenstudy, or any account of JC's) and paste what it prints.
# GitHub: a fine-grained token for zhen-swift/zhen-study (Contents read/write, Pull requests read/write,
#         Issues read) and zhen-swift/zhen-core (Contents read).
set -euo pipefail
[ "$(id -un)" = zhenstudy ] || { echo "run this as zhenstudy" >&2; exit 1; }
dir="$HOME/.config/zhen"
mkdir -p "$dir" && chmod 700 "$dir"
umask 077
read -rsp "Claude token: " t && echo && printf %s "$t" > "$dir/claude-token" && unset t
read -rsp "GitHub token: " g && echo && printf %s "$g" > "$dir/gh-token" && unset g
chmod 600 "$dir/claude-token" "$dir/gh-token"
GH_TOKEN="$(cat "$dir/gh-token")" /opt/homebrew/bin/gh api user --jq '"GitHub: signed in as " + .login'
echo "Both tokens stored."
