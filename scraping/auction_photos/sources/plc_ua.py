import logging
import os
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
        session_id = f"plc_{vin}"
        logger.info(f"[{self.name}] Шукаю VIN {vin} через Google...")
        google_search_url = f"https://html.duckduckgo.com/html/?q={vin}"

        await self._create_session(session_id)
        try:
            # 1. Шукаємо лінк на PLC через DuckDuckGo (з тою ж сесією/cookies)
            plc_url = await self._get_link_from_google(google_search_url, session_id)
            if not plc_url:
                return []

            # 2. Отримуємо HTML сторінки авто (та сама сесія — cookies переносяться)
            html = await self._fetch_page_html(plc_url, session_id)
            if not html:
                return []

            # Діагностика: зберігаємо сирий HTML для ручного огляду при потребі
            debug_path = "/app/logs/plc_debug.html"
            os.makedirs(os.path.dirname(debug_path), exist_ok=True)
            with open(debug_path, "w", encoding="utf-8") as f:
                f.write(html)
            logger.info(f"[{self.name}] HTML збережено для дебагу: {debug_path}, довжина={len(html)} символів")

            # 3. Дістаємо фото
            photos = self._extract_photos(html)
            logger.info(f"[{self.name}] Витягнуто {len(photos)} фото-URL із HTML")
            return photos
        finally:
            await self._destroy_session(session_id)

    async def _create_session(self, session_id: str) -> None:
        payload = {"cmd": "sessions.create", "session": session_id}
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                await client.post(self.flaresolverr_url, json=payload)
        except Exception:
            logger.exception(f"[{self.name}] Не вдалося створити FlareSolverr-сесію {session_id}")

    async def _destroy_session(self, session_id: str) -> None:
        payload = {"cmd": "sessions.destroy", "session": session_id}
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                await client.post(self.flaresolverr_url, json=payload)
        except Exception:
            logger.exception(f"[{self.name}] Не вдалося видалити FlareSolverr-сесію {session_id}")

    async def _get_link_from_google(self, url: str, session_id: str) -> str | None:
        payload = {"cmd": "request.get", "url": url, "session": session_id, "maxTimeout": 40000}
        try:
            async with httpx.AsyncClient(timeout=45.0) as client:
                response = await client.post(self.flaresolverr_url, json=payload)
                if response.status_code != 200:
                    return None

                html = response.json().get("solution", {}).get("response", "")
                soup = BeautifulSoup(html, "lxml")

                for a_tag in soup.find_all("a", href=True):
                    href = a_tag["href"]

                    if "uddg=" in href:
                        try:
                            href = urllib.parse.unquote(href.split("uddg=")[1].split("&")[0])
                        except Exception:
                            continue
                    elif "/url?q=" in href:
                        try:
                            href = urllib.parse.unquote(href.split("/url?q=")[1].split("&")[0])
                        except Exception:
                            continue

                    if "plc.ua" in href.lower() and "/auctions/lot/" in href.lower():
                        logger.info(f"[{self.name}] Знайдено лінк: {href}")
                        return href

        except Exception:
            logger.exception(f"[{self.name}] Помилка пошуку в Google/DuckDuckGo")

        return None

    async def _fetch_page_html(self, url: str, session_id: str) -> str | None:
        payload = {"cmd": "request.get", "url": url, "session": session_id, "maxTimeout": 60000}
        try:
            async with httpx.AsyncClient(timeout=65.0) as client:
                response = await client.post(self.flaresolverr_url, json=payload)
                if response.status_code == 200 and response.json().get("status") == "ok":
                    html = response.json().get("solution", {}).get("response", "")

                    if "Just a moment" in html or "cf-chl-widget" in html:
                        logger.warning(f"[{self.name}] Отримали Cloudflare challenge замість контенту")
                        return None

                    return html
        except Exception:
            logger.exception(f"[{self.name}] Помилка отримання сторінки {url}")
        return None

    def _extract_photos(self, html: str) -> list[str]:
        soup = BeautifulSoup(html, "lxml")
        links = []

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