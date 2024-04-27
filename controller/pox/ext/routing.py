# Lib imports
from pox.core import core
from pox.lib.util import dpidToStr, strToDPID
import pox.openflow.libopenflow_01 as of

# Packet imports
from pox.lib.packet.ethernet import ethernet
from pox.lib.packet.arp import arp

# Addresses imports
from pox.lib.addresses import IPAddr, EthAddr

# Other imports
import numpy as np
import networkx as nx

# Own imports
from host_tracking import hostMoved

class Routing():
	def __init__(self):
		core.openflow.addListeners(self)
		core.HostTracker.addListeners(self)

		self.host_ip_mac = {}
		self.lastPath = []

		self.last_connected_link = ""
		self.new_connected_link = ""
	
	def _handle_hostMoved(self, event):
		switch_src = core.HostTracker.host_connected_switch
		switch_dst = core.FakeGateway.gateway_dpid
		
		if(switch_src == '' or switch_dst == ''):
			print(f"No route found from src ({switch_src}) to dst ({switch_dst}). If they appear to be blank, they will be populated soon.")
			return
		
		print(dpidToStr(switch_src))
		
		S = list(core.linkDiscovery.switch_id.keys())[list(core.linkDiscovery.switch_id.values()).index(switch_src)]
		D = list(core.linkDiscovery.switch_id.keys())[list(core.linkDiscovery.switch_id.values()).index(switch_dst)]
		
		print(S)
			
		# Getting the graph and adding weights by passing the last path used
		graph = core.linkDiscovery.getGraph(self.lastPath)

		# Saving the best path given the weights
		try:
			path = nx.dijkstra_path(graph, source=S, target=D, weight='weight')
		except nx.NetworkXNoPath:
			print(f"No route found from {switch_src} to {switch_dst}")
			return
			
		# Installing and removing the flow rules to every switch
		# Finding all the rules that should be installed by the new path:
		print(path)
		print(graph.adj)

		add_rules = []
		remove_rules = []

		for switch in range(len(path) - 1):
			add_rules.append(f"{path[switch]}_{path[switch+1]}")
			
		# Removing the rules that where already installed (all the rules that are not in the new path must be removed)
		for switch in range(len(self.lastPath) - 1):
			flow = f"{self.lastPath[switch]}_{self.lastPath[switch+1]}"
			if(flow in add_rules): add_rules.remove(flow)
			else: remove_rules.append(flow)
			
		self.lastPath = path

		# Installing and removing all the flowrules
		for rule in add_rules:
			link = core.linkDiscovery.links[rule]

			msg = of.ofp_flow_mod(command=of.OFPFC_ADD)
			msg.priority = 50000
			msg.match = of.ofp_match(dl_dst = core.FakeGateway.gateway_mac)
			msg.actions = [of.ofp_action_output(port = link.port1)]
			msg.priorityy = 42
			msg.match.dl_type = 0x800

			# Sending message
			core.openflow.sendToDPID(strToDPID(link.dpid1), msg)

		# Removing the unused rules
		for rule in remove_rules:
			link = core.linkDiscovery.links[rule]

			msg = of.ofp_flow_mod(command = of.OFPFC_DELETE)
			msg.match = of.ofp_match(dl_dst = core.FakeGateway.gateway_mac)
			core.openflow.sendToDPID(strToDPID(link.dpid1), msg)
		
		return None
			

def launch():
	core.registerNew(Routing)
	print("Routing with minumum changes installed")