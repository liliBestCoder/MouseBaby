from abc import ABC, abstractmethod

class Proxy(ABC):
    @abstractmethod
    def forward_to_tunnel(self):
        pass

    @abstractmethod
    def forward_to_client(self):
        pass
