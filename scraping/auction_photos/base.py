from abc import ABC, abstractmethod

class AuctionPhotoSource(ABC):
    name: str

    @abstractmethod
    async def search_by_vin(self, vin: str) -> list[str]:
        """Повертає список URL фото або порожній список."""