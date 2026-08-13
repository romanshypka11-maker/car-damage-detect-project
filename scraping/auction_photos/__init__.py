from .aggregator import PhotoAggregator

# Створюємо один екземпляр агрегатора на весь застосунок
_aggregator = PhotoAggregator()

# Функція-точка входу
async def get_auction_photos(vin: str) -> list[str]:
    return await _aggregator.get_photos(vin)

__all__ = ["get_auction_photos"]