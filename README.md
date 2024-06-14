# Programmable network, first homework
This project creates the following pox applications:
- Fake Gateway, implemented in [fake_gateway.py](/controller/pox/ext/fake_gateway.py)
- Host Tracking, implemented in [host_tracking.py](/controller/pox/ext/host_tracking.py)
- Routing, implemented in [routing.py](/controller/pox/ext/routing.py)
- Topology Discovery, implemented in [topology_discovery.py](/controller/pox/ext/topology_discovery.py)

This project is built upon the following [topology]()

# Topology Discovery
Topology discovery installs two handles to discover the topology dinamically:
1. _handle_ConnectionUp ([line 40](TODO: add permalink))
2. _handle_PacketIn ([line 33](TODO: add permalink))

## ConnectionUp event
Once a switch connects to the controller, it is saved into a list used to send probes. In particular, it sends an arp packet with the source ethernet address
```python
mac_src = EthAddr("00:00:00:01:10:11")
```
and the destination address
```python
mac_dst = EthAddr("00:00:00:00:" + str(sid) + ":" + str(port.port_no))
```
through every switch interfaces (other than the one that connects the switch to the controller).

## PacketIn event
Once a packetIn is triggered with source address equals to "00:00:00:01:10:11", the destination address is used to find the link between the two switch. In particular, a link is defined as the two switch sid's, dpid's and the ports that connect the two.

```python
class Link():
	def __init__(self, sid1, sid2, dpid1, port1, dpid2, port2):
		self.name = str(sid1) + "_" + str(sid2)
		self.sid1 = sid1
		self.sid2 = sid2
		self.dpid1 = dpidToStr(dpid1)
		self.dpid2 = dpidToStr(dpid2)
		self.port1 = int(port1)
		self.port2 = int(port2)
```

## getGraph function
Furthermore, topology discovery defines the 'getGraph' function, used to obtained the weighted graph based on the discovered topology, where the weights are adjusted to minimize the number of rule changes when the host moves.

```python
def getGraph(self, lastPath):
	N = len(self.switches)

	if len(lastPath) == 0:
		adj = np.zeros((N, N))
		for link in self.links: adj[self.links[link].sid1, self.links[link].sid2] = 1
		self.graph = nx.Graph(adj)
	else:
		for index in range(len(lastPath)):
			switch = lastPath[index]

			for connected_switch in self.graph[switch]:
				if (index == 0 and lastPath[1] == connected_switch) or \
				(index == len(lastPath) - 1 and lastPath[index - 1] == connected_switch) or \
				(index > 0 and index < len(lastPath) -1 and (lastPath[index - 1] == connected_switch or lastPath[index + 1] == connected_switch)):
					self.graph[switch][connected_switch]['weight'] = 0
				else:
					# It does self.graph[connected_switch][switch] automatically
					self.graph[switch][connected_switch]['weight'] = 2

					_switch_pos = lastPath.index(switch)

					if (_switch_pos == 0 and not lastPath[1] == connected_switch) or \
					(_switch_pos == len(lastPath) - 1 and not lastPath[-2] == connected_switch) or \
					(_switch_pos > 0 and _switch_pos < len(lastPath) - 1 and not (lastPath[_switch_pos - 1] == connected_switch or lastPath[_switch_pos + 1] == connected_switch)):
						self.graph[switch][connected_switch]['weight'] += (lastPath.index(switch) + 1)
```

link to the function: [getGraph](TODO: Add permalink)

# Host tracking
Host tracking installs two handlers to follow a mobile host through different access points, represented as a connection to a particular switch interface:
1. _handle_ConnectionUp, ([line 38](TODO: add permalink))
2. _handle_PacketIn, ([line 62](TODO: add permalink))

## ConnectionUp event
On ConnectionUp, every switch tries to find any connected host by sending an arp request through any port not connected to the controller. In particlar, it sets the source address as:
```python
arp_req.hwsrc = EthAddr("00:00:00:01:10:10")
ether.src = EthAddr("00:00:00:01:10:10")
```

