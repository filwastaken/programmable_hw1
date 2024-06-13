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
    def __init__(self, old_mac, new_mac, old_port, new_port):
        Event.__init__(self)
        self.old_mac = old_mac
        self.new_mac = new_mac
        self.old_port = old_port
        self.new_port = new_port

class HostTracker(EventMixin):

    _eventMixin_events = set([hostMoved])

    def __init__(self):
        core.openflow.addListeners(self)
        self.host_connected_switch = ""
        self.host_connected_networkcard = ""
        self.connected_host_mac = ""
        self.last_connected_networkcard = ""

        self.last_packet = -1

        self.host_addresses = set()
        self.max_hosts = 4 # There are 4 interfaces for the host

    def _handle_ConnectionUp(self, event):

        for h in range(1, self.max_hosts+1):
            arp_req = arp()
            arp_req.hwsrc = EthAddr("00:00:00:01:10:10")
            arp_req.opcode = arp.REQUEST
            arp_req.protodst = IPAddr(f"10.0.1.{str(h)}")
            arp_req.protosrc = IPAddr(f"10.0.1.{str(self.max_hosts+1)}")
            ether = ethernet()
            ether.type = ethernet.ARP_TYPE
            ether.dst = EthAddr.BROADCAST
            ether.src = EthAddr("00:00:00:01:10:10")
            ether.payload = arp_req
            msg = of.ofp_packet_out()
            msg.data = ether.pack()

            # Sending the message out to all ports
            for port_num in range(len(event.ofp.ports)):
                if port_num == 65534: continue # Do not send these requests to the controller

                msg.actions.append(of.ofp_action_output(port = port_num))
                event.connection.send(msg)


    def _handle_PacketIn(self, event):
        eth_frame = event.parsed.find("ethernet")
        if not ethernet: return

        # We are learning the mac of the host
        if eth_frame.type == ethernet.ARP_TYPE and eth_frame.dst == EthAddr("00:00:00:01:10:10"):
            arp_packet = event.parsed.find("arp")
            if arp_packet.opcode == arp.REPLY: self.host_addresses.add(eth_frame.src)
            return

        # Check that the packet is coming from the host
        if eth_frame.src not in self.host_addresses: return

        # Every switch will have packetIn installed, except for the fake gateway, who the host will be NOT connected to
        if event.dpid == core.FakeGateway.gateway_dpid: return

        # Raising event in case the host is connected to a different switch
        if self.host_connected_switch == event.dpid and self.host_connected_networkcard == event.port: return

        self.host_connected_switch = event.dpid
        self.host_connected_networkcard = event.port
        print(f"The host is connected to the switch with dpid {dpidToStr(self.host_connected_switch)} to the network card eth{self.host_connected_networkcard - 1}")
        self.raiseEvent(hostMoved(self.connected_host_mac, eth_frame.src, self.last_connected_networkcard, event.port))
        self.connected_host_mac = eth_frame.src
        self.last_connected_networkcard = event.port


def launch():
    core.registerNew(HostTracker)
    print("Host tracking succesfully registered")
