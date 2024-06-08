#!/bin/python3

import random, subprocess
import argparse
import signal

def sigint(num, frame):
	print("\nClosing....\n")
	exit(0)

def sigstp(num, frame):
	print("\nResetting network cards")
	subprocess.call("ifconfig eth0 down && ifconfig eth1 down && ifconfig eth2 down && ifconfig eth3 down", shell=True)
	print("Closing....\n")
	exit(0)

def main(host):
	subprocess.call("ifconfig eth0 down && ifconfig eth1 down && ifconfig eth2 down && ifconfig eth3 down", shell=True)

	while True:
		interface = random.randint(0, 3)
		amount = random.randint(2, 20)

		subprocess.call(f"ifconfig eth{interface} up", shell=True)
		print(f"Sending {amount} pings to {host} via the interface eth{interface}")
		subprocess.call(f"ping {host} -c {amount} -I eth{interface}", shell=True)
		print("----------------------------------------------------------\nDone!\n")
		subprocess.call(f"ifconfig eth{interface} down", shell=True)

if __name__ == "__main__":
	parser = argparse.ArgumentParser(prog="Python mobility simulator", description="This program simulates the movement of an host in python", epilog="Use Ctrl+C to close the program and Ctrl+Z to close and reset the network configuration")
	parser.add_argument('-ho', '--host', type=str, default="192.168.1.1")
	args = parser.parse_args()

	# SIGINT handler
	sigint_handler = signal.getsignal(signal.SIGINT)
	signal.signal(signal.SIGINT, sigint)

	# SIGSTP handler
	sigint_handler = signal.getsignal(signal.SIGTSTP)
	signal.signal(signal.SIGTSTP, sigstp)
	
	main(args.host)
