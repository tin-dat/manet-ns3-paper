#!/bin/bash
# Sweep the two-node range test and report the largest distance at which frames
# still arrive. Usage (from the ns-3 root, after copying range_test.cc to scratch/):
#
#   bash range_test.sh
#   NS3_DIR=~/ns-3-dev bash range_test.sh
#
# The output is written to range_test_results.txt and printed at the end.

set -u

NS3_DIR=${NS3_DIR:-}
if [ -n "$NS3_DIR" ]; then
    cd "$NS3_DIR" || { echo "Cannot cd to NS3_DIR=$NS3_DIR"; exit 1; }
fi

./ns3 build range-test || { echo "Build failed"; exit 1; }

BIN=$(find build/scratch -maxdepth 1 -type f -name "ns3*-range-test-*" | head -1)
if [ -z "$BIN" ]; then
    echo "Cannot find the range-test binary in build/scratch"
    exit 1
fi
export LD_LIBRARY_PATH="$PWD/build/lib:${LD_LIBRARY_PATH:-}"

OUTFILE=range_test_results.txt
: > "$OUTFILE"

# Coarse sweep first, then bisect between the last reachable and first
# unreachable distance to get within ~10 m.
reachable_max=0
unreachable_min=""

echo "Sweeping distance (coarse step 50 m)..."
for d in $(seq 50 50 1500); do
    line=$("$BIN" --distance="$d")
    echo "$line" >> "$OUTFILE"
    ok=$(echo "$line" | sed -n 's/.*reachable=\([01]\).*/\1/p')
    if [ "${ok:-0}" = "1" ]; then
        reachable_max=$d
    elif [ -z "$unreachable_min" ]; then
        unreachable_min=$d
        break
    fi
done

if [ -n "$unreachable_min" ]; then
    echo "Bisecting between ${reachable_max} m and ${unreachable_min} m..."
    lo=$reachable_max
    hi=$unreachable_min
    while [ $((hi - lo)) -gt 10 ]; do
        mid=$(( (lo + hi) / 2 ))
        line=$("$BIN" --distance="$mid")
        echo "$line" >> "$OUTFILE"
        ok=$(echo "$line" | sed -n 's/.*reachable=\([01]\).*/\1/p')
        if [ "${ok:-0}" = "1" ]; then
            lo=$mid
        else
            hi=$mid
        fi
    done
    reachable_max=$lo
fi

echo
echo "Measured radio range: about ${reachable_max} m"
echo "  (Tx 7.5 dBm, Friis 2.412 GHz, 802.11b 2 Mbps broadcast)"
echo "  Area is 300 x 1500 m; each node covers a band of width min(2R, 300) m."
echo "  Per-run detail: $OUTFILE"
