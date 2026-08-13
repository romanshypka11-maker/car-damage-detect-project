import logging
import urllib.parse
import httpx
from bs4 import BeautifulSoup

from core.config import get_settings
from ..base import AuctionPhotoSource

logger = logging.getLogger(__name__)


class PlcUaSource(AuctionPhotoSource):
    name = "PLC.ua"

    def __init__(self):
        settings = get_settings()
        self.flaresolverr_url = f"{settings.flaresolverr_url.rstrip('/')}/v1"

    async def search_by_vin(self, vin: str) -> list[str]:
        logger.info(f"[{self.name}] Шукаю VIN {vin} через Google...")
        google_search_url = f"https://www.google.com/search?q={vin}"

        # 1. Шукаємо лінк на PLC через Google (Асинхронно!)
        plc_url = await self._get_link_from_google(google_search_url)
        if not plc_url:
            return []

        # 2. Отримуємо HTML сторінки авто
        html = await self._fetch_page_html(plc_url)
        if not html:
            return []

        # 3. Дістаємо фото
        return self._extract_photos(html)

    async def _get_link_from_google(self, url: str) -> str | None:
        payload = {"cmd": "request.get", "url": url, "maxTimeout": 40000}
        try:
            async with httpx.AsyncClient(timeout=45.0) as client:
                response = await client.post(self.flaresolverr_url, json=payload)
                if response.status_code != 200:
                    return None

                html = response.json().get("solution", {}).get("response", "")
                soup = BeautifulSoup(html, "lxml")

                for a_tag in soup.find_all("a", href=True):
                    href = a_tag["href"]
                    if "/url?q=" in href:
                        href = urllib.parse.unquote(href.split("/url?q=")[1].split("&")[0])
                    if "plc.ua" in href.lower() and "/auctions/lot/" in href.lower():
                        return href
        except Exception as e:
            logger.error(f"[{self.name}] Помилка пошуку в Google: {e}")
        return None

    async def _fetch_page_html(self, url: str) -> str | None:
        payload = {"cmd": "request.get", "url": url, "maxTimeout": 60000}
        try:
            async with httpx.AsyncClient(timeout=65.0) as client:
                response = await client.post(self.flaresolverr_url, json=payload)
                if response.status_code == 200 and response.json().get("status") == "ok":
                    return response.json().get("solution", {}).get("response", "")
        except Exception:
            pass
        return None

    def _extract_photos(self, html: str) -> list[str]:
        soup = BeautifulSoup(html, "lxml")
        links = []

        # Твоя логіка парсингу PLC
        for tag in soup.select("link[itemprop='image']"):
            if href := tag.get("href"):
                links.append(href)

        if not links:
            for tag in soup.find_all(["link", "img", "a"]):
                for attr in ["href", "src", "data-src"]:
                    val = tag.get(attr)
                    if val and "img.plc.ua/full" in val:
                        links.append(val)

        clean_links = []
        for link in links:
            if link.startswith("//"):
                link = "https:" + link
            if any(ext in link.lower() for ext in [".jpg", ".jpeg", ".png", ".webp"]):
                clean_links.append(link)

        return list(set(clean_links))