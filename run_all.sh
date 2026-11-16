#!/bin/bash
# Run all simulations of the paper (SS-I and SS-II) with several seeds.
# Usage (from the ns-3 root directory):
#   bash run_all.sh                 # seeds 1..6, 2 parallel jobs (matches analyze.py)
#   RUNS=2 JOBS=4 bash run_all.sh   # quick test
# Each run writes its own CSV in results/ so it is safe to run in parallel
# and safe to resume (finished runs, and runs with a truncated CSV, are redone).
#
# If you only want the analysis to succeed, seeds 1..6 are enough; run_part.sh
# is the recommended way to add optional extra seeds.

set -u

RUNS=${RUNS:-6}
JOBS=${JOBS:-2}
OUT=results
LOGDIR=${LOGDIR:-logs}
NS3_DIR=${NS3_DIR:-}

if [ -n "$NS3_DIR" ]; then
    cd "$NS3_DIR" || { echo "Cannot cd to NS3_DIR=$NS3_DIR"; exit 1; }
fi

mkdir -p "$OUT" "$LOGDIR"

echo "Building manet-paper..."
./ns3 build manet-paper || { echo "Build failed"; exit 1; }

BIN=$(find build/scratch -maxdepth 1 -type f -name "ns3*-manet-paper-*" | head -1)
if [ -z "$BIN" ]; then
    echo "Cannot find the manet-paper binary in build/scratch"
    exit 1
fi
export LD_LIBRARY_PATH="$PWD/build/lib:${LD_LIBRARY_PATH:-}"
echo "Using binary: $BIN"

# See run_part.sh: require a header plus one complete data row.
EXPECTED_FIELDS=19
csv_is_complete() {
    local f="$1"
    [ -s "$f" ] || return 1
    local nrows nfields
    nrows=$(awk 'END{print NR}' "$f" 2>/dev/null)
    [ "${nrows:-0}" -ge 2 ] || return 1
    nfields=$(awk -F, 'NR==2{print NF}' "$f" 2>/dev/null)
    [ "${nfields:-0}" = "$EXPECTED_FIELDS" ]
}

: > jobs.txt

# SS-I: vary node density, no pause
for p in OLSR AODV DSDV; do
  for n in 30 40 50 60 70 80 90 100; do
    for r in $(seq 1 "$RUNS"); do
      f="$OUT/SS-I_${p}_${n}_0_${r}.csv"
      csv_is_complete "$f" && continue
      echo "$BIN --protocol=$p --nNodes=$n --pause=0 --run=$r --scenario=SS-I --csv=$f" >> jobs.txt
    done
  done
done

# SS-II: 50 nodes, vary pause time
for p in OLSR AODV DSDV; do
  for t in 5 10 15 20 25 30; do
    for r in $(seq 1 "$RUNS"); do
      f="$OUT/SS-II_${p}_50_${t}_${r}.csv"
      csv_is_complete "$f" && continue
      echo "$BIN --protocol=$p --nNodes=50 --pause=$t --run=$r --scenario=SS-II --csv=$f" >> jobs.txt
    done
  done
done

echo "Jobs to run: $(wc -l < jobs.txt)  (parallel: $JOBS)"
nice -n 10 xargs -P "$JOBS" -I{} bash -c "{}" < jobs.txt | tee -a run_log.txt
echo "Done. Results are in $OUT/. Next: python3 analyze.py"
