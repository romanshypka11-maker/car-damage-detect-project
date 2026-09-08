from .aggregator import PhotoAggregator

_aggregator = PhotoAggregator()

async def get_auction_photos(vin: str) -> list[str]:
    return await _aggregator.get_photos(vin)

__all__ = ["get_auction_photos","_aggregator"]