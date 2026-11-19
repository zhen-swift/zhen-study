g9() {
  echo "\n== G9 (JC half) — one scan per row of change 9's table; each flag's value must be in the artifact."
  rm -f $ZHEN_HISTORY
  echo "row 8, --version: $($Z --version)"
  scan --reach-percentile 0.9 --first-scan-wait 1200ms --reach-cap 4s --reach-min-samples 10 \
    --reach-device-min-samples 3 --reach-margin 1.5 --reach-miss-backoff 3 --expected-attempts-step 400ms --expected-attempts-cap 7 > $OUT/g9-1.json
  echo "row 1: $(jq -c '.run.reach' $OUT/g9-1.json)"
  # F3's row: the window that makes an address expected. 1ms forgets the scan just above; 1s
  # would not, since the next scan starts ~50 ms after the last one finishes (R5, 2026-10-16).
  scan --expected-window 1ms > $OUT/g9-1w.json
  echo "row 1w: $(jq -c '.run.reach | {expected_window_millis, expected_count}' $OUT/g9-1w.json) (default: $(jq -c '.run.reach.expected_window_millis' $OUT/g9-1.json))"
  # F7's row: the rule for a known network's unexpected cold addresses.
  scan --unexpected-cold first-scan > $OUT/g9-1u.json
  echo "row 1u: $(jq -c '.run.reach | {unexpected_cold, known_network}' $OUT/g9-1u.json) (default: $(jq -c '.run.reach.unexpected_cold' $OUT/g9-1.json))"
  # F8's row: how long the scan listened after its all-nodes echo, and by which rule.
  scan --ipv6-window 2s > $OUT/g9-1i.json
  scan --ipv6-window 0 > $OUT/g9-1i0.json
  echo "row 1i: 2s $(jq -c '.run.ipv6_window' $OUT/g9-1i.json), 0 $(jq -c '.run.ipv6_window' $OUT/g9-1i0.json) (default: $(jq -c '.run.ipv6_window' $OUT/g9-1.json))"
  scan --reach learned --no-neighbor-watch > $OUT/g9-2.json
  echo "row 2: $(jq -c '{policy: .run.reach.policy, neighbor_watch: .run.neighbor_watch}' $OUT/g9-2.json)"
  local before=$(shasum -a 256 $ZHEN_HISTORY | cut -d' ' -f1)
  scan --no-history > $OUT/g9-3.json
  echo "row 3: $(jq -c '{first_scan: .run.reach.first_scan, history_samples: .run.reach.history_samples, history_read: .run.reach.history_read}' $OUT/g9-3.json) store unchanged: $([[ $before == $(shasum -a 256 $ZHEN_HISTORY | cut -d' ' -f1) ]] && echo yes || echo NO)"
  cold; scan > $OUT/g9-4.json
  echo "rows 4–6: $(jq -c '{stage: (.run.timing.stages[0] | {attempts, concurrency, retransmit_budget_millis, tail_budget_millis}), hosts: [.devices[] | {a: .addresses[0], via: .discovered_via, found_after_millis, first_contact_millis, first_contact_cold}]}' $OUT/g9-4.json)"
  sudo -n /usr/bin/env ZHEN_HISTORY=$OUT/root-history.ndjson $Z scan --cidr $CIDR --iface $IFACE --discovery-only --json --quiet > $OUT/g9-7.json \
    || echo "row 7: sudo -n failed — no rule for this exact command (is OUT the directory the rule names?)"
  echo "row 7 (root): $(jq -c '{engine: .run.engine, tool: .run.tool, via: ([.devices[].discovered_via[]] | group_by(.) | map({(.[0]): length}) | add)}' $OUT/g9-7.json)"
  echo "row 8: $(jq -c '.run.tool' $OUT/g9-1.json)"
}
