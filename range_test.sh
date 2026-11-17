#!/bin/bash
# Sweep the two-node range test and report where reception degrades.
# Usage (from the ns-3 root, after copying range_test.cc to scratch/):
#
#   bash range_test.sh
#   NS3_DIR=~/ns-3-dev bash range_test.sh
#   MAXDIST=3000 bash range_test.sh      # extend the sweep
#
# Output:
#   range_test_results.txt - one TSV line per measured distance
#   stdout                 - the range, plus the partial-reception band
#
# The sweep is deliberately NOT short-circuited at the first non-full distance:
# breaking early loses how wide the transition band is (the zone where some
# frames arrive and others do not). Every distance is measured, then the
# boundary is refined by bisection.
#
# Outcomes per probe, kept distinct:
#   send_failures > 0        harness broken -> abort, result invalid
#   received = sent          full link
#   0 < received < sent      partial link (the edge of coverage)
#   received = 0             no link

set -u

NS3_DIR=${NS3_DIR:-}
if [ -n "$NS3_DIR" ]; then
    cd "$NS3_DIR" || { echo "Cannot cd to NS3_DIR=$NS3_DIR"; exit 1; }
fi

MAXDIST=${MAXDIST:-1500}
COARSE_STEP=${COARSE_STEP:-50}
BISECT_TOL=${BISECT_TOL:-10}
CONTROL_DIST=${CONTROL_DIST:-1}

# ns-3 names a scratch target after the FILE, prefixed with "scratch_":
#   scratch/range_test.cc  ->  target "scratch_range_test"
# The binary is build/scratch/ns<ver>-range_test[-<profile>].
# A hyphenated name ("range-test") does not exist, so do not assume one.
SRC_NAME=range_test
TARGET_NAME=scratch_${SRC_NAME}

if [ ! -f "scratch/${SRC_NAME}.cc" ]; then
    echo "ERROR: scratch/${SRC_NAME}.cc not found in $PWD"
    echo "  ns-3 only builds scratch programs that live in scratch/."
    echo "  Copy it there first, then re-run this script:"
    echo "      cp /path/to/${SRC_NAME}.cc ~/ns-3-dev/scratch/"
    echo "  Files in ~/manet-ns3-paper are NOT picked up by the build."
    exit 1
fi

echo "Building ${TARGET_NAME}..."
if ! ./ns3 build "$TARGET_NAME"; then
    echo "ERROR: build of target '${TARGET_NAME}' failed."
    echo "  If ns-3 says the target does not exist, force a CMake re-scan:"
    echo "      ./ns3 configure --enable-examples --enable-tests"
    echo "  then re-run this script. Compiler errors are printed above."
    exit 1
fi

BIN=$(find build/scratch -maxdepth 1 -type f -name "ns3*-${SRC_NAME}-*" | head -1)
if [ -z "$BIN" ]; then
    echo "ERROR: target ${TARGET_NAME} built, but no binary matching"
    echo "  'build/scratch/ns3*-${SRC_NAME}-*' was found."
    echo "  Files present in build/scratch:"
    ls -1 build/scratch 2>/dev/null | sed 's/^/    /' || echo "    (none)"
    exit 1
fi
echo "Using binary: $BIN"
export LD_LIBRARY_PATH="$PWD/build/lib:${LD_LIBRARY_PATH:-}"

OUTFILE=range_test_results.txt
: > "$OUTFILE"
printf 'distance_m\tsent\treceived\tsend_failures\treachable\n' >> "$OUTFILE"

PROBE_SENT=0
PROBE_RECEIVED=0
PROBE_OK=0

# Returns 0 on a usable measurement, 1 on a fatal (invalid) one.
probe() {
    local d="$1"
    local line rc sent received failures ok

    line=$("$BIN" --distance="$d")
    rc=$?

    if [ "$rc" -ne 0 ]; then
        printf '%s\t%s\t%s\t%s\t%s\n' "$d" "?" "?" ">0" "invalid" >> "$OUTFILE"
        return 1
    fi

    sent=$(echo "$line" | sed -n 's/.*sent=\([0-9]*\).*/\1/p')
    received=$(echo "$line" | sed -n 's/.*received=\([0-9]*\).*/\1/p')
    failures=$(echo "$line" | sed -n 's/.*send_failures=\([0-9]*\).*/\1/p')
    ok=$(echo "$line" | sed -n 's/.*reachable=\([01]\).*/\1/p')

    if [ -z "$sent" ] || [ -z "$received" ] || [ -z "$ok" ]; then
        printf '%s\t%s\t%s\t%s\t%s\n' "$d" "?" "?" "?" "unparsable" >> "$OUTFILE"
        return 1
    fi

    printf '%s\t%s\t%s\t%s\t%s\n' \
        "$d" "$sent" "$received" "${failures:-?}" "$ok" >> "$OUTFILE"

    PROBE_SENT=$sent
    PROBE_RECEIVED=$received
    PROBE_OK=$ok
    return 0
}

abort_invalid() {
    echo "ERROR: invalid measurement at $1 m ($2)."
    echo "  The harness is broken, not the radio range. Aborting without a result."
    echo "  Per-run detail: $OUTFILE"
    exit 1
}

