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
 * Distance must be > 0. Co-locating the two nodes is a degenerate configuration
 * (ns-3's Friis model short-circuits d <= 0 to txPower - MinLoss), so use a
 * small positive distance such as 1 m as the near-field control instead.
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
uint32_t g_sendFailures = 0;

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
    int result = socket->Send(packet);

    if (result < 0)
    {
        // Keep the errno: ERROR_NOTCONN means the socket was not bound+connected,
        // ERROR_MSGSIZE means the frame exceeded the device MTU, and so on. Without
        // it, a harness problem is indistinguishable from "out of range".
        g_sendFailures++;
        std::cerr << "Send failed, errno=" << socket->GetErrno() << "\n";
    }
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

    if (distance <= 0.0)
    {
        std::cerr << "ERROR: --distance must be > 0 (got " << distance << ").\n"
                     "  Use a small positive value such as 1 m as the near-field "
                     "control; 0 m is a degenerate configuration.\n";
        return 2;
    }

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
    //
    // Note on SetPhysicalAddress: PacketSocket::DoBind() only consumes the device
    // index and the protocol number -- it calls RegisterProtocolHandler(protocol, dev)
    // and never reads the physical address. The address set here therefore does NOT
    // act as a receive filter; a frame addressed to this device's own MAC is delivered
    // either way. The local device address is used because it is the value that a bind
    // address semantically represents, and because Mac48Address::GetBroadcast() here
    // would wrongly suggest that reception depends on a broadcast destination.
    //
    // (Verified against ns-3 src/network/utils/packet-socket.cc, PacketSocket::DoBind
    // and PacketSocket::ForwardUp: ForwardUp sets the physical address of the *source*
    // of the received frame, it does not compare against the bound address.)
    Ptr<Socket> recvSocket =
        Socket::CreateSocket(nodes.Get(1), PacketSocketFactory::GetTypeId());
    PacketSocketAddress recvAddress;
    recvAddress.SetSingleDevice(devices.Get(1)->GetIfIndex());
    recvAddress.SetPhysicalAddress(devices.Get(1)->GetAddress());
    recvAddress.SetProtocol(protocolNumber);
    if (recvSocket->Bind(recvAddress) != 0)
    {
        std::cerr << "ERROR: Receiver PacketSocket::Bind failed.\n";
        return 1;
    }
    recvSocket->SetRecvCallback(MakeCallback(&Receive));

    // Sender: broadcast, so there is no link-layer acknowledgement or retransmission.
    //
    // IMPORTANT: PacketSocket::Connect() requires the socket to be BOUND first.
    // A freshly created socket is in STATE_OPEN, and Connect() rejects it:
    //     if (m_state == STATE_OPEN) { m_errno = ERROR_INVAL; goto error; }
    // and PacketSocket::Send() then also refuses:
    //     if (m_state == STATE_OPEN || m_state == STATE_BOUND) { ERROR_NOTCONN }
    // so without Bind() first, every frame would be silently dropped and this test
    // would report a radio range of 0 m at every distance.
    Ptr<Socket> sendSocket =
        Socket::CreateSocket(nodes.Get(0), PacketSocketFactory::GetTypeId());

    // Bind explicitly to this device and protocol rather than using the no-argument
    // Bind(), which binds protocol 0 on all devices. Both work here (the sender never
    // receives, and Node::ReceiveFromDevice matches on `protocol == 0 || protocol`),
    // but naming the device and protocol keeps the socket's state explicit and makes
    // a device-index or protocol mismatch fail loudly at bind time instead of
    // showing up later as "no frame received".
    PacketSocketAddress localAddress;
    localAddress.SetSingleDevice(devices.Get(0)->GetIfIndex());
    localAddress.SetProtocol(protocolNumber);

    if (sendSocket->Bind(localAddress) != 0)
    {
        std::cerr << "ERROR: PacketSocket::Bind failed.\n";
        return 1;
    }

    PacketSocketAddress sendAddress;
    sendAddress.SetSingleDevice(devices.Get(0)->GetIfIndex());
    sendAddress.SetPhysicalAddress(Mac48Address::GetBroadcast());
    sendAddress.SetProtocol(protocolNumber);
    if (sendSocket->Connect(sendAddress) != 0)
    {
        std::cerr << "ERROR: PacketSocket::Connect failed; the range test would "
                     "silently measure nothing.\n";
        return 1;
    }
    // SetAllowBroadcast is not needed: PacketSocket decides broadcast from the
    // destination MAC above. Its implementation returns !allowBroadcast and has
    // no effect on PacketSocket, so it is deliberately not called.

    for (uint32_t i = 0; i < nFrames; i++)
    {
        Simulator::Schedule(Seconds(1.0 + i * spacing), &SendOne, sendSocket, packetSize);
    }

    Simulator::Stop(Seconds(1.0 + nFrames * spacing + 1.0));
    Simulator::Run();

    if (g_sendFailures > 0)
    {
        std::cerr << "ERROR: " << g_sendFailures << " of " << nFrames
                  << " Send() calls failed. The socket is not usable; the result below "
                     "does NOT represent a radio range.\n";
    }
    else if (g_received == 0)
    {
        // Distinguish "out of range" from "the test is broken", which is what an
        // unbindable/unconnectable socket would produce.
        std::cerr << "WARNING: no frame was received at all, even at "
                  << distance << " m. Check that the sender socket is bound and "
                     "connected, and that both nodes use the same protocol number.\n";
    }

    // One line of machine-readable output, consumed by range_test.sh.
    std::cout << "distance_m=" << distance << " sent=" << nFrames << " received=" << g_received
              << " send_failures=" << g_sendFailures
              << " reachable=" << ((g_received == nFrames && g_sendFailures == 0) ? 1 : 0)
              << std::endl;

    Simulator::Destroy();
    return (g_sendFailures > 0) ? 1 : 0;
}
