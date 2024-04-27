# Library imports
from pox.core import core
import pox.openflow.libopenflow_01 as of
from pox.lib.addresses import EthAddr, IPAddr
from pox.lib.util import dpidToStr

# Event handling imports
from pox.lib.revent.revent import Event, EventMixin

# Packet imports
from pox.lib.packet.ethernet import ethernet
from pox.lib.packet.arp import arp


class hostMoved(Event):
    def __init__(self):
        Event.__init__(self)

class HostTracker(EventMixin):

    _eventMixin_events = set([hostMoved])

    def __init__(self):
        core.openflow.addListeners(self)
        self.host_connected_switch = ""
        self.host_connected_networkcard = ""

        self.host_addresses = set()

        self.ip6_hop = -1
        self.ip4_hop = -1
        self.max_hosts = 4 # There are 4 interfaces for the host
    
    def _handle_ConnectionUp(self, event):
        conn = event.connection

        for h in range(1, self.max_hosts+1):
            arp_req = arp()
            arp_req.hwsrc = EthAddr("00:00:00:00:11:22")
            arp_req.opcode = arp.REQUEST
            arp_req.protodst = IPAddr(f"10.0.1.{str(h)}")
            arp_req.protosrc = IPAddr(f"10.0.1.{str(self.max_hosts+1)}")
            ether = ethernet()
            ether.type = ethernet.ARP_TYPE
            ether.dst = EthAddr.BROADCAST
            ether.src = EthAddr("00:00:00:00:11:22")
            ether.payload = arp_req
            msg = of.ofp_packet_out()
            msg.data = ether.pack()

            # Sending the message out to all ports
            for port_num in range(len(event.ofp.ports)):
                msg.actions.append(of.ofp_action_output(port = port_num))
                conn.send(msg)

    def _handle_PacketIn(self, event):
        eth_frame = event.parsed.find("ethernet")
        if not ethernet: return

        # We are learning the mac of the host
        if eth_frame.type == ethernet.ARP_TYPE and eth_frame.dst == EthAddr("00:00:00:00:11:22"):
            arp_packet = event.parsed.find("arp")
            if arp_packet.opcode == arp.REPLY: self.host_addresses.add(eth_frame.src)
            return

        # Check that the packet is coming from the host
        if eth_frame.src not in self.host_addresses: return

        # Get the ip packet:
        ip4 = event.parsed.find('ipv4')
        ip6 = event.parsed.find('ipv6')

        # If it is the first time I'm seeing this packet, it must have the maximum ttl (or hop_limit)
        if ip6 is not None:
            hop_limit = ip6.hop_limit
            if hop_limit < self.ip6_hop: return
            self.ip6_hop = hop_limit
        elif ip4 is not None:
            ttl = ip4.ttl
            if ttl < self.ip4_hop: return
            self.ip4_hop = ttl

        # Raising event in case the host is connected to a different switch
        if self.host_connected_switch == event.dpid and self.host_connected_networkcard == event.port - 1:
            return

        self.host_connected_switch = event.dpid
        self.host_connected_networkcard = event.port - 1
        print(f"The host is connected to the switch with dpid {dpidToStr(self.host_connected_switch)} to the network card eth{self.host_connected_networkcard}")
        self.raiseEvent(hostMoved())


def launch():
    core.registerNew(HostTracker)
    print("Host tracking succesfully registered")