## PacketIn event
On packet in we check the ethernet type and ethernet destination address. If they are respectivly an ARP reply and the ethernet destination is the once we set as source before, we have just learnt the ethernet address of the host.
```python
# We are learning the mac of the host
if eth_frame.type == ethernet.ARP_TYPE and eth_frame.dst == EthAddr("00:00:00:01:10:10"):
	arp_packet = event.parsed.find("arp")
	if arp_packet.opcode == arp.REPLY: self.host_addresses.add(eth_frame.src)
		return
```
Otherwise we check every packet that comes from the host and check wheter it is recieved from a different switch than the saved switch, keeping track where the host was last connected. If it changed, we can save the connected host, the port the packet came through and raise an 'hostMoved' event

```python
class hostMoved(Event):
	def __init__(self, old_mac, new_mac, old_port, new_port):
		Event.__init__(self)
		self.old_mac = old_mac
		self.new_mac = new_mac
		self.old_port = old_port
		self.new_port = new_port

	def _handle_PacketIn(self, event){
		...

		self.host_connected_switch = event.dpid
		self.host_connected_networkcard = event.port
		print(f"The host is connected to the switch with dpid {dpidToStr(self.host_connected_switch)} to the network card eth{self.host_connected_networkcard - 1}")
		self.raiseEvent(hostMoved(self.connected_host_mac, eth_frame.src, self.last_connected_networkcard, event.port))
		self.connected_host_mac = eth_frame.src
		self.last_connected_networkcard = event.port
	}
```

# Routing
The routing app installs the hostMoved handle. Every time this function is called, the minimum path is found with the networkx library. At this point, simple logic is used to divide between the flows that needs to be added and removed based on the existing path and the calculated path in the following manner:

```python
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
```

Furthermore, a timer is used to call the function again in case there are missing information, such as the switch dpid the host is connected to or the switch dpid. The timer is used in case no path can be found too. This may occur in case the pox application has not yet found all links and finished building the graph.

# Fake Gateway
The fake gateway installs two handlers to use a switch as a fake gateway towards the internet:
1. _handle_ConnectionUp, ([line 38](TODO: add permalink))
2. _handle_packetIn, ([line 38](TODO: add permalink))

## ConnectionUp event
On Connection Up the function returns for every switch that is not the fake gateway, saving the gateway dpid. In particular, the gateway ethernet address and the port number of the interface going towards the internet as well as those of the interface towards the other pox switches.

## PacketIn event
On Packet in the function we handle mac requests, handle gateway routing and store messages that cannot yet be sent.

### Gateway routing
If the switch running the PacketIn event is the fake gateway switch, then we can first learn about the ethernet address associated to a particular ip if not known and call the function [handle_gateway_routing](TODO: add permalink)

### Handle mac requests
Otherwise, any switch will handle mac requests by first ignoring any 'fake' arp requests that were generated by fake_gateway, host_tracking and topology discovery. Once it has been assured that the arp request is from a valid host, the switch will reply with an arp reply with the gateway mac as the source address. This true of course as long as the gateway mac address is known, otherwise the requests is just dropped. This may happen because a request arrived before the switch representing the fake gateway has connected.

link to the function: [handle_mac_requests](TODO: Add permalink)

### Handle Gateway Routing
This function handles messages passing through the fake gateway. In particular, it manages the flow rules between two hosts separated by the gateway: one managed by the pox network, one in the internet. Once any non-arp message is recieved by the fake-gateway, as long as the switch knows both ethernet addresses for the two hosts, it will install the flow rules with the function [install_bidirectional_flowrules](TODO: Add perma link). Once the flowrule is installed it emptys the message queue for all the messages that apply to that flow and sends the messages. Otherwise, if the ethernet is not known for the destination, an arp request is made. Upon recieving an arp reply messages, the mac is saved in a dictionary and the messages are sent since both ethernet address of the source and destination are known.

## Bidirectional flow rule installation
This function handles the installation of two flows for any connection. In particular, it changes the source ethernet address with the fake gateway address, as in a SNAT and sets the destination address as the real ethernet address: by default the destination address is the gateway address since any switch will reply with the gateway MAC for any arp requests.

```python
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
```
