/*
 * manet-paper.cc
 *
 * Re-implementation of the simulation setup described in:
 *   "Analysis of Node Density and Pause Time Effects in MANET Routing
 *    Protocols using NS-3" (IJCNIS 2016, 8(12), 9-17)
 *
 * Fixed parameters (Table 1 and Table 7 of the paper):
 *   - 802.11b ad-hoc, 2 Mbps (DsssRate2Mbps), Friis loss model
 *   - Tx power 7.5 dBm
 *   - Random Waypoint, speed 20 m/s, area 300 x 1500 m
 *   - 10 CBR/UDP flows, 2048 bps, 64-byte packets (4 packets/s)
 *   - Simulation time 150 s
 *
 * Variable parameters (command line):
 *   --protocol=OLSR|AODV|DSDV   --nNodes=N   --pause=SECONDS   --run=K
 *
 * Metrics (computed per run, one CSV row):
 *   sent, recv, PDR(%), throughput(Kbps), delay(ms), loss, routing packets,
 *   routing bytes, NRL (routing packets sent / data packets received)
 *
 * Tested target: ns-3.4x (CMake-based ./ns3). Put this file in scratch/.
 */

#include "ns3/aodv-module.h"
#include "ns3/applications-module.h"
#include "ns3/core-module.h"
#include "ns3/dsdv-module.h"
#include "ns3/flow-monitor-module.h"
#include "ns3/internet-module.h"
#include "ns3/ipv4-header.h"
#include "ns3/mobility-module.h"
#include "ns3/network-module.h"
#include "ns3/olsr-module.h"
#include "ns3/udp-header.h"
#include "ns3/wifi-module.h"

#include <algorithm>
#include <cctype>
#include <fstream>
#include <iostream>
#include <string>

using namespace ns3;

NS_LOG_COMPONENT_DEFINE("ManetPaper");

namespace
{

// Well-known UDP ports used by the routing protocols in ns-3
const uint16_t PORT_DSDV = 269;
const uint16_t PORT_AODV = 654;
const uint16_t PORT_OLSR = 698;

uint64_t g_routingPackets = 0;
uint64_t g_routingBytes = 0;
uint64_t g_appTx = 0; // data packets accepted by the source sockets
uint64_t g_appRx = 0; // data packets received by the sinks

/**
 * Called every time an IPv4 packet is handed to a net device (every hop).
 * Counts packets whose UDP destination port belongs to a routing protocol.
 */
void
Ipv4TxTrace(Ptr<const Packet> packet, Ptr<Ipv4> ipv4, uint32_t interface)
{
    Ptr<Packet> p = packet->Copy();
    Ipv4Header ipHeader;
    if (p->GetSize() < ipHeader.GetSerializedSize())
    {
        return;
    }
    p->RemoveHeader(ipHeader);
    if (ipHeader.GetProtocol() != 17) // UDP only
    {
        return;
    }
    UdpHeader udpHeader;
    if (p->GetSize() < udpHeader.GetSerializedSize())
    {
        return;
    }
    p->RemoveHeader(udpHeader);
    uint16_t dport = udpHeader.GetDestinationPort();
    if (dport == PORT_DSDV || dport == PORT_AODV || dport == PORT_OLSR)
    {
        g_routingPackets++;
        g_routingBytes += packet->GetSize();
    }
}

void
AppTxTrace(Ptr<const Packet> packet)
{
    g_appTx++;
}

void
AppRxTrace(Ptr<const Packet> packet, const Address& from)
{
    g_appRx++;
}

} // namespace

