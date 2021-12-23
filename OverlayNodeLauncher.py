from PIL import Image, ImageTk
import socket, threading, sys, traceback, os

from OverlayNode import OverlayNode

class OverlayNodeLauncher:

	def main(self):
		try:
			self.udpPort = 2021
			self.rtspPort = 25000
			self.rtpPort = 4567
			self.neighbours = []
			for i in range(1, len(sys.argv)):
				self.neighbours.append(sys.argv[i])
		except:
			print("[Usage: OverlayNodeLauncher.py Neighbour1 Neighbour2 etc...]\n")
		OverlayNode(self.udpPort, self.rtspPort, self.rtpPort, self.neighbours).run()
	
if __name__ == "__main__":
	(OverlayNodeLauncher()).main()