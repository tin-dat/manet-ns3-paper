# MANET routing protocols in NS-3 (AODV, DSDV, OLSR)

Re-implementation of the simulation setup of:

> Lakshman Naik.L, R.U. Khan, R.B. Mishra, "Analysis of Node Density and Pause Time
> Effects in MANET Routing Protocols using NS-3", IJCNIS 8(12), 9-17, 2016.
> DOI: 10.5815/ijcnis.2016.12.02

The paper does not publish its source code, so this is an independent reconstruction
from its parameter tables (Table 1 and Table 7). Results will not match the paper
exactly (different NS-3 version, seeds and metric definitions); the goal is to compare trends.

## Files

| File | Purpose |
|---|---|
| `manet-paper.cc` | NS-3 simulation (copy to `scratch/`) |
| `check.sh` | Part 1: quick sanity check (3 short runs) |
| `run_part.sh` | Part 2: run one scenario for one protocol (resumable) |
| `run_all.sh` | Run everything in one go (optional) |
| `par.sh` | Run several seeds in parallel, one core per seed (optional) |
| `analyze.py` | Part 3: aggregate `results/*.csv`, plot figures, compare with the paper |
| `range_test.cc` | Two-node radio-range measurement (copy to `scratch/`) |
| `range_test.sh` | Sweep `range_test` to find the actual radio range |

## Setup (Ubuntu 22.04/24.04, NS-3 3.48, optimized profile)

```bash
git clone https://github.com/tin-dat/manet-ns3-paper.git ~/manet-ns3-paper
cd ~/ns-3-dev
cp ~/manet-ns3-paper/manet-paper.cc ~/manet-ns3-paper/range_test.cc scratch/
cp ~/manet-ns3-paper/*.sh ~/manet-ns3-paper/analyze.py .
./ns3 build manet-paper
./ns3 build range_test
```

## Run

```bash
bash range_test.sh                     # measure the actual radio range first
bash check.sh                          # sanity check
bash run_part.sh SS-I OLSR             # repeat for AODV, DSDV
bash run_part.sh SS-II OLSR            # repeat for AODV, DSDV
RUN_FROM=1 RUN_TO=2 bash run_part.sh SS-I OLSR   # optional: fewer seeds first
sudo apt install -y python3-pandas python3-matplotlib python3-scipy
python3 analyze.py                     # plots/, plots_vs_paper/, summary.csv, paper_comparison.csv
```

`run_part.sh` defaults to seeds **1..6**, which is exactly what `analyze.py` uses for
the main averages, so the default sequence produces a dataset the analysis accepts.

Optional extra seeds (they are archived in `all_runs.csv` but excluded from the
main averages, which is what the original code did with the 12 extra OLSR runs):

```bash
RUN_FROM=7 RUN_TO=10 NODES="30 40 50" bash run_part.sh SS-I OLSR
```

## Simulation parameters

- 802.11b ad-hoc, 2 Mbps, Friis loss model, Tx power 7.5 dBm
- Random Waypoint, 20 m/s, area 300 x 1500 m
- 10 CBR/UDP flows, 2048 bps, 64-byte packets, 150 s
- SS-I: 30-100 nodes, no pause. SS-II: 50 nodes, pause 5-30 s
- The Friis model is set to 2.412 GHz (`--freq`), since 802.11b uses the 2.4 GHz band
  (ns-3's default of 5.15 GHz gives a shorter radio range at 7.5 dBm, too short for a
  300 x 1500 m area). **Run `range_test.sh` to measure the actual range** — see
  "Known limitations".
- Broadcast frames (HELLO/TC/RREQ) are sent at 2 Mbps rather than at the 1 Mbps basic
  rate (`NonUnicastMode`), matching `examples/routing/manet-routing-compare.cc`.
  Without this, routing control packets reach further than data packets and the
  protocol sees neighbours it cannot actually deliver data to.

## Metrics

Throughput (payload, Kbps), PDR (%), average end-to-end delay (ms), packet loss,
and NRL.

`nrl` = every routing packet transmitted by every node / data packets received.

This is **not** a per-hop count. ns-3's OLSR sends every routing packet from a
socket bound to the local address (`RoutingProtocol::SendPacket` sends to the
subnet-directed broadcast of `GetAddress().GetLocal()`), and AODV does the same,
so a relayed packet always carries the relay's own IP source address. A
source-address test therefore cannot separate originated from forwarded traffic.

Verification: `routing_packets` matches `105 x nNodes` to within 1% at both 30 and
100 nodes, where 105 is 75 HELLO (150 s / 2 s) plus 30 TC (150 s / 5 s) per node.
If forwarded copies were counted the figure would grow faster than linearly and
would be many times larger. So the counter measures packets **originated** by the
node, which is the definition normally used in the literature.

