import logging
import urllib.parse

import requests
from bs4 import BeautifulSoup

from core.config import get_settings

logger = logging.getLogger(__name__)


class DeepAutoScraper:
    def __init__(self):
        settings = get_settings()
        self.flaresolverr_url = f"{settings.flaresolverr_url.rstrip('/')}/v1"
        self.site_rules = {
            "plc": {
                "selector": "link[itemprop='image']",
                "attr_name": "href",
                "url_prefix": "https://plc.ua/",
            }
        }

    def search_vin_on_plc(self, vin):
        logger.info("Searching VIN %s via Google Proxy for PLC.ua", vin)
        google_search_url = f"https://www.google.com/search?q={vin}"
        payload = {"cmd": "request.get", "url": google_search_url, "maxTimeout": 40000}

        try:
            response = requests.post(self.flaresolverr_url, json=payload, timeout=45)
            if response.status_code != 200:
                logger.warning("FlareSolverr API error during Google search: %s", response.status_code)
                return []

            html = response.json().get("solution", {}).get("response", "")
            soup = BeautifulSoup(html, "lxml")
            valid_links = []

            for a_tag in soup.find_all("a", href=True):
                url = a_tag["href"]
                if "/url?q=" in url:
                    url = url.split("/url?q=")[1].split("&")[0]
                    url = urllib.parse.unquote(url)
                if "plc.ua" in url.lower() and "/auctions/lot/" in url.lower():
                    logger.info("Found PLC.ua lot link: %s", url)
                    valid_links.append((url, "plc"))
                    break
            return valid_links
        except Exception:
            logger.exception("Error searching VIN via Google Proxy")
            return []

    def fetch_page_html(self, url):
        payload = {"cmd": "request.get", "url": url, "maxTimeout": 60000}
        try:
            response = requests.post(self.flaresolverr_url, json=payload, timeout=65)
            if response.status_code != 200:
                return None
            res_json = response.json()
            if res_json.get("status") == "ok":
                return res_json.get("solution", {}).get("response", "")
            return None
        except Exception:
            logger.exception("Failed to fetch page via FlareSolverr: %s", url)
            return None

    def extract_photos(self, html, domain_keyword):
        if not html:
            return []

        soup = BeautifulSoup(html, "lxml")
        rule = self.site_rules[domain_keyword]
        links = []

        for tag in soup.select(rule["selector"]):
            href = tag.get(rule["attr_name"])
            if href:
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


def get_photos_by_vin(vin: str) -> list[str]:
    scraper = DeepAutoScraper()
    try:
        links_to_check = scraper.search_vin_on_plc(vin)
        if not links_to_check:
            return []
        for url, domain_keyword in links_to_check:
            raw_html = scraper.fetch_page_html(url)
            all_photos = scraper.extract_photos(raw_html, domain_keyword)
            if all_photos:
                return all_photos
        return []
    except Exception:
        logger.exception("Error in get_photos_by_vin")
        return []
