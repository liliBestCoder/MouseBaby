import threading
import time

from core import P2PNode
from proxy.udp_proxy import UDPProxy

class Tunnel:
    def __init__(self, mode: str, endpoint: P2PNode, port: int):
        self.mode = mode
        self.endpoint = endpoint
        self.proxy = UDPProxy(mode=mode, tunnel_endpoint=endpoint, port=port)
    def start(self):
        if self.mode == "client":
            self._client_loop()
        else:
            self._server_loop()

        self._send_keepalive_packet()

    def _client_loop(self):
        # client: proxy_port -> peer -> local proxy 回流
        def client_to_peer():
            while True:
                self.proxy.forward_to_tunnel()
        def peer_to_client():
            while True:
                self.proxy.forward_to_client()

        threading.Thread(target=client_to_peer, daemon=True).start()
        threading.Thread(target=peer_to_client, daemon=True).start()

    def _server_loop(self):
        # server: forward_port -> peer -> local forward 回流
        def server_to_peer():
            self.proxy.start_forwarding_socket_to_tunnel()

        def peer_to_server():
            while True:
                self.proxy.forward_to_server()

        threading.Thread(target=server_to_peer, daemon=True).start()
        threading.Thread(target=peer_to_server, daemon=True).start()

    def _send_keepalive_packet(self):
        """
        发送一个空包，用于保持连接
        """
        def keepalive():
            while True:
                payload = f"HEARTBEAT ".encode()
                self.endpoint.send_to_peer(payload)
                time.sleep(1)

        threading.Thread(target=keepalive, daemon=True).start()