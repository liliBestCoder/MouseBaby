import socket
import stun
import time
import threading
import binascii


class P2PNode:
    def __init__(self, node_id, peer_id, stun_host="stun.ringostat.com", stun_port=3478):
        # 随机本地 UDP 端口
        self.node_id = node_id
        self.peer_id = peer_id
        self.peer = None
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(("", 0))
        self.sock.settimeout(0.3)
        self.stun_host = stun_host
        self.stun_port = stun_port
        self.local_ip, self.local_port = self.sock.getsockname()

        nat_type, nat = stun.get_nat_type(self.sock,  self.local_ip, self.local_port,
                                          stun_host=stun_host, stun_port=stun_port)
        external_ip = nat['ExternalIP']
        external_port = nat['ExternalPort']

        self.public_ip = external_ip
        self.public_port = external_port
        self.nat_type = nat_type

        self.keepalive_running = True
        threading.Thread(target=self._send_keepalive_packet, daemon=True).start()
        self.got_peer = threading.Event()

        self.recv_thread = threading.Thread(target=self._recv_punch, daemon=True)
        self.recv_thread.start()


    def send_to_peer(self, data: bytes):
        self.sock.sendto(data, self.peer)

    def recv(self, handler, timeout=0.3):
        try:
            self.sock.settimeout(timeout)
            data, addr = self.sock.recvfrom(4096)
        except socket.timeout:
            return

        handler(data, addr)

    def _send_keepalive_packet(self):
        while self.keepalive_running:  # 只要 keepalive_running 为 True，就保持发送包
            try:
                # 向 STUN 服务器发送一个保持活跃的包
                str_len = "%#04d" % (len('') / 2)
                tran_id = stun.gen_tran_id()
                str_data = ''.join(['0001', str_len, tran_id, ''])
                data = binascii.a2b_hex(str_data)
                self.sock.sendto(data, (self.stun_host, self.stun_port))
                #print(f"[Core] send heartbeat to stun")
            except Exception as e:
                print(f"Error sending keepalive: {e}")
            time.sleep(1)  # 每3秒发送一次

    def _stop_keepalive(self):
        # 停止周期性发送包
        self.keepalive_running = False
        #print("[Core] Stopped sending keepalive packets.")

    def _recv_punch(self):
        def handle_punch(data, addr):
            text = data.decode(errors='ignore').strip()
            # 检查是否来自目标对端
            if addr == self.peer:
                #print(f"[recv] [{time.time():.3f}] {addr}: {text}")
                if "PUNCH" in text:
                    print(f"[punch] [{time.time():.3f}] received punch from target peer {addr}")
                    ack_payload = f"ACK from {self.node_id}".encode()
                    print(f"[punch] [{time.time():.3f}] sending ACK to {addr}")
                    self.sock.sendto(ack_payload, addr)
                    self.got_peer.set()
                    return

                elif "ACK" in text:
                    print(f"[punch] [{time.time():.3f}] received ack from target peer {addr}")
                    self.got_peer.set()
                    return
            else:
                pass
        def do_recv_punch_loop(timeout=30):
            deadline = time.time() + timeout
            print(f"[punch] start punch receiving, deadline: {deadline:.3f}")

            while time.time() < deadline and not self.got_peer.is_set():
                try:
                    self.recv(handle_punch, timeout=0.3)
                except ConnectionResetError:
                    print(f"[punch] [{time.time():.3f}] recv punch ConnectionResetError: 远程主机强迫关闭了一个现有的连接")
                    continue
                except Exception as e:
                    print(f"[punch] [{time.time():.3f}] recv punch err {self.peer}: {e}")
                    continue

            self.sock.settimeout(0.3)

        do_recv_punch_loop()

    def punch(self):
        def do_punch():
            print(f"[punch] start punching to {self.peer} from local {self.local_port}")
            payload = f"PUNCH from {self.node_id}".encode()

            # 等待下一个10秒的整数倍时间点
            current_time = time.time()
            next_sync_point = (int(current_time) // 10 + 1) * 10
            wait_time = next_sync_point - current_time
            print(f"[punch] waiting {wait_time:.2f} seconds for time synchronization...")
            time.sleep(wait_time)

            # 增加更多的调试信息
            for i in range(180):
                try:
                    print(f"[punch] [{time.time():.3f}] send punching payload {i+1}/180 to {self.peer}")
                    self.send_to_peer(payload)
                    time.sleep(0.2)
                except Exception as e:
                    print("send err", e)
            print(f"[punch] [{time.time():.3f}] finished to send punch packets")

            if self.got_peer.is_set():
                return

        send_thread = threading.Thread(target=do_punch, daemon=True)
        send_thread.start()

        success = self.got_peer.wait(timeout=30)

        send_thread.join()
        self.recv_thread.join()

        if not success:
            print(f"[punch] [{time.time():.3f}] punched to {self.peer} failed")
            return False

        self._stop_keepalive()
        print(f"[punch] [{time.time():.3f}] punched to {self.peer} success")
        return True
