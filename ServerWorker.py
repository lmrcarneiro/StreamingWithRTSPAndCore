from random import randint
import sys, traceback, threading, socket

from VideoStream import VideoStream
from RtpPacket import RtpPacket

class ServerWorker:
	SETUP = 'SETUP'
	PLAY = 'PLAY'
	PAUSE = 'PAUSE'
	TEARDOWN = 'TEARDOWN'
	
	INIT = 0
	READY = 1
	PLAYING = 2
	state = INIT

	OK_200 = 0
	FILE_NOT_FOUND_404 = 1
	CON_ERR_500 = 2
	
	clientInfo = {}
	
	def __init__(self, clientInfo):
		self.clientInfo = clientInfo
		self.fileName = "movie.Mjpeg"
		self.udpPort = 2021 # SPAGHETTI
		self.discoveredNodes = []

	def run(self):
		threading.Thread(target=self.recvRtspRequest).start()

		self.clientInfo["rtpSocket"] = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
		self.clientInfo['videoStream'] = VideoStream(self.fileName)
		self.clientInfo['rtpPort'] = 4567
		self.clientInfo['event'] = threading.Event()
		self.clientInfo['worker']= threading.Thread(target=self.sendRtp) 
		self.clientInfo['worker'].start()
	
	def recvRtspRequest(self):
		"""Receive RTSP request from the client."""
		connSocket = self.clientInfo['rtspSocket'][0]
		while True:            
			data = connSocket.recv(256)
			if data:
				print("Data received:\n" + data.decode("utf-8"))

	def sendRtp(self):
		"""Send RTP packets over UDP."""
		while True:
			self.clientInfo['event'].wait(0.05) 
			
			# Stop sending if request is PAUSE or TEARDOWN
			if self.clientInfo['event'].isSet(): 
				break 
				
			data = self.clientInfo['videoStream'].nextFrame()
			if data: 
				frameNumber = self.clientInfo['videoStream'].frameNbr()
				try:
					address = self.clientInfo['rtspSocket'][1][0]
					port = int(self.clientInfo['rtpPort'])
					print("Sending to",address,"with port",port)
					self.clientInfo['rtpSocket'].sendto(self.makeRtp(data, frameNumber),(address,port))
				except Exception as e:
					print("Connection Error. Exception is",e)
					print('-'*60)
					traceback.print_exc(file=sys.stdout)
					print('-'*60)
		# Close the RTP socket
		self.clientInfo['rtpSocket'].close()
		print("All done!")

	def makeRtp(self, payload, frameNbr):
		"""RTP-packetize the video data."""
		version = 2
		padding = 0
		extension = 0
		cc = 0
		marker = 0
		pt = 26 # MJPEG type
		seqnum = frameNbr
		ssrc = 0 
		
		rtpPacket = RtpPacket()
		
		rtpPacket.encode(version, padding, extension, cc, seqnum, marker, pt, ssrc, payload)
		
		return rtpPacket.getPacket()
