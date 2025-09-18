# signaling 插件接口
class Signaling:
    def upload(self, peer_id: str, data: str):
        raise NotImplementedError

    def download(self, peer_id: str) -> str:
        raise NotImplementedError