# ---------------------------------------------------------------- control probe
# A short-range control: if the link does not work at 1 m, every later distance
# would read as "out of range" and the sweep would be meaningless.
# 0 m is deliberately not probed: two nodes at the same point is a degenerate
# configuration, and 1 m answers the same question without it.
echo "Control probe (${CONTROL_DIST} m)..."
probe "$CONTROL_DIST" || abort_invalid "$CONTROL_DIST" "Send() failed or output unparsable"
if [ "$PROBE_OK" != "1" ]; then
    echo "ERROR: the link does not deliver all frames at ${CONTROL_DIST} m."
    echo "  Every longer distance would be misread as out of range, so the sweep"
    echo "  is not meaningful. Check that both sockets are bound, that they use"
    echo "  the same protocol number, and the Tx power / Friis settings."
    echo "  Per-run detail: $OUTFILE"
    exit 1
fi
echo "  link works at ${CONTROL_DIST} m: harness is usable."

# The control distance is a known-good point, so it seeds the baseline. Without
# this, a link that already fails at the first sweep step would produce no
# full->non-full pair and the boundary between CONTROL_DIST and that step would
# never be searched.
last_full=$CONTROL_DIST
prev_full=$CONTROL_DIST
first_partial=""
first_zero=""
partial_list=""
pairs=""

# ---------------------------------------------------------------- coarse sweep
# MAXDIST is appended explicitly so a value that is not a multiple of
# COARSE_STEP is still probed; otherwise "all distances were full" would be
# compared against a distance that was never measured.
DISTANCES=$(seq "$COARSE_STEP" "$COARSE_STEP" "$MAXDIST" 2>/dev/null || true)
if [ "$MAXDIST" -lt "$COARSE_STEP" ]; then
    DISTANCES="$MAXDIST"
else
    case " $DISTANCES " in
        *" $MAXDIST "*) ;;
        *)
            # Keep the list sorted so the last_full/prev_full pairing below stays
            # monotonic: an out-of-order MAXDIST could otherwise pair a boundary
            # backwards.
            DISTANCES=$(printf '%s\n%s\n' "$DISTANCES" "$MAXDIST" | sort -n | tr '\n' ' ')
            ;;
    esac
fi

echo "Coarse sweep ${COARSE_STEP}..${MAXDIST} m (step ${COARSE_STEP} m)..."
for d in $DISTANCES; do
    probe "$d" || abort_invalid "$d" "Send() failed or output unparsable"

    if [ "$PROBE_SENT" != "0" ] && [ "$PROBE_RECEIVED" = "$PROBE_SENT" ]; then
        last_full=$d
        prev_full=$d
        continue
    fi

    [ "$PROBE_RECEIVED" = "0" ] && [ -z "$first_zero" ] && first_zero=$d
    if [ "$PROBE_RECEIVED" != "0" ]; then
        [ -z "$first_partial" ] && first_partial=$d
        partial_list="$partial_list $d($PROBE_RECEIVED/$PROBE_SENT)"
    fi

    # Record exactly one boundary per contiguous full run, then close it so a
    # later run cannot pair with a stale full distance.
    if [ -n "$prev_full" ]; then
        pairs="$pairs $prev_full:$d"
        prev_full=""
    fi
done

# ---------------------------------------------------------------- bisection
if [ -n "$pairs" ]; then
    echo "Refining each boundary by bisection..."
    for pair in $pairs; do
        lo=${pair%%:*}
        hi=${pair##*:}
        while [ $((hi - lo)) -gt "$BISECT_TOL" ]; do
            mid=$(( (lo + hi) / 2 ))
            probe "$mid" || abort_invalid "$mid" "Send() failed or output unparsable"

            if [ "$PROBE_SENT" != "0" ] && [ "$PROBE_RECEIVED" = "$PROBE_SENT" ]; then
                lo=$mid
            else
                hi=$mid
                [ "$PROBE_RECEIVED" != "0" ] && \
                    partial_list="$partial_list $mid($PROBE_RECEIVED/$PROBE_SENT)"
            fi
        done
        [ "$lo" -gt "$last_full" ] && last_full=$lo
    done
fi

# ---------------------------------------------------------------- report
echo
# MAXDIST was actually probed (see DISTANCES above), so this comparison is sound.
if [ "$last_full" -ge "$MAXDIST" ]; then
    echo "Radio range: >= ${MAXDIST} m (upper bound NOT reached)."
    echo "  Every distance up to ${MAXDIST} m delivered all frames, so this is a"
    echo "  lower bound only. Re-run with a larger limit to find the edge, e.g.:"
    echo "      MAXDIST=$((MAXDIST * 2)) bash range_test.sh"
    echo "  Per-run detail: $OUTFILE"
    exit 0
fi

if [ "$last_full" -le "$CONTROL_DIST" ]; then
    echo "Radio range: below the resolution of this sweep (${CONTROL_DIST}-${COARSE_STEP} m)."
    echo "  ${CONTROL_DIST} m delivered all frames but ${COARSE_STEP} m did not, so the"
    echo "  boundary lies in between. Re-run with a smaller step to resolve it:"
    echo "      COARSE_STEP=2 MAXDIST=${COARSE_STEP} bash range_test.sh"
    echo "  Per-run detail: $OUTFILE"
    exit 0
fi

echo "Radio range (all frames delivered): ${last_full} m"
echo "  (Tx 7.5 dBm, Friis 2.412 GHz, 802.11b 2 Mbps broadcast)"
if [ -n "$partial_list" ]; then
    echo "  Partial reception (some frames lost, not all) at:${partial_list}"
    echo "  The edge of coverage is a band, not a single radius: the link is reliable"
    echo "  up to ${last_full} m and intermittent in the distances listed above."
fi
if [ -n "$first_zero" ]; then
    echo "  Total loss (no frame at all) first at ${first_zero} m."
fi
echo "  Area is 300 x 1500 m; each node covers a band of width min(2R, 300) m."
echo "  Per-run detail: $OUTFILE"
