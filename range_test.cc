/*
 * range_test.cc
 *
 * Measures the actual radio range produced by the propagation settings used in
 * manet-paper.cc. This exists because the paper does not state its transmission
 * range, and the Friis model's range depends on the carrier frequency, the
 * transmit power and ns-3's receiver thresholds. Without measuring it, the
 * density sweep in SS-I cannot be interpreted: if the range is comparable to the
 * 300 m width of the area, every node hears every other node across the width
 * and the number of nodes barely changes the topology.
 *
 * Method: two static nodes, one broadcast frame at 2 Mbps (the same data rate
 * and the same NonUnicastMode override used by manet-paper.cc), no IP stack and
 * no ARP. Broadcast frames are not acknowledged, so reception is a clean
 * yes/no rather than a retransmission race.
 *
 * Put this file in scratch/ next to manet-paper.cc:
 *
 *   cp range_test.cc scratch/
 *   ./ns3 build range-test
 *   ./ns3 run "range-test --distance=300"
 *
 * Or sweep all distances with range_test.sh.
 */

#include "ns3/core-module.h"
#include "ns3/mobility-module.h"
#include "ns3/network-module.h"
#include "ns3/packet-socket-address.h"
#include "ns3/packet-socket-helper.h"
#include "ns3/packet-socket.h"
#include "ns3/wifi-module.h"

#include <iostream>

using namespace ns3;

NS_LOG_COMPONENT_DEFINE("RangeTest");

namespace
{

uint32_t g_received = 0;

void
Receive(Ptr<Socket> socket)
{
    while (Ptr<Packet> packet = socket->Recv())
    {
        g_received++;
    }
}

void
SendOne(Ptr<Socket> socket, uint32_t size)
{
    Ptr<Packet> packet = Create<Packet>(size);
    socket->Send(packet);
}

} // namespace

int
main(int argc, char* argv[])
{
    double distance = 300.0;   // m
    double txPower = 7.5;      // dBm, same as manet-paper.cc
    double freq = 2.412e9;     // Hz, same as manet-paper.cc
    uint32_t packetSize = 64;  // bytes
    uint32_t nFrames = 3;      // frames sent per test
    double spacing = 0.1;      // s between frames

    CommandLine cmd(__FILE__);
    cmd.AddValue("distance", "Separation between the two nodes (m)", distance);
    cmd.AddValue("txPower", "Transmit power (dBm)", txPower);
    cmd.AddValue("freq", "Friis carrier frequency (Hz)", freq);
    cmd.AddValue("packetSize", "Frame payload size (bytes)", packetSize);
    cmd.AddValue("nFrames", "Frames to send per test", nFrames);
    cmd.AddValue("spacing", "Time between frames (s)", spacing);
    cmd.Parse(argc, argv);

    // Same 802.11b, 2 Mbps configuration as the main simulation.
    Config::SetDefault("ns3::WifiRemoteStationManager::NonUnicastMode",
                       StringValue("DsssRate2Mbps"));

    NodeContainer nodes;
    nodes.Create(2);

    WifiHelper wifi;
    wifi.SetStandard(WIFI_STANDARD_80211b);
    wifi.SetRemoteStationManager("ns3::ConstantRateWifiManager",
                                 "DataMode",
                                 StringValue("DsssRate2Mbps"),
                                 "ControlMode",
                                 StringValue("DsssRate2Mbps"));

    YansWifiChannelHelper channel;
    channel.SetPropagationDelay("ns3::ConstantSpeedPropagationDelayModel");
    channel.AddPropagationLoss("ns3::FriisPropagationLossModel", "Frequency", DoubleValue(freq));

    YansWifiPhyHelper phy;
    phy.SetChannel(channel.Create());
    phy.Set("TxPowerStart", DoubleValue(txPower));
    phy.Set("TxPowerEnd", DoubleValue(txPower));

    WifiMacHelper mac;
    mac.SetType("ns3::AdhocWifiMac");

    NetDeviceContainer devices = wifi.Install(phy, mac, nodes);

    Ptr<ListPositionAllocator> positions = CreateObject<ListPositionAllocator>();
    positions->Add(Vector(0.0, 0.0, 0.0));
    positions->Add(Vector(distance, 0.0, 0.0));

    MobilityHelper mobility;
    mobility.SetPositionAllocator(positions);
    mobility.SetMobilityModel("ns3::ConstantPositionMobilityModel");
    mobility.Install(nodes);

    PacketSocketHelper packetSocket;
    packetSocket.Install(nodes);

    const uint16_t protocolNumber = 1;

    // Receiver: listen on the second device for any frame.
    Ptr<Socket> recvSocket =
        Socket::CreateSocket(nodes.Get(1), PacketSocketFactory::GetTypeId());
    PacketSocketAddress recvAddress;
    recvAddress.SetSingleDevice(devices.Get(1)->GetIfIndex());
    recvAddress.SetPhysicalAddress(Mac48Address::GetBroadcast());
    recvAddress.SetProtocol(protocolNumber);
    recvSocket->Bind(recvAddress);
    recvSocket->SetRecvCallback(MakeCallback(&Receive));

    // Sender: broadcast, so there is no link-layer acknowledgement or retransmission.
    Ptr<Socket> sendSocket =
        Socket::CreateSocket(nodes.Get(0), PacketSocketFactory::GetTypeId());
    PacketSocketAddress sendAddress;
    sendAddress.SetSingleDevice(devices.Get(0)->GetIfIndex());
    sendAddress.SetPhysicalAddress(Mac48Address::GetBroadcast());
    sendAddress.SetProtocol(protocolNumber);
    sendSocket->Connect(sendAddress);
    sendSocket->SetAllowBroadcast(true);

    for (uint32_t i = 0; i < nFrames; i++)
    {
        Simulator::Schedule(Seconds(1.0 + i * spacing), &SendOne, sendSocket, packetSize);
    }

    Simulator::Stop(Seconds(1.0 + nFrames * spacing + 1.0));
    Simulator::Run();

    // One line of machine-readable output, consumed by range_test.sh.
    std::cout << "distance_m=" << distance << " sent=" << nFrames << " received=" << g_received
              << " reachable=" << ((g_received == nFrames) ? 1 : 0) << std::endl;

    Simulator::Destroy();
    return 0;
}
