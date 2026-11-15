#!/bin/bash
# Run several seeds IN PARALLEL, one process per seed, each pinned to its own CPU core.
# Needs a VM with >= 4 vCPUs (core 0 is left free for the operating system).
#
# Usage (from ~/ns-3-dev):
#   OUT=results EXTRA="--bcastAtDataRate=false" SEEDS="4 5 6" bash par.sh
#   OUT=results_u LOGDIR=logs_u EXTRA="--speedUniform=true --bcastAtDataRate=false" SEEDS="1 2 3" bash par.sh
#
# Each process handles one seed over all of SS-I and SS-II (OLSR, DSDV, then AODV).
# Finished runs are skipped, so you can stop and start again at any time.

cd ~/ns-3-dev || exit 1
OUT=${OUT:-results}
LOGDIR=${LOGDIR:-logs}
EXTRA=${EXTRA:-}
SEEDS=${SEEDS:-"4 5 6"}

NCPU=$(nproc)
NSEEDS=$(echo $SEEDS | wc -w)
if [ "$NCPU" -le "$NSEEDS" ]; then
    echo "The VM has $NCPU vCPUs; need at least $((NSEEDS + 1)) for $NSEEDS parallel seeds."
    exit 1
fi

./ns3 build manet-paper || { echo "Build failed"; exit 1; }
mkdir -p "$OUT" "$LOGDIR"

core=1
for s in $SEEDS; do
    SKIP_BUILD=1 OUT="$OUT" LOGDIR="$LOGDIR" EXTRA="$EXTRA" RUN_FROM=$s RUN_TO=$s JOBS=1 \
    setsid nohup taskset -c $core nice -n 19 bash -c \
      'for sc in SS-I SS-II; do for p in OLSR DSDV AODV; do bash run_part.sh $sc $p; done; done' \
      > "par_seed${s}.out" 2>&1 < /dev/null &
    core=$((core + 1))
done
echo "Started $NSEEDS parallel processes (seeds: $SEEDS). Progress: ls $OUT | wc -l"
