import os
import subprocess
from signaling import Signaling  # 绝对导入


class BaiduPCSSignaling(Signaling):
    def __init__(self):
        self.BAIDU_PCS_BIN = os.path.join(os.getcwd(), "BaiduPCS-Go")
        if not self._check_login():
            print("[Signaling] 尚未登录百度网盘，请输入 cookies: ")
            self._login_interactive()

        cmd = [self.BAIDU_PCS_BIN, "mkdir", "/apps/mousebaby"]
        subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="ignore"
        )

    def _check_login(self) -> bool:
        """检查是否已登录过"""
        cmd = [self.BAIDU_PCS_BIN, "quota"]
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="ignore"
        )
        # BaiduPCS-Go 未登录时通常会输出 "未登录" 或 "请先登录"
        output = result.stdout + result.stderr
        if "未登录" in output or "重新登录" in output:
            return False
        return True


    def _login_interactive(self):
        """循环要求用户输入 BDUSS 直到成功"""
        while True:
            cookies = input("请输入 cookies: ").strip()
            cookies = cookies.replace('"', '')
            cmd = [self.BAIDU_PCS_BIN, "login", "-cookies", cookies]
            result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="ignore")
            output = result.stdout + result.stderr
            if "登录成功" in output:
                print("[Signaling] 登录成功 ✅")
                break
            else:
                print("[Signaling] 登录失败，请确认 BDUSS 是否正确或未过期。")
                print("错误信息：", result.stderr.strip())

    def upload(self, peer_id: str, data: str):
        remote_dir = "/apps/mousebaby"

        remote_path = f"/apps/mousebaby/{peer_id}.txt"

        cmd = [self.BAIDU_PCS_BIN, "rm", remote_path]
        subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="ignore")

        local_tmp = os.path.join(os.getcwd(), "tmp", f"{peer_id}.txt")
        os.makedirs(os.path.dirname(local_tmp), exist_ok=True)

        with open(local_tmp, "w", encoding="utf-8") as f:
            f.write(data)

        cmd = [self.BAIDU_PCS_BIN, "upload", local_tmp, remote_dir]
        result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="ignore")
        output = result.stdout + result.stderr
        if "上传文件成功" in output:
            #print(f"[Signaling] Uploaded {peer_id}.txt")
            pass
        else:
            raise RuntimeError(f"[Signaling] 上传失败, code={result.returncode}")

    def download(self, peer_id: str) -> str:
        remote_path = f"/apps/mousebaby/{peer_id}.txt"
        local_tmp = os.path.join(os.getcwd(), "tmp", f"{peer_id}.txt")
        local_dir = os.path.dirname(local_tmp)
        os.makedirs(os.path.dirname(local_dir), exist_ok=True)

        if os.path.exists(local_tmp):
            os.remove(local_tmp)

        cmd = [self.BAIDU_PCS_BIN, "download", remote_path, "--saveto", local_dir]
        result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="ignore")
        output = result.stdout + result.stderr

        if "下载完成" in output:
            with open(local_tmp, "r", encoding="utf-8") as f:
                return f.read()

        raise RuntimeError(f"[Signaling] 下载失败, code={result.returncode}")

