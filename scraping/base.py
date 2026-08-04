from abc import ABC, abstractmethod


class BaseParser(ABC):
    @abstractmethod
    async def get_data(self, url: str) -> dict:
        pass