Consequence: the CSV's `routing_packets_origin` and `nrl_origin` columns duplicate
`routing_packets` and `nrl`, because the source-address test never distinguishes
anything. They are written for inspection but are not plotted or summarised.

'sent' is the number of packets the sources generate on their CBR schedule (about
6000 per run); 'received' is counted at the sinks. Because `sent` is a formula rather
than a counter, `recv` can exceed it by a packet or two; PDR is then clamped to 100%
and a warning is printed to stderr.

The paper's "NRL" columns equal PDR/100; this is kept as `nrl_pdr_over_100` for
comparison. See below.

## Figures produced by `analyze.py`

`plots/` — simulation only: 5 metrics x 2 scenarios, mean with a 95% CI band.

`plots_vs_paper/` — the same 5 metrics x 2 scenarios, but with the paper's own
values overlaid as dashed lines with hollow markers. This is the only set that
answers the repo's stated goal ("compare trends"): a simulation-only plot shows
what this model does, and the CSV shows what the paper claims, but only the
overlay shows whether the two *shapes* agree. For the NRL figure both curves are
PDR/100, because that is what the paper's NRL column actually is.

`plots_nrl_pdr_over_100/` — diagnostic only, kept to show the identity above.

## What the original paper's tables actually contain

Only **PDR** and **end-to-end delay** are independent measurements in the paper. The
other three columns are algebra on PDR, verified against all 42 values in Tables 2-6
and 8-12:

| Paper column | Identity |
|---|---|
| Throughput (Kbps) | `20 * PDR/100` |
| Packet loss | `6000 * (1 - PDR/100)` |
| NRL | `PDR/100` |

Consequences:

- The paper's NRL is not a routing load at all. `analyze.py` computes the real
  `routing_packets / recv` instead, and keeps `nrl_pdr_over_100` only as a diagnostic.
- The loss column reproducing `6000 * (1 - PDR/100)` to the packet implies a single
  simulation per point, with no seed averaging. The repo uses 6 seeds and reports a
  95% confidence interval, so the two datasets are not strictly comparable: the paper
  plots one sample, this repo plots a mean.
- `paper_comparison.csv` marks these rows with
  `paper_value_is_derived_from_pdr = True`.

## Measured radio range

`range_test.sh` measures the two-node link directly. On this setup (Tx 7.5 dBm,
Friis at 2.412 GHz, 802.11b 2 Mbps broadcast) the link delivers essentially all
frames up to about **293 m** and fails at **300 m**, so the practical range is
roughly **295 m**.

Consequence for SS-I: with a 300 x 1500 m area, one node covers a band about
590 m wide, i.e. **wider than the area itself**. Every node can hear every other
node across the width, so at 50 nodes the mean neighbour count is on the order of
40, and at 100 nodes about 80. The density sweep therefore mostly varies
*contention*, not *connectivity*: it does not test whether a route exists, it
tests how well the network copes when almost every node is a neighbour of almost
every other.

That is consistent with the paper's OLSR PDR staying flat at 87-95% regardless of
density, and it is the reason SS-I results should be read as a load sweep rather
than a connectivity sweep.

## Result that contradicts the paper

At 30 nodes, no pause, 20 m/s (single seed, so indicative rather than final):

| Protocol | PDR |
|---|---|
| AODV | ~78% |
| OLSR | ~57% |

The paper reports the opposite ordering (OLSR 91.3%, AODV 80.2%). This is a real
effect of the mobility model, not a bug: with a constant 20 m/s and no pause,
links break continuously, and OLSR only detects a dead link after missing several
HELLOs (2 s apart). Until then it keeps forwarding into a next hop that has left
the radio range. AODV discovers routes on demand and so does not depend on
neighbour state being fresh, which is why it degrades more gracefully here.

The paper states "Node Speed 20 m/s" without saying whether that is a constant or
a maximum. Treating it as a constant is the harshest reading for a proactive
protocol. `--speedUniform=true` gives the milder Uniform[0,20] interpretation.

## Known limitations

- **Radio range** is measured (~295 m, above) rather than assumed, but the paper
  gives no range and no receiver threshold, so the match to the paper's own setup is
  unknown.
- **NS-3 version.** The paper used ns-3.13; this uses 3.48. The Wi-Fi PHY, and the
  AODV/OLSR implementations, have changed substantially in between, so absolute
  numbers cannot be reproduced.
- **Node speed.** The paper says "20 m/s" without saying whether this is constant or a
  maximum. The default here is constant 20 m/s, which is harsher on topology stability
  than a Uniform[0,20] model; use `--speedUniform=true` to test the alternative.
- **Protocol parameters** (OLSR HELLO/TC intervals, AODV RREQ retry and rate limits,
  DSDV update interval) are ns-3 defaults, since the paper does not state them.
- **`routing_bytes`** counts bytes on the wire at each hop, including IP and UDP
  headers, not routing payload.
