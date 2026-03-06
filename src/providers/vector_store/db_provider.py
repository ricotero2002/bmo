from abc import ABC, abstractmethod

class DbProvider(ABC):
    @abstractmethod
    def getVectorStore(self):
        pass
