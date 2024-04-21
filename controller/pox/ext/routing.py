import pox.openflow.libopenflow_01 as of
from pox.core import core
from pox.lib.packet.ethernet import ethernet
from pox.lib.packet.arp import arp
from pox.lib.addresses import IPAddr, EthAddr
from pox.lib.util import dpidToStr

# Other imports
import numpy as np
import networkx as nx

class Routing():
	def __init__(self):
		core.openflow.addListeners(self)
		self.host_location = {}
		self.host_ip_mac = {}
		self.lastPath = []

		self.last_connected_link = ""
		self.new_connected_link = ""
	
	def _handle_hostMoved(self, event):
		# TODO: Change topography, search new route and send flow changes to switches (based on path)
		# ex. Copy below
		return None

	def _handle_PacketIn(self, event):
		eth_frame = event.parsed

		if eth_frame.type == ethernet.IP_TYPE:
			ip_pkt = eth_frame.payload
			ip_src = ip_pkt.srcip
			ip_dst = ip_pkt.dstip
			switch_src = self.host_location[ip_src.toStr()]
			switch_dst = self.host_location[ip_dst.toStr()]
			S = list(core.linkDiscovery.switch_id.keys())[list(core.linkDiscovery.switch_id.values()).index(switch_src)]
			D = list(core.linkDiscovery.switch_id.keys())[list(core.linkDiscovery.switch_id.values()).index(switch_dst)]
			
			# Getting the graph and adding weights by passing the last path used
			graph = core.linkDiscovery.getGraph(self.lastPath)

			# Saving the best path given the weights
			path = nx.shortest_path(graph, S, D)
			self.lastPath = path
			
			# Installing rules for all the elements in the path
			print(path)
			
			## Path differences
   			
			return None
		
			# TODO: Install and modify/remove flowrules based on the new path

			msg = of.ofp_flow_mod()
			msg.priority = 50000
			match = of.ofp_match(dl_src = EthAddr("00:11:22:33:44:55"))
			msg.match = match
			msg.actions = [of.ofp_action_output(port = of.OFPP_CONTROLLER)]
			core.openflow.sendToDPID(dpid, msg)

			msg = of.ofp_flow_mod(command=of.OFPFC_ADD)
			msg.priorityy = 42
			msg.match.dl_type = 0x800

def launch():
	Routing()
	print("Routing with minumum changes installed")