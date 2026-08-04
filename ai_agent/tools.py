import logging
from typing import Any

from core.db import fetch_all
from damage_detection.analyzer import analyze_damage
from pricing.model import predict_price
from scraping.autoria.parser import AutoRiaParser
from scraping.plc_ua.parser import get_photos_by_vin

logger = logging.getLogger(__name__)


def tool_predict_price(features: dict[str, Any]) -> float:
    return predict_price(features)


def tool_analyze_damage(urls: list[str]) -> dict[str, Any]:
    return analyze_damage(urls)


async def tool_scrape_autoria(url: str) -> dict[str, Any]:
    parser = AutoRiaParser()
    return await parser.get_data(url)


def tool_get_auction_photos(vin: str) -> list[str]:
    return get_photos_by_vin(vin)


async def tool_query_database(sql: str) -> list[dict]:
    return await fetch_all(sql)
