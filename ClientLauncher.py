from tkinter import *
import tkinter.messagebox
from tkinter import ttk
from PIL import Image, ImageTk
import socket, threading, sys, traceback, os

from tkinter import Tk
from Client import Client

if __name__ == "__main__":
	try:
		serverAddr = sys.argv[1]
		serverPort = 25000
		rtpPort = 4567
		fileName = 'movie.Mjpeg'
		udpPort = 2021
	except:
		print("[Usage: ClientLauncher.py NextOverlayNodeIp]\n")	
	
	root = Tk()
	
	# Create a new client
	app = Client(root, serverAddr, serverPort, rtpPort, fileName, udpPort)
	app.master.title("RTPClient")	
	root.mainloop()
	