import socket
import threading
import time
import selectors

from core import P2PNode
from proxy import Proxy

from concurrent.futures import ThreadPoolExecutor


class UDPProxy(Proxy):

    def __init__(self, mode: str, tunnel_endpoint: P2PNode, port: int = None):
        """
        mode: "client" or "server"
        client 模式需要 bind local_port
        server 模式不 bind
        """
        self.mode = mode
        self.tunnel_endpoint = tunnel_endpoint
        self.port = port
        self.client_socket_map = {}
        self.lock_socket = threading.Lock()
        self.addr_map = {}
        self.lock_addr = threading.Lock()
        self.pending_client_id_map = {}
        self.lock_pending = threading.Lock()
        self.client_id_map = {}
        self.lock_client = threading.Lock()
        self.client_id_seed = 1
        self.selector = selectors.DefaultSelector()
        self.executor = ThreadPoolExecutor(max_workers=10)

        if self.mode == "client":
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.sock.bind(("0.0.0.0", port))

        threading.Thread(target=self._clean, daemon=True).start()

    def server_forward_to_tunnel(self):
        # 创建固定大小的线程池
        while True:
            if not self.selector.get_map():
                time.sleep(0.01)  # 等待 socket 注册
                continue

            events = self.selector.select(timeout=0.05)
            for key, _ in events:
                client_id, sock = key.data
                try:
                    data = sock.recv(4096)
                    with self.lock_socket:
                        self.client_socket_map[client_id] = (sock, time.time())
                except Exception:
                    continue
                self.executor.submit(self._server_forward_socket_to_tunnel, client_id, data)

    def _server_forward_socket_to_tunnel(self, client_id, data):
        # 前面加上 client_id
        client_id_byte = client_id.to_bytes(1, byteorder='big')
        self.tunnel_endpoint.send_to_peer(client_id_byte + data)

    def client_forward_to_tunnel(self,timeout=0.05):
        try:
            self.sock.settimeout(timeout)
            data, addr = self.sock.recvfrom(4096)
        except Exception:
            return

        exists, client_id = self._map_addr_from_packet(addr)
        if not exists:
             payload = f"CONNECT {client_id}".encode()
             self.tunnel_endpoint.send_to_peer(payload)

        client_id_byte = client_id.to_bytes(1, byteorder='big')
        data = client_id_byte + data
        self.tunnel_endpoint.send_to_peer(data)

    def _client_tunnel_endpoint_recv_handler(self, data, addr):
        if data.startswith(b'CONNECT_ACK'):
            text = data.decode(errors='ignore').strip()
            client_id = int(text.split()[1])
            client_addr_time = self.pending_client_id_map.pop(client_id)
            if client_addr_time is not None:
                with self.lock_client:
                    self.client_id_map[client_id] = (client_addr_time[0], time.time())
        elif data.startswith(b'HEARTBEAT'):
            pass
        else:
            client_id = data[0]
            client_addr_time = self.client_id_map.get(client_id)
            if client_addr_time is not None :
                client_addr = client_addr_time[0]
                self.sock.sendto(data[1:], client_addr)
                with self.lock_client:
                    self.client_id_map[client_id] = (client_addr, time.time())
    def tunnel_forward_to_client(self):
        try:
             self.tunnel_endpoint.recv(self._client_tunnel_endpoint_recv_handler, 0.3)
        except Exception:
            return

    def _server_tunnel_endpoint_recv_handler(self, data, addr):
        if data.startswith(b'CONNECT'):
            text = data.decode(errors='ignore').strip()
            client_id = int(text.split()[1])
            with self.lock_socket:
                if client_id not in self.client_socket_map:
                    # 新建 socket 用于和本地服务通信
                    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                    sock.bind(("", 0))
                    self.client_socket_map[client_id] = (sock,time.time())
                    self.selector.register(sock, selectors.EVENT_READ, data=(client_id, sock))
                # 回复客户端 ACK
                self.tunnel_endpoint.send_to_peer(f"CONNECT_ACK {client_id}".encode())

        elif data.startswith(b'DISCONNECT'):
            text = data.decode(errors='ignore').strip()
            client_id = int(text.split()[1])
            with self.lock_socket:
                if client_id in self.client_socket_map:
                    del self.client_socket_map[client_id]

        elif data.startswith(b'HEARTBEAT'):
           pass
        else:
            # 假设 client_id 在 data 的前 1 个字节
            client_id = data[0]
            payload = data[1:]  # 去掉 client_id
            sock_time = self.client_socket_map.get(client_id)
            if sock_time:
                sock = sock_time[0]
                sock.sendto(payload, ("127.0.0.1", self.port))
            else:
                print(f"No socket for client_id={client_id}, drop packet")

    def tunnel_forward_to_server(self):
        try:
            self.tunnel_endpoint.recv(self._server_tunnel_endpoint_recv_handler, timeout=0.3)
        except Exception:
            return

    def _map_addr_from_packet(self, client_addr: tuple) -> (bool, int):
        key = f"{client_addr[0]}:{client_addr[1]}"
        if key in self.addr_map :
            client_id = self.addr_map[key]
            return True, client_id
        else:
            with self.lock_addr:
                self.client_id_seed += 1
                client_id = self.client_id_seed
                self.addr_map[key] = client_id
                with self.lock_pending:
                    self.pending_client_id_map[client_id] = (client_addr, time.time())
                return False, client_id

    def _clean(self):
        def clean_pending_map():
            now = time.time()
            with self.lock_pending:
                to_remove = [cid for cid, (_, ts) in self.pending_client_id_map.items() if now - ts > 30]
                for cid in to_remove:
                    del self.pending_client_id_map[cid]
                    #通知对端把socket关掉
                    for i in range(5):
                        self.tunnel_endpoint.send_to_peer(f"DISCONNECT {cid}".encode())
                    # 遍历 addr_map 找到对应的 key 并删除
                    with self.lock_addr:
                        for addr_key, stored_cid in list(self.addr_map.items()):
                            if stored_cid == cid:
                                del self.addr_map[addr_key]
                                break  # 找到就可以退出循环
        def clean_client_id_map():
            now = time.time()
            with self.lock_client:
                to_remove = [cid for cid, (addr, ts) in self.client_id_map.items() if now - ts > 30]
                for cid in to_remove:
                    del self.client_id_map[cid]
                    #通知对端把socket关掉
                    for i in range(5):
                        self.tunnel_endpoint.send_to_peer(f"DISCONNECT {cid}".encode())
                    # 遍历 addr_map 找到对应的 key 并删除
                    with self.lock_addr:
                        for addr_key, stored_cid in list(self.addr_map.items()):
                            if stored_cid == cid:
                                del self.addr_map[addr_key]
                                break
        def clean_client_socket_map():
            now = time.time()
            with self.lock_socket:
                to_remove = [cid for cid, (sock, ts) in self.client_socket_map.items() if now - ts > 30]
                for cid in to_remove:
                    sock = self.client_socket_map[cid][0]
                    del self.client_socket_map[cid]
                    try:
                        self.selector.unregister(sock)
                        sock.close()
                    except Exception as e:
                        print("unregister error:", e)
        while True:
            clean_pending_map()
            clean_client_id_map()
            clean_client_socket_map()
            time.sleep(5)


