import yaml
import time
from core import P2PNode
from tunnel import Tunnel
from signaling.baidupcs import BaiduPCSSignaling

def main():
    # 1️⃣ 读取配置文件
    with open("config.yaml", "r") as f:
        config = yaml.safe_load(f)

    mode = config["mode"]
    node_id = config["id"]
    peer_id = config["peer"]
    port = config["port"]

    # 2️⃣ 创建信令客户端
    signaling = BaiduPCSSignaling()

    # 3️⃣ 创建节点
    node = P2PNode(node_id=node_id, peer_id=peer_id)

    # 4️⃣ 上传公网地址到信令服务器
    signaling.upload(node_id,  f"{node.public_ip}:{node.public_port}:{int(time.time())}")
    print(f"[CLI] 上传公网ip、nat映射端口到信令服务器: {node_id}: {node.public_ip}:{node.public_port}:{int(time.time())}")

    peer_info = None
    peer_ip = None
    peer_port = None
    got_peer_status = False

    i = 0
    print("[CLI] 正在获取对端地址", end="", flush=True)
    # 5️⃣ 获取对端地址
    while i < 20:
        try:
            if got_peer_status:
                break

            i = i + 1
            peer_info = signaling.download(peer_id)
            peer_ip, peer_port, ts_str = peer_info.split(":")
            peer_ts = int(ts_str)
            if time.time() - peer_ts > 20:
                print(".", end="", flush=True)
                time.sleep(5)
                continue

            got_peer_status = True
        except Exception as e:
            print(".", end="", flush=True)
        time.sleep(5)

    print()
    if not got_peer_status:
        print(f"[CLI] 获取对端地址失败")
        return

    print(f"[CLI] 本地 UDP: {node_id} {node.local_ip}:{node.local_port}, 公网: {node.public_ip}:{node.public_port}, (NAT 类型: {node.nat_type})")
    print(f"[CLI] 对端 UDP: {peer_id} {peer_ip}:{peer_port}")

    node.peer = (peer_ip, int(peer_port))

    punched = node.punch()
    if not punched :
        return

    # 6️⃣ 启动隧道
    tunnel = Tunnel(
        mode=mode,
        endpoint=node,
        port=port
    )

    tunnel.start()

    if mode == "client":
        print(f"[CLI] 客户端模式启动: 代理端口 {port} <-> 隧道 <-> {peer_ip}:{peer_port}")
    else:
        print(f"[CLI] 服务端模式启动: {peer_ip}:{peer_port} <-> 隧道 <-> 转发端口 {port} ")

    # 7️⃣ 阻塞主线程
    try:
        while True:
            time.sleep(5)
    except KeyboardInterrupt:
        print("[CLI] 退出")


if __name__ == "__main__":
    main()
