from abc import ABC, abstractmethod

class Proxy(ABC):
    @abstractmethod
    def client_forward_to_tunnel(self):
        pass

    @abstractmethod
    def tunnel_forward_to_client(self):
        pass

    @abstractmethod
    def server_forward_to_tunnel(self):
        pass

    @abstractmethod
    def tunnel_forward_to_server(self):
        pass
