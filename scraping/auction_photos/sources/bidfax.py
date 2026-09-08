import logging
import urllib.parse
import httpx
from bs4 import BeautifulSoup

from core.config import get_settings
from ..base import AuctionPhotoSource

logger = logging.getLogger(__name__)


class BidfaxSource(AuctionPhotoSource):
    name = "Bidfax"

    def __init__(self):
        settings = get_settings()
        self.flaresolverr_url = f"{settings.flaresolverr_url.rstrip('/')}/v1"

    async def search_by_vin(self, vin: str) -> list[str]:
        logger.info(f"[{self.name}] Шукаю VIN {vin} через DuckDuckGo...")

        # 1. Формуємо правильний URL для DuckDuckGo (шукаємо тільки по bidfax.info)
        search_url = f"https://html.duckduckgo.com/html/?q={vin}"

        # 2. Шукаємо лінк на Bidfax (Асинхронно!)
        bidfax_url = await self._get_link_from_google(search_url)
        if not bidfax_url:
            # Якщо нічого не знайшли, повертаємо порожній список (агрегатор піде далі до PLC)
            return []

        logger.info(f"[{self.name}] Знайдено лот: {bidfax_url}. Завантажую сторінку...")

        # 3. Отримуємо HTML сторінки авто через FlareSolverr
        # (Увага: перевір, чи твій метод називається _fetch_via_flaresolverr чи _fetch_page_html.
        # Я залишив _fetch_via_flaresolverr, як було у твоєму першому рядку)
        car_html = await self._fetch_page_html(bidfax_url)
        if not car_html:
            return []

        # 4. Витягуємо фотографії з HTML коду сторінки автомобіля
        photos = self._extract_photos(car_html)
        logger.info(f"[{self.name}] Успішно знайдено {len(photos)} фото.")

        return photos

    async def _get_link_from_google(self, url: str) -> str | None:
        payload = {"cmd": "request.get", "url": url, "maxTimeout": 40000}
        try:
            async with httpx.AsyncClient(timeout=45.0) as client:
                response = await client.post(self.flaresolverr_url, json=payload)
                if response.status_code != 200:
                    return None

                html = response.json().get("solution", {}).get("response", "")

                logger.info(f"--- [DEBUG] RAW HTML ВІД ПОШУКОВИКА ---")
                logger.info(html[:1500])
                logger.info(f"-----------------------------------")

                # Створюємо soup лише один раз!
                soup = BeautifulSoup(html, "lxml")

                # Виводимо знайдені лінки у видачі для дебагу
                all_links = [a.get('href') for a in soup.find_all('a', href=True)]
                logger.info(f"[DEBUG] Усі знайдені href у видачі (перші 20):")
                for i, link in enumerate(all_links[:20], 1):
                    logger.info(f"   {i}. {link}")

                found_links = []
                for a_tag in soup.find_all("a", href=True):
                    href = a_tag["href"]

                    # 1. Якщо це лінк від DuckDuckGo: дістаємо і декодуємо
                    if "uddg=" in href:
                        try:
                            href = urllib.parse.unquote(href.split("uddg=")[1].split("&")[0])
                        except Exception:
                            continue

                    # 2. Якщо це лінк від Google (на випадок, якщо колись повернемося):
                    elif "/url?q=" in href:
                        try:
                            href = urllib.parse.unquote(href.split("/url?q=")[1].split("&")[0])
                        except Exception:
                            continue

                    # 3. Перевіряємо, чи отримали ми чистий лінк на Bidfax
                    if "bidfax.info" in href.lower():
                        found_links.append(href)
                        # Відкидаємо головні сторінки, шукаємо конкретний лот
                        if href.lower() not in ["https://bidfax.info/", "https://bidfax.info", "http://bidfax.info/",
                                                "http://bidfax.info"]:
                            logger.info(f"--- [DEBUG] ЗНАЙДЕНО ЧИСТИЙ ЛІНК BIDFAX: {href} ---")
                            return href

                # Допомагає побачити в логах усе, що знайшов пошуковик, якщо точного збігу не було
                logger.info(f"[{self.name}] Усі знайдені лінки Bidfax: {found_links}")

        except Exception as e:
            logger.error(f"[{self.name}] Помилка пошуку: {e}")

        return None

    async def _fetch_page_html(self, url: str) -> str | None:
        payload = {"cmd": "request.get", "url": url, "maxTimeout": 60000}
        try:
            async with httpx.AsyncClient(timeout=65.0) as client:
                response = await client.post(self.flaresolverr_url, json=payload)
                if response.status_code == 200 and response.json().get("status") == "ok":
                    return response.json().get("solution", {}).get("response", "")
        except Exception as e:
            logger.error(f"[{self.name}] Помилка завантаження сторінки лоту: {e}")

        return None


    def _extract_photos(self, html: str) -> list[str]:
        soup = BeautifulSoup(html, "lxml")
        links = []

        for img in soup.select("ul.xfieldimagegallery img"):
            src = img.get("src")
            if src:
                if src.startswith("/"):
                    src = f"https://bidfax.info{src}"
                links.append(src)

        return list(set(links))