from tkinter import *
import tkinter.messagebox
from tkinter import ttk
from PIL import Image, ImageFile, ImageTk
import socket, threading, sys, traceback, os
from time import sleep

from RtpPacket import RtpPacket

CACHE_FILE_NAME = "cache-"
CACHE_FILE_EXT = ".jpg"

class Client:
	INIT = 0
	READY = 1
	PLAYING = 2
	
	SETUP = 0
	PLAY = 1
	PAUSE = 2
	TEARDOWN = 3

	#ImageFile.LOAD_TRUNCATED_IMAGES = True
	
	# Initiation..
	def __init__(self, master, serveraddr, serverport, rtpport, filename, udpport):
		self.master = master
		self.master.protocol("WM_DELETE_WINDOW", self.handler)
		self.createWidgets()
		self.serverAddr = serveraddr

		self.neighAlive = False
		self.aliveNeighLock = threading.Lock()

		self.serverPort = int(serverport)
		self.rtpPort = int(rtpport)
		self.fileName = filename
		self.sessionId = 0
		self.connectToServer()
		self.frameNbr = 0

		self.state = self.INIT

		self.udpPort = udpport
		self.nextNeigh = None
		self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
		# Bind the socket to the port
		server_address = ("", self.udpPort)
		self.sock.bind(server_address)
		print("Starting DISCOVER thread...")
		threading.Thread(target=self.listenUdp).start()

		print("Saying hello to neighbour!")
		self.sendUdp(serveraddr, "DISCOVER NOIP GO")

		print("Starting HEARTBEAT...") # to discover nodes that have left/crashed
		# ping neighbours every 10 seconds
		threading.Thread(target=self.sendHearbeat).start()
		
	def sendHearbeat(self):
		while True:
			sleep(10)
			if self.neighAlive == False:
				print("Neighbour",self.serverAddr,"is not alive!")
			if self.state == self.TEARDOWN:
				print("Exiting hearbeat thread...")
				break

			self.aliveNeighLock.acquire()
			self.neighAlive = False
			self.aliveNeighLock.release()
			self.sendUdp(self.serverAddr, "HEARTBEAT")

	def listenUdp(self):
		sock = self.sock

		print("####### Server is listening #######")
		while True:
			data, address = sock.recvfrom(1024)
			msg = data.decode('utf-8')
			if self.state == self.TEARDOWN:
				break
			print("\n\n Received:", msg, "\n\n")
			msg_list = msg.split(" ")
			
			if msg_list[0] == "HEARTBEAT" and (not self.state == self.TEARDOWN):
				self.sendUdp(address[0], "ACKED_HEARTBEAT")
			elif msg_list[0] == "ACKED_HEARTBEAT":
				self.aliveNeighLock.acquire()
				self.neighAlive = True
				self.aliveNeighLock.release()
			elif msg_list[2] == "RETURN":
				if self.nextNeigh is None:
					self.nextNeigh = address[0]
					print(self.nextNeigh,"is now my next neighbour")
					print("Announcing my next neighbour!")
					self.sendUdp(self.nextNeigh, "ANNOUNCE NOIP")
				
				if len(msg_list) == 3: # é o próprio nó quem mandou o discover
					print("I sent the DISCOVER myself!")
				else:
					print("Something went very wrong!")
			else:
				print("2. Something went very wrong!")
			

	def sendUdp(self, neigh, msg):
		sock = self.sock
		sock.sendto(msg.encode('utf-8'), (neigh, self.udpPort))
		print("Sent", msg, "to", neigh)

	def createWidgets(self):
		"""Build GUI."""
		# Create Setup button
		self.setup = Button(self.master, width=20, padx=3, pady=3)
		self.setup["text"] = "Setup"
		self.setup["command"] = self.setupMovie
		self.setup.grid(row=1, column=0, padx=2, pady=2)
		
		# Create Play button		
		self.start = Button(self.master, width=20, padx=3, pady=3)
		self.start["text"] = "Play"
		self.start["command"] = self.playMovie
		self.start.grid(row=1, column=1, padx=2, pady=2)
		
		# Create Pause button			
		self.pause = Button(self.master, width=20, padx=3, pady=3)
		self.pause["text"] = "Pause"
		self.pause["command"] = self.pauseMovie
		self.pause.grid(row=1, column=2, padx=2, pady=2)
		
		# Create Teardown button
		self.teardown = Button(self.master, width=20, padx=3, pady=3)
		self.teardown["text"] = "Teardown"
		self.teardown["command"] =  self.exitClient
		self.teardown.grid(row=1, column=3, padx=2, pady=2)
		
		# Create a label to display the movie
		self.label = Label(self.master, height=19)
		self.label.grid(row=0, column=0, columnspan=4, sticky=W+E+N+S, padx=5, pady=5) 
	
	def setupMovie(self):
		"""Setup button handler."""
		if self.state == self.INIT:
			self.sendRtspRequest(self.SETUP)
	
	def exitClient(self):
		"""Teardown button handler."""
		self.sendRtspRequest(self.TEARDOWN)		
		self.master.destroy() # Close the gui window
		os.remove(CACHE_FILE_NAME + str(self.sessionId) + CACHE_FILE_EXT) # Delete the cache image from video

	def pauseMovie(self):
		"""Pause button handler."""
		if self.state == self.PLAYING:
			self.sendRtspRequest(self.PAUSE)
	
	def playMovie(self):
		"""Play button handler."""
		if self.state == self.READY:
			# Create a new thread to listen for RTP packets
			threading.Thread(target=self.listenRtp).start()
			self.playEvent = threading.Event()
			self.playEvent.clear()
			self.sendRtspRequest(self.PLAY)
	
	def listenRtp(self):		
		"""Listen for RTP packets."""
		while True:
			try:
				data = self.rtpSocket.recv(20480)
				if data:
					rtpPacket = RtpPacket()
					rtpPacket.decode(data)
					
					currFrameNbr = rtpPacket.seqNum()
					print("Current Seq Num: " + str(currFrameNbr))
					if currFrameNbr > self.frameNbr: # Discard the late packet
						self.frameNbr = currFrameNbr
						self.updateMovie(self.writeFrame(rtpPacket.getPayload()))
			except:
				# Stop listening upon requesting PAUSE or TEARDOWN
				if self.playEvent.isSet(): 
					break
				
				self.rtpSocket.shutdown(socket.SHUT_RDWR)
				self.rtpSocket.close()
				break
					
	def writeFrame(self, data):
		"""Write the received frame to a temp image file. Return the image file."""
		cachename = CACHE_FILE_NAME + str(self.sessionId) + CACHE_FILE_EXT
		file = open(cachename, "wb")
		file.write(data)
		file.close()
		
		return cachename
	
	def updateMovie(self, imageFile):
		"""Update the image file as video frame in the GUI."""
		photo = ImageTk.PhotoImage(Image.open(imageFile))
		self.label.configure(image = photo, height=288) 
		self.label.image = photo
		
	def connectToServer(self):
		"""Connect to the Server. Start a new RTSP/TCP session."""
		self.rtspSocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
		try:
			self.rtspSocket.connect((self.serverAddr, self.serverPort))
		except:
			messagebox.showwarning('Connection Failed', 'Connection to \'%s\' failed.' %self.serverAddr)
	
	def sendRtspRequest(self, requestCode):
		"""Send RTSP request to the server."""	
		
		# Setup request
		if requestCode == self.SETUP and self.state == self.INIT:
			# Write the RTSP request to be sent.
			request = "SETUP"
			self.openRtpPort()
			self.state = self.READY 
		
		# Play request
		elif requestCode == self.PLAY and self.state == self.READY:
			print('\nPLAY event\n')
			
			request = "PLAY"
			self.state = self.PLAYING
		
		# Pause request
		elif requestCode == self.PAUSE and self.state == self.PLAYING:
			print('\nPAUSE event\n')
			
			request = "PAUSE"
			self.state = self.READY
			
		# Teardown request
		elif requestCode == self.TEARDOWN and not self.state == self.INIT:
			print('\nTEARDOWN event\n')
			
			request = "TEARDOWN"
			self.state = self.TEARDOWN
		else:
			return
		
		# Send the RTSP request using rtspSocket.
		self.rtspSocket.send(request.encode("utf-8"))
		print('\nData sent:\n' + request)
	
	def openRtpPort(self):
		"""Open RTP socket binded to a specified port."""
		
		# Create a new datagram socket to receive RTP packets from the server
		self.rtpSocket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
		
		try:
			# Bind the socket to the address using the RTP port given by the client user
			self.rtpSocket.bind(('', self.rtpPort))
			print('\nBind \n')
		except socket.error as message:
			messagebox.showwarning('Unable to Bind', 'Unable to bind PORT=%d' %self.rtpPort + str(massage[0]) + ' Message ' + massage[1])

	def handler(self):
		"""Handler on explicitly closing the GUI window."""
		self.pauseMovie()
		if messagebox.askokcancel("Quit?", "Are you sure you want to quit?"):
			self.exitClient()
		else: # When the user presses cancel, resume playing.
			self.playMovie()
