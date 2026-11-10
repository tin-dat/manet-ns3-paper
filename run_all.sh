#!/bin/bash
# Run all simulations of the paper (SS-I and SS-II) with several seeds.
# Usage (from the ns-3 root directory):
#   bash run_all.sh                 # 10 runs, 2 parallel jobs
#   RUNS=3 JOBS=4 bash run_all.sh   # quick test: 3 runs, 4 parallel jobs
# Each run writes its own CSV in results/ so it is safe to run in parallel
# and safe to resume (finished runs are skipped).

RUNS=${RUNS:-10}
JOBS=${JOBS:-2}
OUT=results

mkdir -p "$OUT"

echo "Building manet-paper..."
./ns3 build manet-paper || { echo "Build failed"; exit 1; }

BIN=$(find build/scratch -maxdepth 1 -type f -name "ns3*-manet-paper-*" | head -1)
if [ -z "$BIN" ]; then
    echo "Cannot find the manet-paper binary in build/scratch"
    exit 1
fi
export LD_LIBRARY_PATH="$PWD/build/lib:$LD_LIBRARY_PATH"
echo "Using binary: $BIN"

: > jobs.txt

# SS-I: vary node density, no pause
for p in OLSR AODV DSDV; do
  for n in 30 40 50 60 70 80 90 100; do
    for r in $(seq 1 "$RUNS"); do
      f="$OUT/SS-I_${p}_${n}_0_${r}.csv"
      [ -s "$f" ] && continue
      echo "$BIN --protocol=$p --nNodes=$n --pause=0 --run=$r --scenario=SS-I --csv=$f" >> jobs.txt
    done
  done
done

# SS-II: 50 nodes, vary pause time
for p in OLSR AODV DSDV; do
  for t in 5 10 15 20 25 30; do
    for r in $(seq 1 "$RUNS"); do
      f="$OUT/SS-II_${p}_50_${t}_${r}.csv"
      [ -s "$f" ] && continue
      echo "$BIN --protocol=$p --nNodes=50 --pause=$t --run=$r --scenario=SS-II --csv=$f" >> jobs.txt
    done
  done
done

echo "Jobs to run: $(wc -l < jobs.txt)  (parallel: $JOBS)"
xargs -P "$JOBS" -I{} bash -c "{}" < jobs.txt | tee -a run_log.txt
echo "Done. Results are in $OUT/. Next: python3 analyze.py"
