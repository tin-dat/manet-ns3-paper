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
./ns3 build range-test
```

## Run

```bash
bash range_test.sh                     # measure the actual radio range first
bash check.sh                          # sanity check
bash run_part.sh SS-I OLSR             # repeat for AODV, DSDV
bash run_part.sh SS-II OLSR            # repeat for AODV, DSDV
RUN_FROM=1 RUN_TO=2 bash run_part.sh SS-I OLSR   # optional: fewer seeds first
sudo apt install -y python3-pandas python3-matplotlib python3-scipy
python3 analyze.py                     # plots/, summary.csv, paper_comparison.csv
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

`nrl` = every routing packet transmitted by every node / data packets received,
counted **at each hop**. `nrl_origin` = only routing packets whose IP source address
belongs to the transmitting node, i.e. the "routing packets originated" definition
usually used in the literature. For OLSR the two differ a lot, because TC messages
are flooded by MPRs: a single TC packet is counted once per relay in `nrl`. Use
`nrl_origin` when comparing against published numbers.

'sent' is the number of packets the sources generate on their CBR schedule (about
6000 per run); 'received' is counted at the sinks. Because `sent` is a formula rather
than a counter, `recv` can exceed it by a packet or two; PDR is then clamped to 100%
and a warning is printed to stderr.

The paper's "NRL" columns equal PDR/100; this is kept as `nrl_pdr_over_100` for
comparison. See below.

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

## Known limitations

- **Radio range is unmeasured.** The paper gives no transmission range and no receiver
  threshold. Run `range_test.sh` before interpreting SS-I: if the range is comparable
  to the 300 m width of the area, every node hears every other node across the width,
  and increasing the node count mostly adds redundancy rather than changing the
  topology. The previous revision of this README claimed "~300 m" without measuring it.
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
