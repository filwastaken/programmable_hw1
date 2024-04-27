# Library imports
from pox.core import core
from pox.lib.util import  dpidToStr
import pox.openflow.libopenflow_01 as of
from pox.lib.addresses import EthAddr

# Event handling imports
from pox.lib.revent.revent import EventMixin

# Packet imports
from pox.lib.packet.ethernet import ethernet
from pox.lib.packet.arp import arp

class FakeGateway(EventMixin):
    def __init__(self):
        core.openflow.addListeners(self)
        self.gateway_mac = ""
        self.gateway_dpid = ""
    
    def _handle_ConnectionUp(self, event):
        # Obtaining mac address of gateway (I know ports list length given the network structure)
        if len(event.ofp.ports) !=  2: return
        if event.ofp.ports[0].name == "gw" or event.ofp.ports[1].name == "gw": self.gateway_dpid = event.dpid
        if event.ofp.ports[0].name == "gw": self.gateway_mac = event.ofp.ports[1].hw_addr
        elif event.ofp.ports[1].name == "gw" : self.gateway_mac = event.ofp.ports[0].hw_addr
        

    def _handle_PacketIn(self, event):
        arp_req = event.parsed.find("arp")
        
        if not arp_req or arp_req.opcode != arp.REQUEST: return

        # Ignoring fake_gateway and topology_discovery mac addresses
        if arp_req.hwsrc == EthAddr("00:00:00:00:11:22") or arp_req.hwsrc == EthAddr("00:11:22:33:44:55"): return

        print(f"Arp request recieved with source address {arp_req.hwsrc} and destination {arp_req.hwdst} on port {event.port} by switch {dpidToStr(event.dpid)}")

        # Creating arp response
        arp_reply = arp()
        arp_reply.hwsrc = self.gateway_mac
        arp_reply.hwdst = arp_req.hwsrc
        arp_reply.opcode = arp.REPLY
        arp_reply.protosrc = arp_req.protodst
        arp_reply.protodst = arp_req.protosrc

        # Creating ethernet message
        ether = ethernet()
        ether.type = ethernet.ARP_TYPE
        ether.dst = arp_req.hwsrc
        ether.src = self.gateway_mac
        ether.payload = arp_reply
        
        # Creating message
        msg = of.ofp_packet_out()
        msg.data = ether.pack()
        msg.in_port = event.port
        msg.actions.append(of.ofp_action_output(port = of.OFPP_IN_PORT))

        print(f"Arp reply sent to {arp_reply.hwdst} by \"{arp_reply.hwsrc}\" ({dpidToStr(event.dpid)}) on port {event.port}")

        # Sending message
        event.connection.send(msg)

def launch():
    core.registerNew(FakeGateway)
    print("ARP Responder succesfully registered")
