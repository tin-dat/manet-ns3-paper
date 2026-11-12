#!/bin/bash
# PART 1 - quick sanity check (about 3 short runs).
# Usage (from the ns-3 root): bash check.sh
# Expected: sent close to 5980, OLSR PDR high (~85-95%) with legacyPhy=true.

./ns3 build manet-paper || { echo "Build failed"; exit 1; }

for p in OLSR AODV DSDV; do
    echo "=== $p (30 nodes, no pause, legacyPhy=true) ==="
    /usr/bin/time -f "wall time: %e s" \
        ./ns3 run --no-build "manet-paper --protocol=$p --nNodes=30 --pause=0 --run=1 --legacyPhy=true --csv=check_$p.csv"
done

echo
echo "Done. If sent is ~5980 and OLSR PDR is high, continue with run_part.sh."
