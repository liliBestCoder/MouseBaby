import time
from datetime import datetime, timezone, timedelta

import yaml

from core import P2PNode
from signaling.baidupcs import BaiduPCSSignaling
from tunnel import Tunnel


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

    start_time = input("请输入开始时间(格式: 2021-01-01 00:00:00)：")
    # 北京时间，UTC+8
    tz = timezone(timedelta(hours=8))
    target = datetime.strptime(start_time, "%Y-%m-%d %H:%M:%S").replace(tzinfo=tz).timestamp()

    while True:
        now = time.time()
        if now >= target:
            break
        remaining = target - now
        print(f"还需要等待 {remaining} 秒...", end="\r")
        time.sleep(0.001)

    start = time.time()

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
                time.sleep(1)
                continue

            got_peer_status = True
        except Exception as e:
            print(".", end="", flush=True)
        time.sleep(1)

    print()
    if not got_peer_status:
        print(f"[CLI] 获取对端地址失败")
        return

    print(f"[CLI] 本地 UDP: {node_id} {node.local_ip}:{node.local_port}, 公网: {node.public_ip}:{node.public_port}, (NAT 类型: {node.nat_type})")
    print(f"[CLI] 对端 UDP: {peer_id} {peer_ip}:{peer_port}")

    node.peer = (peer_ip, int(peer_port))

    #同步时钟
    while time.time() - start < 10:
        time.sleep(0.001)

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