int
main(int argc, char* argv[])
{
    LogComponentEnable("DsdvRoutingProtocol", LOG_LEVEL_ALL);
    // ---------------- Parameters ----------------
    std::string protocol = "OLSR";
    std::string scenario = "SS-I";
    std::string csvFile = "manet-paper.csv";
    std::string dataRate = "2048bps";
    uint32_t nNodes = 50;
    uint32_t nSinks = 10;
    uint32_t packetSize = 64;
    uint32_t run = 1;
    double pause = 0.0;      // seconds (0 = no pause, as in SS-I)
    double totalTime = 150.0; // seconds
    double txPower = 7.5;    // dBm
    double speed = 20.0;     // m/s
    double areaX = 300.0;    // m
    double areaY = 1500.0;   // m
    bool bcastAtDataRate = true; // send broadcast frames (HELLO/TC/RREQ) at the data rate, as in ns-3's manet-routing-compare
    bool speedUniform = false; // true: speed ~ Uniform[0, speed] (as in ns-3's manet-routing-compare)
    double freq = 2.412e9;   // Hz, Friis carrier frequency (802.11b = 2.4 GHz band)

    CommandLine cmd(__FILE__);
    cmd.AddValue("protocol", "Routing protocol: OLSR, AODV or DSDV", protocol);
    cmd.AddValue("nNodes", "Number of nodes", nNodes);
    cmd.AddValue("nSinks", "Number of source/sink pairs", nSinks);
    cmd.AddValue("pause", "Random Waypoint pause time (s)", pause);
    cmd.AddValue("run", "Run number (changes the random seed)", run);
    cmd.AddValue("totalTime", "Simulation time (s)", totalTime);
    cmd.AddValue("txPower", "Transmit power (dBm)", txPower);
    cmd.AddValue("speed", "Node speed (m/s)", speed);
    cmd.AddValue("bcastAtDataRate",
                 "true: NonUnicastMode = DsssRate2Mbps (like manet-routing-compare); "
                 "false: ns-3 default (broadcasts at the 1 Mbps basic rate)",
                 bcastAtDataRate);
    cmd.AddValue("speedUniform", "Draw node speed from Uniform[0,speed] instead of a constant", speedUniform);
    cmd.AddValue("freq", "Carrier frequency used by the Friis model (Hz)", freq);
    cmd.AddValue("dataRate", "CBR rate per flow", dataRate);
    cmd.AddValue("packetSize", "Packet size (bytes)", packetSize);
    cmd.AddValue("scenario", "Label written to the CSV (e.g. SS-I, SS-II)", scenario);
    cmd.AddValue("csv", "Output CSV file (appended)", csvFile);
    cmd.Parse(argc, argv);

    std::transform(protocol.begin(), protocol.end(), protocol.begin(), ::toupper);
    if (protocol != "OLSR" && protocol != "AODV" && protocol != "DSDV")
    {
        std::cerr << "Unknown protocol '" << protocol << "'. Use OLSR, AODV or DSDV.\n";
        return 1;
    }
    if (nNodes < 2 * nSinks)
    {
        std::cerr << "nNodes must be >= 2 * nSinks (" << 2 * nSinks << ").\n";
        return 1;
    }

    RngSeedManager::SetSeed(12345);
    RngSeedManager::SetRun(run);

    // ---------------- Nodes ----------------
    NodeContainer nodes;
    nodes.Create(nNodes);

    // ---------------- Wi-Fi 802.11b ad-hoc ----------------
    if (bcastAtDataRate)
    {
        // By default ns-3 sends broadcast frames at the lowest basic rate (1 Mbps), which
        // reaches farther than the 2 Mbps unicast data frames. Routing control packets then
        // see neighbours that data frames cannot reach. The reference example
        // (examples/routing/manet-routing-compare.cc) avoids this by setting NonUnicastMode
        // to the unicast mode; we do the same.
        Config::SetDefault("ns3::WifiRemoteStationManager::NonUnicastMode",
                           StringValue("DsssRate2Mbps"));
    }

    WifiHelper wifi;
    wifi.SetStandard(WIFI_STANDARD_80211b);

    YansWifiChannelHelper wifiChannel;
    wifiChannel.SetPropagationDelay("ns3::ConstantSpeedPropagationDelayModel");
    // ns-3's Friis model defaults to 5.15 GHz, but 802.11b operates in the 2.4 GHz band.
    // Using 2.412 GHz gives a radio range of roughly 300 m at 7.5 dBm with the default
    // receiver thresholds (about 140 m at 5.15 GHz, too short for 300 x 1500 m).
    wifiChannel.AddPropagationLoss("ns3::FriisPropagationLossModel",
                                   "Frequency",
                                   DoubleValue(freq));

    YansWifiPhyHelper wifiPhy;
    wifiPhy.SetChannel(wifiChannel.Create());
    wifiPhy.Set("TxPowerStart", DoubleValue(txPower));
    wifiPhy.Set("TxPowerEnd", DoubleValue(txPower));

    WifiMacHelper wifiMac;
    wifiMac.SetType("ns3::AdhocWifiMac");
    wifi.SetRemoteStationManager("ns3::ConstantRateWifiManager",
                                 "DataMode",
                                 StringValue("DsssRate2Mbps"),
                                 "ControlMode",
                                 StringValue("DsssRate2Mbps"));

    NetDeviceContainer devices = wifi.Install(wifiPhy, wifiMac, nodes);

    // ---------------- Mobility: Random Waypoint ----------------
    ObjectFactory pos;
    pos.SetTypeId("ns3::RandomRectanglePositionAllocator");
    pos.Set("X", StringValue("ns3::UniformRandomVariable[Min=0.0|Max=" + std::to_string(areaX) + "]"));
    pos.Set("Y", StringValue("ns3::UniformRandomVariable[Min=0.0|Max=" + std::to_string(areaY) + "]"));
    Ptr<PositionAllocator> posAlloc = pos.Create()->GetObject<PositionAllocator>();

    const std::string speedStr =
        speedUniform ? "ns3::UniformRandomVariable[Min=0.0|Max=" + std::to_string(speed) + "]"
                     : "ns3::ConstantRandomVariable[Constant=" + std::to_string(speed) + "]";

    MobilityHelper mobility;
    mobility.SetPositionAllocator(posAlloc);
    mobility.SetMobilityModel(
        "ns3::RandomWaypointMobilityModel",
        "Speed",
        StringValue(speedStr),
        "Pause",
        StringValue("ns3::ConstantRandomVariable[Constant=" + std::to_string(pause) + "]"),
        "PositionAllocator",
        PointerValue(posAlloc));
    mobility.Install(nodes);

    // ---------------- Internet stack + routing ----------------
    InternetStackHelper internet;
    if (protocol == "OLSR")
    {
        OlsrHelper olsr;
        internet.SetRoutingHelper(olsr);
    }
    else if (protocol == "AODV")
    {
        AodvHelper aodv;
        internet.SetRoutingHelper(aodv);
    }
    else
    {
        DsdvHelper dsdv;
        internet.SetRoutingHelper(dsdv);
    }
    internet.Install(nodes);

    Ipv4AddressHelper addressHelper;
    addressHelper.SetBase("10.1.0.0", "255.255.0.0");
    Ipv4InterfaceContainer interfaces = addressHelper.Assign(devices);

    // ---------------- Traffic: nSinks CBR/UDP flows ----------------
    // Sink i = node i, source i = node (i + nSinks). Positions are random,
    // so the pairing is effectively random.
    const uint16_t dataPort = 9;
    Ptr<UniformRandomVariable> startJitter = CreateObject<UniformRandomVariable>();
    startJitter->SetAttribute("Min", DoubleValue(0.0));
    startJitter->SetAttribute("Max", DoubleValue(1.0));

    uint64_t generatedPackets = 0; // packets the sources try to send
    const double pktInterval = packetSize * 8.0 / DataRate(dataRate).GetBitRate();

    for (uint32_t i = 0; i < nSinks; i++)
    {
        PacketSinkHelper sinkHelper("ns3::UdpSocketFactory",
                                    InetSocketAddress(Ipv4Address::GetAny(), dataPort));
        ApplicationContainer sinkApp = sinkHelper.Install(nodes.Get(i));
        sinkApp.Start(Seconds(0.0));
        sinkApp.Stop(Seconds(totalTime));

        OnOffHelper onoff("ns3::UdpSocketFactory",
                          Address(InetSocketAddress(interfaces.GetAddress(i), dataPort)));
        onoff.SetAttribute("OnTime", StringValue("ns3::ConstantRandomVariable[Constant=1.0]"));
        onoff.SetAttribute("OffTime", StringValue("ns3::ConstantRandomVariable[Constant=0.0]"));
        onoff.SetConstantRate(DataRate(dataRate), packetSize);

        ApplicationContainer srcApp = onoff.Install(nodes.Get(i + nSinks));
        const double appStart = startJitter->GetValue();
        srcApp.Start(Seconds(appStart));
        // OnOff sends its first packet one interval after the start time
        generatedPackets += static_cast<uint64_t>((totalTime - appStart) / pktInterval);
        srcApp.Stop(Seconds(totalTime));
    }

    // ---------------- Measurement ----------------
    Config::ConnectWithoutContext("/NodeList/*/$ns3::Ipv4L3Protocol/Tx",
                                  MakeCallback(&Ipv4TxTrace));

    Config::ConnectWithoutContext("/NodeList/*/ApplicationList/*/$ns3::OnOffApplication/Tx",
                                  MakeCallback(&AppTxTrace));
    Config::ConnectWithoutContext("/NodeList/*/ApplicationList/*/$ns3::PacketSink/Rx",
                                  MakeCallback(&AppRxTrace));

    FlowMonitorHelper flowHelper;
    Ptr<FlowMonitor> monitor = flowHelper.InstallAll();

    Simulator::Stop(Seconds(totalTime));
    Simulator::Run();

    monitor->CheckForLostPackets();
    Ptr<Ipv4FlowClassifier> classifier =
        DynamicCast<Ipv4FlowClassifier>(flowHelper.GetClassifier());
    std::map<FlowId, FlowMonitor::FlowStats> stats = monitor->GetFlowStats();

    // "Sent" = packets the sources generate according to their CBR schedule.
    // OnOffApplication fires its Tx trace only when Socket::Send() succeeds, and Send()
    // fails when the routing protocol has no route (e.g. OLSR before convergence), so
    // g_appTx (kept as sent_accepted) under-counts. FlowMonitor has the same problem.
    uint64_t txPackets = generatedPackets;
    uint64_t rxPackets = g_appRx;
    uint64_t fmRxPackets = 0;
    double delaySumMs = 0.0;

    for (auto it = stats.begin(); it != stats.end(); ++it)
    {
        Ipv4FlowClassifier::FiveTuple t = classifier->FindFlow(it->first);
        // Keep only the application data flows (UDP, destination port 9)
        if (t.protocol != 17 || t.destinationPort != dataPort)
        {
            continue;
        }
        fmRxPackets += it->second.rxPackets;
        delaySumMs += it->second.delaySum.GetSeconds() * 1000.0;
    }
    
    std::cout << "DEBUG RX: PacketSink=" << rxPackets
          << " FlowMonitor=" << fmRxPackets
          << " Difference="
          << static_cast<int64_t>(rxPackets) -
                 static_cast<int64_t>(fmRxPackets)
          << std::endl;

    Simulator::Destroy();

    // Metrics as defined in Section IV of the paper
    double pdr = (txPackets > 0) ? 100.0 * rxPackets / txPackets : 0.0;
    // Payload throughput (matches the paper: 10 flows * 2.048 kbps * PDR)
    double throughputKbps = (rxPackets * packetSize * 8.0) / (totalTime * 1024.0);
    double avgDelayMs = (fmRxPackets > 0) ? delaySumMs / fmRxPackets : 0.0;
    uint64_t loss = (txPackets > rxPackets) ? (txPackets - rxPackets) : 0;
    double nrl = (rxPackets > 0) ? static_cast<double>(g_routingPackets) / rxPackets : 0.0;

    if (g_routingPackets == 0)
    {
        std::cerr << "WARNING: no routing packets counted; NRL is not valid. "
                     "Check the Ipv4L3Protocol/Tx trace.\n";
    }

    // ---------------- Output ----------------
    std::cout << scenario << " " << protocol << " nodes=" << nNodes << " pause=" << pause
              << " run=" << run << " | sent=" << txPackets << " accepted=" << g_appTx << " recv=" << rxPackets
              << " PDR=" << pdr << "% thr=" << throughputKbps << "Kbps delay=" << avgDelayMs
              << "ms loss=" << loss << " routingPkts=" << g_routingPackets << " NRL=" << nrl
              << std::endl;

    bool needHeader = true;
    {
        std::ifstream in(csvFile);
        if (in.good() && in.peek() != std::ifstream::traits_type::eof())
        {
            needHeader = false;
        }
    }
    std::ofstream out(csvFile, std::ios::app);
    if (needHeader)
    {
        out << "scenario,protocol,nodes,pause,run,sent,sent_accepted,recv,pdr_percent,throughput_kbps,"
               "delay_ms,loss_packets,routing_packets,routing_bytes,nrl\n";
    }
    out << scenario << "," << protocol << "," << nNodes << "," << pause << "," << run << ","
        << txPackets << "," << g_appTx << "," << rxPackets << "," << pdr << "," << throughputKbps << ","
        << avgDelayMs << "," << loss << "," << g_routingPackets << "," << g_routingBytes << ","
        << nrl << "\n";
    out.close();

    return 0;
}
