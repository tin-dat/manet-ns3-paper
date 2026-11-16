#!/bin/bash
# PART 1 - quick sanity check (3 short runs).
# Usage (from the ns-3 root): bash check.sh
#
# Expected, with the default parameters:
#   - sent is close to 5980-6000 for every protocol
#   - OLSR PDR is high (~85-95%)
#   - "routingOrig" is lower than "routingPkts" at 30 nodes, and much lower
#     at higher densities (per-hop counting vs. originated-only counting)
#
# This script deliberately avoids /usr/bin/time, which is missing from many
# minimal containers.

set -u

NS3_DIR=${NS3_DIR:-}
if [ -n "$NS3_DIR" ]; then
    cd "$NS3_DIR" || { echo "Cannot cd to NS3_DIR=$NS3_DIR"; exit 1; }
fi

./ns3 build manet-paper || { echo "Build failed"; exit 1; }

for p in OLSR AODV DSDV; do
    echo "=== $p (30 nodes, no pause) ==="
    start=$(date +%s)
    ./ns3 run --no-build "manet-paper --protocol=$p --nNodes=30 --pause=0 --run=1 --csv=check_$p.csv"
    echo "wall time: $(( $(date +%s) - start )) s"
done

echo
echo "Done. If sent is ~5980 and OLSR PDR is high, continue with run_part.sh."
