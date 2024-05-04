# Library imports
from pox.core import core
from pox.lib.util import  dpidToStr
import pox.openflow.libopenflow_01 as of
from pox.lib.addresses import EthAddr, IPAddr

# Event handling imports
from pox.lib.revent.revent import EventMixin

# Packet imports
from pox.lib.packet.ethernet import ethernet
from pox.lib.packet.arp import arp

class FakeGateway(EventMixin):

    __OLD_MESSAGES_MAX = 250

    def __init__(self):
        core.openflow.addListeners(self)

        self.gateway_dpid = ""
        self.gateway_mac = ""

        self.pox_net_port = ""
        self.internet_port = -1

        self.saved_macs = {}
        self.old_messages = []
    
    def _handle_ConnectionUp(self, event):
        # Obtaining mac address of gateway and "internet" host
        found = False
        for port in event.ofp.ports:
            if port.name == "gw": found = True
        
        if not found: return

        self.gateway_dpid = event.dpid
        for port in event.ofp.ports:
            if port.name == "eth0":
                self.internet_port = port.port_no
                self.saved_macs[IPAddr("192.168.1.0")] = port.hw_addr
            elif port.name == "eth1":
                self.gateway_mac = port.hw_addr
                self.pox_net_port = port.port_no

    def _handle_PacketIn(self, event):
        arp_message = event.parsed.find("arp")
        eth_frame = event.parsed.find("ethernet")
        ip4 = event.parsed.find("ipv4")

        if event.dpid == self.gateway_dpid:
            # If it's an IPv4 packet saving the ip-mac (as long as the mac is not the gateway)
            if ip4 is not None and eth_frame.src != self.gateway_mac and self.saved_macs.get(ip4.srcip) is None:
                self.saved_macs[ip4.srcip] = eth_frame.src
            self.handle_gateway_routing(event, eth_frame, ip4, arp_message)

        self.handle_mac_requests(event, arp_message, eth_frame)

        if len(self.old_messages) > 0:
            print("Stored messages: ")
            for eth_index in range(len(self.old_messages)):
                eth_frame = self.old_messages[eth_index]
                print(f"\tMessage {eth_index}: source mac address is {eth_frame.src}, destination mac address is {eth_frame.dst}")

    def handle_gateway_routing(self, event, eth_frame, ip4, arp_message):
        if not eth_frame: return

        ip_source = ""
        ip_dest = ""

        # If it's a response from the internet with the mac address
        if arp_message:
            # Ignoring fake_gateway, host_tracking and topology_discovery custom arp requests
            if arp_message.hwsrc == EthAddr("00:00:00:01:10:01") or arp_message.hwsrc == EthAddr("00:00:00:01:10:10") or arp_message.hwsrc == EthAddr("00:00:00:01:10:11"): return
            if arp_message.hwdst == EthAddr("00:00:00:01:10:10") or  arp_message.hwdst == EthAddr("00:00:00:01:10:11"): return

            if arp_message.hwdst == EthAddr("00:00:00:01:10:01") and arp_message.opcode == arp.REPLY:
                self.saved_macs[arp_message.protosrc] = arp_message.hwsrc
                ip_source = arp_message.protodst
                ip_dest = arp_message.protosrc

        elif ip4: # Otherwise if it's an IPv4 and not an ARP message
            ip_source = ip4.srcip
            ip_dest = ip4.dstip
        else:
            raise Exception("Case not handled")

        if ip_source == "" or ip_dest == "": return

        # If the mac addresses are known
        if self.saved_macs.get(ip_source) is not None and self.saved_macs.get(ip_dest) is not None:
            # Installing flow rule
            self.install_bidirectional_flowrule(ip_source, ip_dest)

            # Emptying the message queue based on the installed flowrule
            index = 0
            while index < len(self.old_messages):
                saved_eth_frame = self.old_messages[index]

                # Manually applying flow rules:
                if saved_eth_frame.payload.srcip == ip_source and saved_eth_frame.payload.dstip == ip_dest:
                    # "First flow" in bidirectional_flowrule
                    saved_eth_frame.src = self.gateway_mac
                    saved_eth_frame.dst = self.saved_macs.get(ip_dest)
                elif saved_eth_frame.payload.srcip == ip_dest and saved_eth_frame.payload.dstip == ip_sourcrp_message.protodst:
                    # "Second flow" in bidirectional_flowrule
                    saved_eth_frame.src = self.gateway_mac
                    saved_eth_frame.dst = self.saved_macs.get(ip_source)
                else:
                    index += 1
                    continue

                msg = of.ofp_packet_out()
                msg.data = saved_eth_frame.pack()
                event.connection.send(msg)
                self.old_messages.pop(index)

        # Gateway doesn't know the IP's mac: set an arp request, install flow rule upon response (above)
        elif ip4:
            arp_req = arp(
                hwsrc = EthAddr("00:00:00:01:10:01"),
                opcode = arp.REQUEST,
                protodst = IPAddr(f"{ip4.dstip}"),
                protosrc = IPAddr(f"{ip4.srcip}")
            )

            ether = ethernet(
                type = ethernet.ARP_TYPE,
                dst = EthAddr.BROADCAST,
                src = EthAddr("00:00:00:01:10:01"),
                payload = arp_req
            )

            msg = of.ofp_packet_out()
            msg.data = ether.pack()
            msg.actions.append(of.ofp_action_output(port = self.internet_port))

            event.connection.send(msg)

            if(len(self.old_messages) >= FakeGateway.__OLD_MESSAGES_MAX):
                self.old_messages = self.old_messages[25:]
    
            self.old_messages.append(eth_frame)

    def handle_mac_requests(self, event, arp_req, eth_frame):
        if not arp_req or arp_req.opcode != arp.REQUEST: return

        # Ignoring fake_gateway, host_tracking and topology_discovery custom arp requests
        if arp_req.hwsrc == EthAddr("00:00:00:01:10:01") or arp_req.hwsrc == EthAddr("00:00:00:01:10:10") or arp_req.hwsrc == EthAddr("00:00:00:01:10:11"): return
        if arp_req.hwdst == EthAddr("00:00:00:01:10:01") or arp_req.hwdst == EthAddr("00:00:00:01:10:10") or arp_req.hwdst == EthAddr("00:00:00:01:10:11"): return

        # Topology discovery sets addresses in the ethernet frame, checking that as well
        if eth_frame and (eth_frame.src == EthAddr("00:00:00:01:10:11") or eth_frame.dst == EthAddr("00:00:00:01:10:11")): return

        print(f"Arp request recieved on port {event.port} by switch {dpidToStr(event.dpid)}.\nARP source: {arp_req.hwsrc}, ARP destination: {arp_req.hwdst}, Eth frame src: {eth_frame.src}, eth frame dst: {eth_frame.dst}")

        # Creating arp response
        arp_reply = arp(
            hwsrc = self.gateway_mac,
            hwdst = arp_req.hwsrc,
            opcode = arp.REPLY,
            protosrc = arp_req.protodst,
            protodst = arp_req.protosrc
        )

        # Creating ethernet message
        ether = ethernet(
            type = ethernet.ARP_TYPE,
            dst = arp_req.hwsrc,
            src = self.gateway_mac,
            payload = arp_reply
        )
        
        # Creating message
        msg = of.ofp_packet_out()
        msg.data = ether.pack()
        msg.in_port = event.port
        msg.actions.append(of.ofp_action_output(port = of.OFPP_IN_PORT))

        print(f"Arp reply sent to {arp_reply.hwdst} by \"{arp_reply.hwsrc}\" ({dpidToStr(event.dpid)}) on port {event.port}")

        # Sending message
        event.connection.send(msg)

    
    def install_bidirectional_flowrule(self, source_ip, destination_ip):
        source_mac = self.saved_macs.get(source_ip)
        dest_mac = self.saved_macs.get(destination_ip)

        # First match (from sender to reciver)
        first_flow_match = of.ofp_match(
            dl_src = source_mac,
            dl_type  = 0x800, # IPv4
            nw_src = source_ip,
            nw_dst = destination_ip
        )

        # Second match (reciever eventual response)
        second_flow_match = of.ofp_match(
            dl_src = dest_mac,
            dl_type  = 0x800, # IPv4
            nw_src = destination_ip,
            nw_dst = source_ip
        )
        
        change_src = of.ofp_action_dl_addr().set_src(self.gateway_mac)
        first_flow_change_dest = of.ofp_action_dl_addr().set_dst(dest_mac)
        second_flow_change_dest= of.ofp_action_dl_addr().set_dst(source_mac)

        first_flow_actions = [change_src, first_flow_change_dest, of.ofp_action_output(port = self.internet_port)]
        second_flow_actions = [change_src, second_flow_change_dest, of.ofp_action_output(port = self.pox_net_port)]

        first_msg = of.ofp_flow_mod(
            command=of.OFPFC_ADD,
            priority = 42,
            match = first_flow_match,
            actions = first_flow_actions
        )

        second_msg = of.ofp_flow_mod(
            command=of.OFPFC_ADD,
            priority = 42,
            match = second_flow_match,
            actions = second_flow_actions
        )

        core.openflow.sendToDPID(self.gateway_dpid, first_msg)
        core.openflow.sendToDPID(self.gateway_dpid, second_msg)

        print(f"Flow rule installed: {source_ip} <----> {destination_ip} via {dpidToStr(self.gateway_dpid)} ({self.gateway_mac})")


def launch():
    core.registerNew(FakeGateway)
    print("Fake Gateway succesfully registered")