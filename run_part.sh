#!/bin/bash
# PART 2 - run ONE scenario for ONE protocol (a small, resumable chunk).
#
# Usage (from the ns-3 root):
#   bash run_part.sh <SS-I|SS-II> <OLSR|AODV|DSDV>
#
# Optional environment variables:
#   RUN_FROM=1 RUN_TO=10   seeds to run (default 1..10)
#   JOBS=1                 parallel processes (keep <= CPUs given to the VM)
#   OUT=results_u          output directory for the CSV files (default: results)
#   LOGDIR=logs_u          log directory (default: logs)
#   EXTRA="--speedUniform=true"   extra options for manet-paper
#
# Examples:
#   bash run_part.sh SS-I OLSR                        # 8 node counts x 10 seeds
#   RUN_FROM=1 RUN_TO=3 bash run_part.sh SS-II AODV   # only seeds 1-3 first
#   RUN_FROM=4 RUN_TO=10 bash run_part.sh SS-II AODV  # add the rest later
#
# Results go to results/ (one CSV per run, same names as run_all.sh).
# Finished runs are skipped, so you can stop (Ctrl+C) and resume any time.
# Simulator output goes to logs/<scenario>_<protocol>.log, not to the terminal.

SCEN=$1
PROTO=$2
RUN_FROM=${RUN_FROM:-1}
RUN_TO=${RUN_TO:-10}
JOBS=${JOBS:-1}
OUT=${OUT:-results}
LOGDIR=${LOGDIR:-logs}
EXTRA=${EXTRA:-}   # extra options passed to manet-paper, e.g. "--speedUniform=true"

if [[ "$SCEN" != "SS-I" && "$SCEN" != "SS-II" ]] || [[ "$PROTO" != "OLSR" && "$PROTO" != "AODV" && "$PROTO" != "DSDV" ]]; then
    echo "Usage: bash run_part.sh <SS-I|SS-II> <OLSR|AODV|DSDV>"
    exit 1
fi

mkdir -p "$OUT" "$LOGDIR"

./ns3 build manet-paper || { echo "Build failed"; exit 1; }

BIN=$(find build/scratch -maxdepth 1 -type f -name "ns3*-manet-paper-*" | head -1)
if [ -z "$BIN" ]; then
    echo "Cannot find the manet-paper binary in build/scratch"
    exit 1
fi
export LD_LIBRARY_PATH="$PWD/build/lib:$LD_LIBRARY_PATH"

LOG="$LOGDIR/${SCEN}_${PROTO}.log"
JOBFILE="jobs_${SCEN}_${PROTO}.txt"
: > "$JOBFILE"

if [ "$SCEN" = "SS-I" ]; then
    for n in 30 40 50 60 70 80 90 100; do
        for r in $(seq "$RUN_FROM" "$RUN_TO"); do
            f="$OUT/SS-I_${PROTO}_${n}_0_${r}.csv"
            [ -s "$f" ] && continue
            echo "$BIN --protocol=$PROTO --nNodes=$n --pause=0 --run=$r --scenario=SS-I --csv=$f $EXTRA" >> "$JOBFILE"
        done
    done
else
    for t in 5 10 15 20 25 30; do
        for r in $(seq "$RUN_FROM" "$RUN_TO"); do
            f="$OUT/SS-II_${PROTO}_50_${t}_${r}.csv"
            [ -s "$f" ] && continue
            echo "$BIN --protocol=$PROTO --nNodes=50 --pause=$t --run=$r --scenario=SS-II --csv=$f $EXTRA" >> "$JOBFILE"
        done
    done
fi

TOTAL=$(wc -l < "$JOBFILE")
if [ "$TOTAL" -eq 0 ]; then
    echo "Nothing to do: all runs of $SCEN $PROTO (seeds $RUN_FROM-$RUN_TO) already exist."
    exit 0
fi

echo "$SCEN $PROTO: $TOTAL runs to do (seeds $RUN_FROM-$RUN_TO, jobs=$JOBS)."
echo "Log: $LOG   (follow with: tail -f $LOG)"

# nice keeps the VM responsive while simulations are running
nice -n 10 xargs -P "$JOBS" -I{} bash -c "{} >> $LOG 2>&1" < "$JOBFILE"

DONE=$(ls "$OUT"/${SCEN}_${PROTO}_*.csv 2>/dev/null | wc -l)
echo "Finished. Result files for $SCEN $PROTO in $OUT/: $DONE"
