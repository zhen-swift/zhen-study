#!/bin/bash
# Gate 0.3's privileged half, and the capture its unprivileged half never had.
#
# One `sudo`, seven runs. Root on this machine is a Touch ID prompt rather than an
# unattended grant, so every privileged invocation costs a person a finger on a sensor.
# That makes the number of sudo calls a design constraint: this script exists so the
# whole gate costs one instead of seven.
#
# It is NOT the harness and nothing it prints is a measurement. `run_block.py` owns
# wall clock, and the durations recorded here are diagnostics for sizing the runs, not
# evidence for any hypothesis. What this script produces that the study needs is a
# packet capture per run, from which the engine each tool actually used is read —
# ARP where ARP is expected — rather than taken from either tool's own claim.
#
# Run:  sudo bash Study/testbed/gate-0.3-privileged.sh
set -u

REPO=/Users/jc/Dev/InfinityCastle
NS=/Users/jc/Dev/InfinityCastle-collection/Packages/netsanity-cli/.build/release/netsanity
NMAP=/opt/homebrew/bin/nmap
CIDR=192.168.64.0/24
IFACE=bridge100
OWNER=jc
WATCHDOG=420                     # seconds; -T2 across a /24 is the one that could sit

CAP=$REPO/Study/data/captures/gate-0.3
RAW=$REPO/Study/data/raw/gate-0.3
STORE=$REPO/Study/data/stores

if [ "$(id -u)" -ne 0 ]; then
    echo "this script must be run as root: sudo bash $0" >&2
    exit 2
fi

# Created AS THE OWNER, not as root. The unprivileged half of the gate runs under
# `sudo -u $OWNER` and writes its own nmap XML, so a root-owned directory makes that
# run fail with "Permission denied (13)" — which it did, the first time this ran, and
# looked briefly like a finding about nmap rather than a bug in this script.
sudo -u "$OWNER" mkdir -p "$CAP" "$RAW" "$STORE"

# ── provenance, so the artifacts describe themselves ──────────────────────────────
{
    echo "date_utc:   $(date -u +%Y-%m-%dT%H:%M:%SZ)"
    echo "host:       $(sw_vers -productName) $(sw_vers -productVersion) $(sw_vers -buildVersion) $(sysctl -n hw.model)"
    echo "iface:      $IFACE $(ipconfig getifaddr $IFACE 2>/dev/null)"
    echo "cidr:       $CIDR"
    echo "nmap:       $($NMAP --version | head -1)"
    echo "nmap_sha:   $(shasum -a 256 $NMAP | cut -d' ' -f1)"
    echo "netsanity:  $($NS --version)"
    echo "ns_sha:     $(shasum -a 256 $NS | cut -d' ' -f1)"
    echo "ns_path:    $NS"
} > "$RAW/provenance.txt"

# ── one run, bracketed by its own capture ─────────────────────────────────────────
#
# The neighbour table is flushed immediately before each run. Without it the first
# run populates the cache and every run after it is a different experiment — and the
# whole question here is which engine a tool reaches for, which is exactly what a warm
# cache lets it skip.
run_with_capture() {
    local name=$1; shift
    local pcap="$CAP/$name.pcap"

    # `ONLY=a,b` re-runs a subset. Root here is a Touch ID prompt, so a re-run of one
    # failed run must not cost a re-run of the six that worked.
    if [ -n "${ONLY:-}" ] && ! echo ",$ONLY," | grep -q ",$name,"; then
        echo "  $name: skipped (ONLY=$ONLY)"
        return 0
    fi

    tcpdump -i "$IFACE" -n -s 0 -U -w "$pcap" > "$RAW/$name.tcpdump.log" 2>&1 &
    local td=$!
    sleep 2                                    # let BPF attach before anything is sent

    arp -a -d > /dev/null 2>&1

    local start=$(python3 -c 'import time; print(time.monotonic())')
    "$@" > "$RAW/$name.stdout" 2> "$RAW/$name.stderr" &
    local job=$!
    local waited=0
    while kill -0 $job 2>/dev/null && [ $waited -lt $WATCHDOG ]; do
        sleep 1
        waited=$((waited + 1))
    done
    if kill -0 $job 2>/dev/null; then
        kill -TERM $job 2>/dev/null
        echo "watchdog: killed after ${WATCHDOG}s" >> "$RAW/$name.stderr"
    fi
    wait $job 2>/dev/null
    local status=$?
    local end=$(python3 -c 'import time; print(time.monotonic())')

    sleep 2                                    # let the tail of the exchange land
    kill -INT $td 2>/dev/null
    wait $td 2>/dev/null

    {
        echo "name:     $name"
        echo "argv:     $*"
        echo "exit:     $status"
        echo "seconds:  $(python3 -c "print(round($end - $start, 3))")   # DIAGNOSTIC, not a measurement"
    } > "$RAW/$name.run"
    echo "  $name: exit $status, $(python3 -c "print(round($end - $start, 2))")s, $(du -h "$pcap" | cut -f1) capture"
}

echo "gate 0.3, privileged half. seven runs, one sudo."
echo

echo "privileged netsanity"
run_with_capture ns-priv \
    env NETSANITY_HISTORY="$STORE/gate03-ns-priv.ndjson" \
    "$NS" scan --cidr "$CIDR" --iface "$IFACE" --json --quiet --no-color --discovery-only

echo "privileged nmap, every template in the matrix"
for T in T2 T3 T4 T5; do
    run_with_capture "nmap-priv-$T" \
        "$NMAP" -sn "$CIDR" -oX "$RAW/nmap-priv-$T.xml" --reason "-$T"
done

# The unprivileged pair runs here too, under a capture, because 0.3 closed the ICMP
# question from the kernel's descriptor tables and said plainly that only a capture
# removes the residual. There is no unprivileged path to a capture on this machine, so
# the only way to take one is from inside this script, dropping back to the owner for
# the run itself. If these show ICMP from nmap, the descriptor evidence was wrong and
# that is worth knowing loudly.
echo "unprivileged pair, for the capture 0.3 could never take"
run_with_capture nmap-unpriv-T3 \
    sudo -u "$OWNER" "$NMAP" -sn "$CIDR" -oX "$RAW/nmap-unpriv-T3.xml" --reason -T3
run_with_capture ns-unpriv \
    sudo -u "$OWNER" env NETSANITY_HISTORY="$STORE/gate03-ns-unpriv.ndjson" \
    "$NS" scan --cidr "$CIDR" --iface "$IFACE" --json --quiet --no-color --discovery-only

chown -R "$OWNER" "$CAP" "$RAW" "$STORE"
echo
echo "done. artifacts under Study/data/{captures,raw}/gate-0.3, owned by $OWNER."
