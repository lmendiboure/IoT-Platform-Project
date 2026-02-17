import socket
import time

HOST = ''
PORT = 5000

s = socket.socket()
s.bind((HOST, PORT))
s.listen(1)

print("Waiting for connection...")
conn, addr = s.accept()
print("Connected:", addr)

while True:
    timestamp = time.time()
    conn.sendall(str(timestamp).encode())
    time.sleep(0.5)
