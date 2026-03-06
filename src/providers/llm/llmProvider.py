from abc import ABC, abstractmethod

class llmProvider(ABC):
    @abstractmethod
    def getLLM(self):
        pass
