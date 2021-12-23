import sys, traceback, threading, socket

from ServerWorker import ServerWorker

class Server:	
	
	def main(self):
		try:
			SERVER_PORT = int(sys.argv[1])
		except:
			print("[Usage: Server.py Server_port]\n")
		rtspSocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
		rtspSocket.bind(('', SERVER_PORT))
		rtspSocket.listen(5)

		self.udpPort = 2021
		# start discover response thread
		self.udpSock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
		# Bind the socket to the port
		server_address = ("", self.udpPort)
		self.udpSock.bind(server_address)
		threading.Thread(target=self.listenUdp).start()

		# Receive client info (address,port) through RTSP/TCP session
		clientInfo = {}
		clientInfo['rtspSocket'] = rtspSocket.accept()
		ServerWorker(clientInfo).run()		

	def listenUdp(self):
		sock = self.udpSock

		print("####### Server is listening #######")
		while True:
			data, address = sock.recvfrom(1024)
			msg = data.decode('utf-8')
			print("\n\n Received:", msg,"from",address[0], "\n\n")
			
			msg_list = msg.split(" ")

			if msg_list[0] == "DISCOVER":
				
				if msg_list[2] == "GO":
					msg_list[2] = "RETURN"
					sender_ip = address[0]

					# must add new source
					if msg_list[1] == "NOIP": # one node away from server
						msg_list[1] = sender_ip
					else: # can be DISCOVER <ip> OR DISCOVER <ip> GO ip2 ip3 ...
						msg_list.append(sender_ip)
					
					new_msg = " ".join(msg_list)

					print("Message from", sender_ip)
					print("Sending",new_msg,"to",sender_ip)
					self.sendUdp(sender_ip, new_msg)

	def sendUdp(self, neigh, msg):
		sock = self.udpSock
		sock.sendto(msg.encode('utf-8'), (neigh, self.udpPort))
		print("Sent", msg, "to", neigh)

if __name__ == "__main__":
	(Server()).main()