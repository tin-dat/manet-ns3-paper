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
| `analyze.py` | Part 3: aggregate `results/*.csv` and plot figures |

## Setup (Ubuntu 22.04/24.04, NS-3 3.48, optimized profile)

```bash
git clone https://github.com/tin-dat/manet-ns3-paper.git ~/manet-ns3-paper
cd ~/ns-3-dev
cp ~/manet-ns3-paper/manet-paper.cc scratch/
cp ~/manet-ns3-paper/*.sh ~/manet-ns3-paper/analyze.py .
./ns3 build manet-paper
```

## Run

```bash
bash check.sh                          # sanity check
bash run_part.sh SS-I OLSR             # repeat for AODV, DSDV
bash run_part.sh SS-II OLSR            # repeat for AODV, DSDV
RUN_FROM=1 RUN_TO=3 bash run_part.sh SS-I OLSR   # optional: fewer seeds first
sudo apt install -y python3-pandas python3-matplotlib python3-scipy
python3 analyze.py                     # plots/, summary.csv, all_runs.csv
```

## Simulation parameters

- 802.11b ad-hoc, 2 Mbps, Friis loss model, Tx power 7.5 dBm
- Random Waypoint, 20 m/s, area 300 x 1500 m
- 10 CBR/UDP flows, 2048 bps, 64-byte packets, 150 s
- SS-I: 30-100 nodes, no pause. SS-II: 50 nodes, pause 5-30 s
- `--legacyPhy=true` (default) lowers the preamble-detection minimum RSSI from
  -82 dBm to -96 dBm to approximate the longer radio range of NS-3.13; use
  `--legacyPhy=false` for modern NS-3 defaults. (Disabling the preamble-detection
  model altogether crashes dense runs with "Invalid WifiPhy state RX".)

## Metrics

Throughput (payload, Kbps), PDR (%), average end-to-end delay (ms), packet loss,
and NRL = routing packets sent / data packets received. Sent/received packets are
counted at application level. The paper's "NRL" columns equal PDR/100; this is kept
as `pdr_over_100` in `all_runs.csv` for comparison.
