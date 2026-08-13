import logging
from typing import Any

from core.db import fetch_all
from damage_detection.analyzer import analyze_damage
from pricing.model import predict_price
from scraping import get_auction_photos,AutoRiaParser

logger = logging.getLogger(__name__)


def tool_predict_price(features: dict[str, Any]) -> float:
    return predict_price(features)


def tool_analyze_damage(urls: list[str]) -> dict[str, Any]:
    return analyze_damage(urls)


async def tool_scrape_autoria(url: str) -> dict[str, Any]:
    parser = AutoRiaParser()
    return await parser.get_data(url)


async def tool_get_auction_photos(vin: str) -> list[str]:
    return await get_auction_photos(vin)


async def tool_query_database(sql: str) -> list[dict]:
    return await fetch_all(sql)
