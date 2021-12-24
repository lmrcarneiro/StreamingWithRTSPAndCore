from tkinter import *
import tkinter.messagebox
from tkinter import ttk
from PIL import Image, ImageTk
import socket, threading, sys, traceback, os
import logging
import threading
from time import sleep
import datetime

from RtpPacket import RtpPacket

class OverlayNode:

	SETUP = 'SETUP'
	PLAY = 'PLAY'
	PAUSE = 'PAUSE'
	TEARDOWN = 'TEARDOWN'
	
	INIT = 0
	READY = 1
	PLAYING = 2

	def __init__(self, udpport, rtspport, rtpport, neighbours):
		self.udpPort = udpport
		self.rtspPort = rtspport
		self.rtpPort = rtpport
		self.neighbours = neighbours
		
		self.neighboursAlive = [False] * len(self.neighbours)
		self.aliveNeighsLock = threading.Lock()
		
		self.nextNeigh = None
		self.timestampDiscNeigh = []
		self.timeForDiscoveringLastNeigh = datetime.datetime.min
		self.prevTimeForDiscoveringLastNeigh = datetime.datetime.min
		self.reachableClients = []
		self.clientIsPlaying = []
		self.nextNodeToReachClient = []

	def run(self):
		# Find out next neighbour and handle routing
		self.createUdpSocket()
		self.handleUdpComms()

		# Handle rtsp packets
		self.handleRtspComms()

		# Handle rtp packets
		self.handleRtpComms()

		print("Starting HEARTBEAT...") # to discover nodes that have left/crashed
		# ping neighbours every 10 seconds
		threading.Thread(target=self.sendHearbeat).start()

	def sendHearbeat(self):
		sizeNeighs = len(self.neighboursAlive)
		neighbours = self.neighbours
		while True:
			sleep(10)
			# ver quais os vizinhos que sairam
			# e dizer q todos os vizinhos sairam
			for i in range(sizeNeighs):
				neighIsAlive = self.neighboursAlive[i]
				neigh = self.neighbours[i]
				if neighIsAlive == False:
					print("Neighbour",neigh,"is not alive!")
				self.aliveNeighsLock.acquire()
				self.neighboursAlive[i] = False
				self.aliveNeighsLock.release()
			
			# enviar mensagem para todos os vizinhos
			for neigh in neighbours:
				self.sendUdp(neigh, "HEARTBEAT")

	# =============== RTP ====================================================================
	def handleRtpComms(self):
		self.createRtpSocketForNextNode()
		threading.Thread(target=self.listenRtp).start()

	# Receive rtp packets from server side...
	def createRtpSocketForNextNode(self):
		"""Open RTP socket binded to a specified port."""
		
		# Create a new datagram socket to receive RTP packets from the server
		self.rtpSocket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
				
		try:
			# Bind the socket to the address using the RTP port given by the client user
			self.rtpSocket.bind(('', self.rtpPort))
			print('\nBinded RTP Port!\n')
		except socket.error as message:
			print('Unable to Bind', 'Unable to bind PORT=%d' %self.rtpPort + str(message[0]) + ' Message ' + message[1])

	def listenRtp(self):		
		"""Listen for RTP packets."""
		print("Listening for RTP Packets")
		while True:
			try:
				data = self.rtpSocket.recv(20480)

				if data:
					reachableClients = self.reachableClients
					nextNodeToReachClient = self.nextNodeToReachClient
					clientIsPlaying = self.clientIsPlaying
					rtspSockets = self.clientInfoArr
					size = len(clientIsPlaying)

					distinctNextNodeToReachClient = []
					for i in range(size):
						if clientIsPlaying[i]: # iterate clients that are playing
							if nextNodeToReachClient[i] not in distinctNextNodeToReachClient:
								print("Must send to IP",nextNodeToReachClient[i])
								distinctNextNodeToReachClient.append(nextNodeToReachClient[i])
								
					rtpConns = []
					size = len(distinctNextNodeToReachClient)
					for i in range(size):
						for clientinfo in rtspSockets:
							clientInfoIp = clientinfo['rtspSocket'][1][0]
							if clientInfoIp == distinctNextNodeToReachClient[i]:
								rtpConns.append(clientinfo)
					
					for rtpConn in rtpConns:
						try:
							address = rtpConn['rtspSocket'][1][0]
							port = int(rtpConn['rtpPort'])
							rtpConn['rtpSocket'].sendto(data,(address,port))
						except Exception as e:
							print("Error 1",e)
					
			except Exception as e:
				print("Error 2",e)

	# *************** END RTP ********************************************************************

	# =============== RTSP ====================================================================
	def handleRtspComms(self):
		self.createRtspSocketForNextNode()
		self.createRtspSocketForClient()
	
	def createRtspSocketForNextNode(self):
		while self.nextNeigh is None:
			sleep(0.2)

		"""Connect to the Server. Start a new RTSP/TCP session."""
		self.sendRtspSocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
		try:
			self.sendRtspSocket.connect((self.nextNeigh, self.rtspPort))
			threading.Thread(target=self.recvRtspRequestServer).start()
		except:
			print('Connection Failed', 'Connection to \'%s\' failed.' %self.nextNeigh)
	
	def createRtspSocketForClient(self):
		# Para receber pedidos rtsp
		rtspSocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
		rtspSocket.bind(('', self.rtspPort))
		rtspSocket.listen(5)

		threading.Thread(target=self.acceptRtspConn, args=(rtspSocket,)).start()

	def acceptRtspConn(self, rtspSocket):
		# Receive client info (address,port) through RTSP/TCP session
		self.clientInfoArr = []
		while True:
			clientInfo = {}
			clientInfo['rtspSocket'] = rtspSocket.accept()
			self.clientInfoArr.append(clientInfo)
			threading.Thread(target=self.recvRtspRequest).start()

	def recvRtspRequest(self): # FROM CLIENT
		"""Receive RTSP request from the client."""
		currClientInfo = self.clientInfoArr[-1]
		print("\t\tListening for client",currClientInfo['rtspSocket'][1][0])
		connSocket = currClientInfo['rtspSocket'][0]
		while True:            
			data = connSocket.recv(256)
			if data:
				print("Data received:\n\t" + data.decode("utf-8"))
				self.processRtspRequest(data.decode("utf-8"),currClientInfo)

	def processRtspRequest(self, data, clientinfo):
		"""Process RTSP request sent from the client."""
		# Get the request type

		request = data.split('\n')
		line1 = request[0].split(' ')
		requestType = line1[0]

		# Ver IP do cliente!
		# Nota: aparece sempre na mesma posição
		if len(request)<2:
			clientIp = clientinfo['rtspSocket'][1][0]
			print("\t1.Ip original é",clientIp)
			data+="\nIP %s" % (clientIp)
		else:
			line4 = request[1].split(' ')
			clientIp = line4[1]
			print("\t2.Ip original é",clientIp)

		# Process SETUP request
		if requestType == self.SETUP:
			print("processing SETUP\n")

			# Assign RTP/UDP port to a static port
			try:
				ind = self.clientInfoArr.index(clientinfo)
				self.clientInfoArr[ind]['rtpPort'] = self.rtpPort
			except ValueError as e:
				print("\t\t*********FATAL ERROR!!!!!**********")
				
		elif requestType == self.PLAY:
			print("processing PLAY\n")
			
			# Create a new socket for RTP/UDP
			try:
				ind = self.clientInfoArr.index(clientinfo)
				self.clientInfoArr[ind]['rtpSocket'] = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
			except ValueError as e:
				print("\t\t*********FATAL ERROR 2!!!!!**********")

			# dizer que client está playing
			clientInd = self.getIndexOfClient(clientIp)
			if clientInd < 0:
				print("\t\t*******FATAL ERROR 3!!!!******")
			print("Client",self.reachableClients[clientInd],"is now playing")
			self.clientIsPlaying[clientInd] = True

		elif requestType == self.PAUSE:
			print("processing PAUSE\n")

			# dizer que client fez pause
			clientInd = self.getIndexOfClient(clientIp)
			print("Client",self.reachableClients[clientInd],"is now paused")
			if clientInd < 0:
				print("\t\t*******FATAL ERROR 3!!!!******")
			self.clientIsPlaying[clientInd] = False

		elif requestType == self.TEARDOWN:
			print("processing TEARDOWN\n")

			# dizer que client fez pause
			clientInd = self.getIndexOfClient(clientIp)
			print("Client",self.reachableClients[clientInd],"is now paused")
			if clientInd < 0:
				print("\t\t*******FATAL ERROR 3!!!!******")
			self.clientIsPlaying[clientInd] = False

		print("Sent",data,"to",self.nextNeigh)
		self.sendRtspSocket.send(data.encode("utf-8"))

	def getIndexOfClient(self, clientIp):
		rc = self.reachableClients
		for i in range(len(rc)):
			ci = rc[i]
			if ci == clientIp:
				return i
		return -1

			# =========================== DEAL WITH SERVER SIDE RTSP =============================================
	def recvRtspRequestServer(self):
		"""Receive RTSP request from the client."""
		connSocket = self.sendRtspSocket
		while True:            
			data = connSocket.recv(256)
			if data:
				print("Data received from server:\n" + data.decode("utf-8"))
				self.processRtspRequestFromServer(data.decode("utf-8"))
	
	def processRtspRequestFromServer(self, data):
		"""Process RTSP request sent from the server."""
		
		request = data.split('\n')
		line4 = request[3].split(' ')
		clientIp = line4[1]
		print("Client ip is",clientIp)

		nodeToSend = None
		rcs = self.reachableClients
		for i in range(len(rcs)):
			rc = rcs[i]
			if rc == clientIp:
				nodeToSend = self.nextNodeToReachClient[i]
				break
		if nodeToSend is None:
			print("**** FATAL ERROR, cant find next node to send server RTSP Req ****")
			return

		rtspSock = None
		for cf in self.clientInfoArr:
			currIp = cf['rtspSocket'][1][0]
			print("Curr ip is",currIp)
			if currIp == nodeToSend:
				rtspSock = cf['rtspSocket'][0]
				break
		if rtspSock is None:
			print("**** FATAL ERROR, cant find client to send server RTSP Req ****")
			return
		
		# Privacy protection
		if nodeToSend in self.reachableClients:
			del request[3]
			data = "\n".join(request)

		print("Sending",data,"back to",nodeToSend,"!")
		connSocket = rtspSock
		connSocket.send(data.encode())
			# ***************************** DEAL WITH SERVER SIDE RTSP ******************************************

	# *************** RTSP ********************************************************************

	# =============== UDP =========================================================================

	def createUdpSocket(self):
		# UDP Socket
		self.udpSocket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
		# Bind the socket to the port
		server_address = ("", self.udpPort)
		self.udpSocket.bind(server_address)

	def handleUdpComms(self):
		print("Starting DISCOVER thread...") # to discover where to route rtsp packets
		# Create a new thread to listen for UDP packets
		threading.Thread(target=self.listenUdp).start()

		print("Saying hello to neighbours!")
		for neighb in self.neighbours:
			self.timestampDiscNeigh.append(datetime.datetime.now())
			self.sendUdp(neighb, "DISCOVER NOIP GO")
	
	def listenUdp(self):
		sock = self.udpSocket

		print("####### Server is listening #######")
		while True:
			data, address = sock.recvfrom(1024)
			msg = data.decode('utf-8')
			print("\n\n Received:", msg, "\n\n")

			threading.Thread(target=self.processUdpReq, args=(msg, address)).start()

	def processUdpReq(self, msg, address):
		msg_list = msg.split(" ")

		if msg_list[0] == "DISCOVER":
			
			if msg_list[2] == "GO":
			
				excl_neigh = [] # neighbours to not send message!
				
				if msg_list[1] == "NOIP":
					origin_ip = address[0]
				else:
					origin_ip = msg_list[1]
					excl_neigh.append(origin_ip)
					
					for i in range(3, len(msg_list)):
						print(msg_list[i])
						excl_neigh.append(msg_list[i])
				
				print(origin_ip," wants to DISCOVER")
				
				if self.nextNeigh is not None:
					neigh_list = [ self.nextNeigh ]
				else: # preparar lista de vizinhos ao ver a quais vizinhos
						# não vai enviar mensagem
					excl_neigh.append(address[0])

					print("Blacklisted neighbours are:")
					for neigh in excl_neigh:
						print("\t", neigh)
					print("")

					# prepare list of neighbours to send message
					neigh_list = self.neighbours
					for el in excl_neigh:
						if el in neigh_list: 
							neigh_list.remove(el)
				
				# prepare message
				if msg_list[1] == "NOIP":
					msg_list[1] = address[0]
				else:
					msg_list.append(address[0])

				# ver se IP's aparecem duplicados
				# porque se aparecerem, existe um ciclo e
				# a mensagem não é enviada
				msg_set = set(msg_list)
				contains_duplicates = len(msg_set) != len(msg_list)
				if contains_duplicates == True:
					print("msg"," ".join(msg_list),"has duplicates!")
				else:

					new_msg = " ".join(msg_list)

					for el in neigh_list:
						#print("Sending to", el, "msg", new_msg)
						self.sendUdp(el, new_msg)
			
			elif msg_list[2] == "RETURN":
				print("Returning message")
				# ou tem que dar forward para trás
				# ou é o próprio
				# de qualquer forma tem já que saber qual o vizinho usar para o destino

				self.prevTimeForDiscoveringLastNeigh = self.timeForDiscoveringLastNeigh
				ind = 0
				try:
					ind = self.neighbours.index(address[0])
				except ValueError as e:
					print("\t\t*********ERROR: Couldnt find neighbour",src,"!!!!!**********")
					return
				self.timeForDiscoveringLastNeigh = datetime.datetime.now() - self.timestampDiscNeigh[ind] 

				if len(msg_list) == 3: # é o próprio nó quem mandou o discover
					print("I sent the DISCOVER myself!")

					if self.nextNeigh is None:
						self.nextNeigh = address[0]
						print(self.nextNeigh,"is now my next neighbour")
						print("Discovered in",self.timeForDiscoveringLastNeigh,"ms")
					else:
						if self.timeForDiscoveringLastNeigh < self.prevTimeForDiscoveringLastNeigh:
							self.nextNeigh = address[0]
							print(self.nextNeigh,"is now my next neighbour")
							print("Discovered in",self.timeForDiscoveringLastNeigh,"ms")
						else:
							print("Neighbour not altered")
							#print("Assigned neighbour reponse time is",self.prevTimeForDiscoveringLastNeigh,"and now neighbour",address[0],"responded in",self.timeForDiscoveringLastNeigh)
				else:
					msg_list.pop()
					if len(msg_list)==3:
						nodeToSend = msg_list[1]
					else:
						nodeToSend = msg_list[len(msg_list)-1]
					new_msg = " ".join(msg_list)
					#print("Sending",new_msg,"to",nodeToSend)
					self.sendUdp(nodeToSend, new_msg)

		elif msg_list[0] == "ANNOUNCE":
			
			if msg_list[1] == "NOIP": # just received the announce
				msg_list[1] = address[0]
				new_msg = new_msg = " ".join(msg_list)
			else:
				new_msg = msg
			
			if msg_list[1] not in self.reachableClients:
				self.reachableClients.append(msg_list[1])
				self.nextNodeToReachClient.append(address[0])
				self.clientIsPlaying.append(False)
				print("To send packets to client",self.reachableClients[-1],"we must send packet to",address[0])

			self.sendUdp(self.nextNeigh, new_msg)
		
		elif msg_list[0] == "HEARTBEAT":
			self.sendUdp(address[0], "ACKED_HEARTBEAT")
		elif msg_list[0] == "ACKED_HEARTBEAT":
			src = address[0]
			#print("Heartbeat ack came from",src)
			try:
				ind = self.neighbours.index(src)
				self.aliveNeighsLock.acquire()
				self.neighboursAlive[ind] = True
				self.aliveNeighsLock.release()
			except ValueError as e:
				print("\t\t*********ERROR: Couldnt find neighbour",src,"!!!!!**********")

		else:
			print("Unrecognized message received:",msg)

	def sendUdp(self, neigh, msg):
		sock = self.udpSocket
		print("Sent", msg, "to", neigh)
		sock.sendto(msg.encode('utf-8'), (neigh, self.udpPort))

	# =============== UDP =========================================================================

	