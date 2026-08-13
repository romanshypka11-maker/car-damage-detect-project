import logging
import httpx
from bs4 import BeautifulSoup

from core.config import get_settings
from ..base import AuctionPhotoSource

logger = logging.getLogger(__name__)


class BidfaxSource(AuctionPhotoSource):
    name = "Bidfax"

    def __init__(self):
        settings = get_settings()
        # FlareSolverr потрібен для обходу захисту Bidfax
        self.flaresolverr_url = f"{settings.flaresolverr_url.rstrip('/')}/v1"

    async def search_by_vin(self, vin: str) -> list[str]:
        logger.info(f"[{self.name}] Пошук VIN {vin}...")

        # 1. Етап: Пошук за VIN
        search_url = f"https://bidfax.info/?do=search&subaction=search&story={vin}"
        search_html = await self._fetch_via_flaresolverr(search_url)

        if not search_html:
            return []

        # 2. Етап: Отримання лінку на авто
        car_url = self._find_car_link(search_html)
        if not car_url:
            logger.info(f"[{self.name}] Авто за VIN {vin} не знайдено.")
            return []

        logger.info(f"[{self.name}] Знайдено лот: {car_url}")

        # 3. Етап: Отримання сторінки авто
        car_html = await self._fetch_via_flaresolverr(car_url)
        if not car_html:
            return []

        # 4. Етап: Витягнення фото
        photos = self._extract_photos(car_html)
        logger.info(f"[{self.name}] Успішно знайдено {len(photos)} фото.")
        return photos

    async def _fetch_via_flaresolverr(self, url: str) -> str | None:
        payload = {"cmd": "request.get", "url": url, "maxTimeout": 60000}
        try:
            async with httpx.AsyncClient(timeout=65.0) as client:
                response = await client.post(self.flaresolverr_url, json=payload)
                if response.status_code == 200:
                    data = response.json()
                    if data.get("status") == "ok":
                        return data.get("solution", {}).get("response", "")
        except Exception as e:
            logger.error(f"[{self.name}] Помилка FlareSolverr для {url}: {e}")
        return None

    def _find_car_link(self, html: str) -> str | None:
        soup = BeautifulSoup(html, "lxml")
        # Точний селектор: блок результату -> посилання
        link_tag = soup.select_one("div.caption a")

        if link_tag and link_tag.has_attr("href"):
            href = link_tag["href"]
            if href.startswith("https://bidfax.info/"):
                return href
        return None

    def _extract_photos(self, html: str) -> list[str]:
        soup = BeautifulSoup(html, "lxml")
        links = []

        # Точний селектор на основі твого скріншоту:
        # ul.xfieldimagegallery всередині блоку з фото
        for img in soup.select("ul.xfieldimagegallery img"):
            src = img.get("src")
            if src:
                # Перетворюємо відносні шляхи на абсолютні
                if src.startswith("/"):
                    src = f"https://bidfax.info{src}"
                links.append(src)

        return list(set(links))