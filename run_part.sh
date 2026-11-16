#!/bin/bash
# PART 2 - run ONE scenario for ONE protocol (a small, resumable chunk).
#
# Usage (from the ns-3 root):
#   bash run_part.sh <SS-I|SS-II> <OLSR|AODV|DSDV>
#
# Optional environment variables:
#   RUN_FROM=1 RUN_TO=6    seeds to run (default 1..6, matching analyze.py)
#   NODES="30 40 50"       restrict SS-I to a subset of node counts
#   JOBS=1                 parallel processes (keep <= CPUs given to the VM)
#   OUT=results            output directory for the CSV files
#   LOGDIR=logs            log directory
#   EXTRA="--speedUniform=true"   extra options for manet-paper
#   NS3_DIR=/path/to/ns-3  ns-3 root (default: current directory)
#
# Examples:
#   bash run_part.sh SS-I OLSR                        # 8 node counts x 6 seeds
#   RUN_FROM=1 RUN_TO=2 bash run_part.sh SS-II AODV   # only seeds 1-2 first
#   RUN_FROM=1 RUN_TO=6 NODES="30 40 50" bash run_part.sh SS-I OLSR
#   RUN_FROM=7 RUN_TO=10 NODES="30 40 50" bash run_part.sh SS-I OLSR   # extra seeds
#
# Results go to results/ (one CSV per run). Finished runs are skipped, so you
# can stop (Ctrl+C) and resume any time. Simulator output goes to
# logs/<scenario>_<protocol>.log, not to the terminal.
#
# The default seed range (1..6) is exactly what analyze.py uses for the main
# analysis. To add the optional extra OLSR seeds 7..10 use NODES as shown
# above; analyze.py archives them but excludes them from the averages.

set -u

SCEN=$1
PROTO=$2
RUN_FROM=${RUN_FROM:-1}
RUN_TO=${RUN_TO:-6}
JOBS=${JOBS:-1}
OUT=${OUT:-results}
LOGDIR=${LOGDIR:-logs}
EXTRA=${EXTRA:-}
NODES=${NODES:-"30 40 50 60 70 80 90 100"}
NS3_DIR=${NS3_DIR:-}

if [[ "$SCEN" != "SS-I" && "$SCEN" != "SS-II" ]] || [[ "$PROTO" != "OLSR" && "$PROTO" != "AODV" && "$PROTO" != "DSDV" ]]; then
    echo "Usage: bash run_part.sh <SS-I|SS-II> <OLSR|AODV|DSDV>"
    exit 1
fi

if [ -n "$NS3_DIR" ]; then
    cd "$NS3_DIR" || { echo "Cannot cd to NS3_DIR=$NS3_DIR"; exit 1; }
fi

mkdir -p "$OUT" "$LOGDIR"

# SKIP_BUILD=1 avoids concurrent builds when several run_part.sh run in parallel
[ -n "${SKIP_BUILD:-}" ] || ./ns3 build manet-paper || { echo "Build failed"; exit 1; }

BIN=$(find build/scratch -maxdepth 1 -type f -name "ns3*-manet-paper-*" | head -1)
if [ -z "$BIN" ]; then
    echo "Cannot find the manet-paper binary in build/scratch"
    exit 1
fi
export LD_LIBRARY_PATH="$PWD/build/lib:${LD_LIBRARY_PATH:-}"

LOG="$LOGDIR/${SCEN}_${PROTO}_s${RUN_FROM}-${RUN_TO}.log"
JOBFILE="jobs_${SCEN}_${PROTO}_s${RUN_FROM}-${RUN_TO}.txt"
: > "$JOBFILE"

# A run is complete only if its CSV has a header plus one data row with the
# expected number of fields. A process killed mid-write leaves a truncated
# file; the plain "-s" test used to skip such a run forever.
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

if [ "$SCEN" = "SS-I" ]; then
    for n in $NODES; do
        for r in $(seq "$RUN_FROM" "$RUN_TO"); do
            f="$OUT/SS-I_${PROTO}_${n}_0_${r}.csv"
            csv_is_complete "$f" && continue
            echo "$BIN --protocol=$PROTO --nNodes=$n --pause=0 --run=$r --scenario=SS-I --csv=$f $EXTRA" >> "$JOBFILE"
        done
    done
else
    for t in 5 10 15 20 25 30; do
        for r in $(seq "$RUN_FROM" "$RUN_TO"); do
            f="$OUT/SS-II_${PROTO}_50_${t}_${r}.csv"
            csv_is_complete "$f" && continue
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
