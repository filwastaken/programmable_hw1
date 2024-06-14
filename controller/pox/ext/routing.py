# Lib imports
from pox.core import core
from pox.lib.util import strToDPID
import pox.openflow.libopenflow_01 as of
from pox.lib.recoco import Timer

# Other imports
import networkx as nx

# Own imports
from host_tracking import hostMoved

class Routing():
	def __init__(self):
		core.openflow.addListeners(self)
		core.HostTracker.addListeners(self)

		self.lastPath = []
	
	def _handle_hostMoved(self, event):
		switch_src = core.HostTracker.host_connected_switch
		switch_dst = core.FakeGateway.gateway_dpid
		
		if(switch_src == '' or switch_dst == ''):
			print(f"No route found from src ({switch_src}) to dst ({switch_dst}). If they appear blank, they will be populated soon.")
			# Waiting 5 seconds before trying again
			Timer(5, self._handle_hostMoved, args=[event], recurring=False)
			return

		S = list(core.linkDiscovery.switch_id.keys())[list(core.linkDiscovery.switch_id.values()).index(switch_src)]
		D = list(core.linkDiscovery.switch_id.keys())[list(core.linkDiscovery.switch_id.values()).index(switch_dst)]

		# Getting the graph and adding weights by passing the last path used
		graph = core.linkDiscovery.getGraph(self.lastPath)

		# Saving the best path given the weights
		try:
			path = nx.dijkstra_path(graph, source=S, target=D, weight='weight')
		except nx.NetworkXNoPath:
			print(f"No route found from {switch_src} to {switch_dst}")

			# Waiting 5 seconds before trying again
			Timer(5, self._handle_hostMoved, args=[event], recurring=False)
			return
			
		# Installing and removing the flow rules to every switch
		# Finding all the rules that should be installed by the new path:
		add_rules = []
		remove_rules = []

		for switch in range(len(path) - 1):
			add_rules.append(f"{path[switch]}_{path[switch+1]}")
			
		# Removing the rules that where already installed (all the rules that are not in the new path must be removed)
		for switch in range(len(self.lastPath) - 1):
			flow = f"{self.lastPath[switch]}_{self.lastPath[switch+1]}"
			if(flow in add_rules): add_rules.remove(flow)
			else: remove_rules.append(flow)
		
		# Delete old flowrule
		if len(self.lastPath) != 0 and event.old_mac != "" and self.lastPath[0] != path[0]:
			print("Deleted old rule from switch to host:")
			old_first_link = core.linkDiscovery.links[f'{self.lastPath[0]}_{self.lastPath[1]}']
			self.install_flowrule(of.OFPFC_DELETE, old_first_link.sid1, 'host', old_first_link.dpid1, event.old_mac, event.old_port)

		# Removing the unused rules
		if len(remove_rules) > 0: print("Removed the following flows:")
		for rule in remove_rules:
			link = core.linkDiscovery.links[rule]

			# Removing two flow rule, from sid1 to sid2 and vice-versa
			self.install_flowrule(of.OFPFC_DELETE, link.sid1, link.sid2, link.dpid1, core.FakeGateway.gateway_mac, link.port1)
			self.install_flowrule(of.OFPFC_DELETE, link.sid2, link.sid1, link.dpid2, event.old_mac, link.port2)
		
		# Installing and removing all the flowrules
		if len(add_rules) > 0: print("Installed the following flows:")
		for rule in add_rules:
			link = core.linkDiscovery.links[rule]

			# Installing two flow rule, from sid1 to sid2 and vice-versa
			self.install_flowrule(of.OFPFC_ADD, link.sid1, link.sid2, link.dpid1, core.FakeGateway.gateway_mac, link.port1)
			self.install_flowrule(of.OFPFC_ADD, link.sid2, link.sid1, link.dpid2, event.new_mac, link.port2)
		
		# Updating flowrules from switch to host
		print("Installed new rule from switch to host:")
		new_first_link = core.linkDiscovery.links[f'{path[0]}_{path[1]}']
		self.install_flowrule(of.OFPFC_ADD, new_first_link.sid1, 'host', new_first_link.dpid1, event.new_mac, event.new_port)
		
		print(f"Previous path: {self.lastPath}, current path: {path}, items to install: {add_rules} and items to remove: {remove_rules}")
		self.lastPath = path

		return None
	
	def install_flowrule(self, command, sid1, sid2, dpid1, mac_address, output_port):
		match = of.ofp_match(dl_dst = mac_address)

		msg = of.ofp_flow_mod(
			command = command,
			priority = 42,
			match = match,
			actions = [of.ofp_action_output(port = output_port)]
		)

		if dpid1 != core.FakeGateway.gateway_dpid: core.openflow.sendToDPID(strToDPID(dpid1), msg)
		print(f"\tOn {dpid1} from {sid1} ----> {sid2} with destination mac {mac_address} and output port {output_port}")

def launch():
	core.registerNew(Routing)
	print("Routing with minumum changes installed")