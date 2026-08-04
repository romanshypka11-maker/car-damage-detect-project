import os
import time
import requests
from bs4 import BeautifulSoup


class DeepAutoScraper:
    def __init__(self):
        # Визначаємо URL FlareSolverr залежно від середовища
        if os.getenv("IS_DOCKER") == "true":
            self.flaresolverr_url = "http://flaresolverr:8191/v1"
        else:
            self.flaresolverr_url = "http://127.0.0.1:8191/v1"

        # Словник правил для BeautifulSoup
        self.site_rules = {
            "plc": {
                "selector": "link[itemprop='image']",
                "attr_name": "href",
                "url_prefix": "https://plc.ua/"
            }
        }

    def search_vin_on_plc(self, vin):
        print(f"🔍 Шукаємо VIN {vin} через Google Proxy для сайту PLC.ua...")

        # Запит до Google (шукаємо суто на домені plc.ua)
        google_search_url = f"https://www.google.com/search?q={vin}"

        payload = {
            "cmd": "request.get",
            "url": google_search_url,
            "maxTimeout": 40000
        }

        try:
            response = requests.post(self.flaresolverr_url, json=payload, timeout=45)
            if response.status_code != 200:
                print(f"❌ FlareSolverr API помилка при довідці в Google: {response.status_code}")
                return []

            html = response.json().get("solution", {}).get("response", "")
            soup = BeautifulSoup(html, "lxml")

            all_links = soup.find_all("a", href=True)
            print(f"📡 Сторінка Google успішно отримана. Фільтруємо результати...")

            valid_links = []
            for a_tag in all_links:
                url = a_tag["href"]

                # Розшифровуємо внутрішні редиректи Google, якщо вони є в HTML
                if "/url?q=" in url:
                    url = url.split("/url?q=")[1].split("&")[0]
                    import urllib.parse
                    url = urllib.parse.unquote(url)

                # Перевіряємо, чи це посилання веде на картку лоту PLC.ua
                if "plc.ua" in url.lower() and "/auctions/lot/" in url.lower():
                    print(f"🎯 Динамічний лінк на лот успішно витягнуто: {url}")
                    valid_links.append((url, "plc"))
                    break  # Нам достатньо першого точного збігу з видачі

            return valid_links

        except Exception as e:
            print(f"❌ Помилка пошуку через Google Proxy: {e}")
            return []

    def fetch_page_html(self, url):
        print(f"🕵️‍♂️ Sending request to FlareSolverr proxy for: {url}")

        payload = {
            "cmd": "request.get",
            "url": url,
            "maxTimeout": 60000  # 60 секунд на проходження Turnstile
        }

        try:
            response = requests.post(self.flaresolverr_url, json=payload, timeout=65)

            if response.status_code == 200:
                res_json = response.json()
                status = res_json.get("status")

                if status == "ok":
                    print("✅ FlareSolverr successfully bypassed Cloudflare!")
                    return res_json.get("solution", {}).get("response", "")
                else:
                    print(f"⚠️ FlareSolverr returned status: {status}. Message: {res_json.get('message')}")
                    return None
            else:
                print(f"❌ FlareSolverr API error. Status code: {response.status_code}")
                return None

        except Exception as e:
            print(f"❌ Failed to connect to FlareSolverr: {e}")
            return None

    def extract_photos(self, html, domain_keyword):
        if not html:
            return []

        soup = BeautifulSoup(html, 'lxml')
        links = []

        rule = self.site_rules[domain_keyword]
        tags = soup.select(rule["selector"])

        # 1. Спроба А: Збір за стандартним селектором
        for tag in tags:
            href = tag.get(rule["attr_name"])
            if href:
                links.append(href)

        # 2. Спроба Б (Страховка): Якщо лінків немає, парсимо прямі згадки фото
        if not links:
            for tag in soup.find_all(["link", "img", "a"]):
                for attr in ["href", "src", "data-src"]:
                    val = tag.get(attr)
                    if val and "img.plc.ua/full" in val:
                        links.append(val)

        # Очищення посилань
        clean_links = []
        for l in links:
            if l.startswith("//"):
                l = "https:" + l
            if any(ext in l.lower() for ext in [".jpg", ".jpeg", ".png", ".webp"]):
                clean_links.append(l)

        final_links = list(set(clean_links))
        print(f"📸 Extracted {len(final_links)} valid photo links.")
        return final_links

    def shutdown(self):
        pass


def get_photos_by_vin(vin: str):
    """ Universal clean facade for the Telegram bot interface. """
    scraper = DeepAutoScraper()
    try:
        links_to_check = scraper.search_vin_on_plc(vin)
        if not links_to_check:
            return []

        for url, domain_keyword in links_to_check:
            raw_html = scraper.fetch_page_html(url)
            all_photos = scraper.extract_photos(raw_html, domain_keyword)

            if all_photos:
                print(f"📸 Found picture on {url}, returning results.")
                return all_photos
        return []
    except Exception as e:
        print(f"❌ Error inside get_photos_by_vin function: {e}")
        return []
    finally:
        scraper.shutdown()


if __name__ == "__main__":
    # Тестовий VIN з твого скріншоту
    test_vin = "WA1VAAF7XJD019981"

    print(" Launching isolated testing sequence for 'get_photos_by_vin'...")
    print(f"Test Target VIN: {test_vin}\n" + "=" * 50)

    start_time = time.time()
    photos = get_photos_by_vin(test_vin)
    end_time = time.time()

    print("=" * 50)
    if photos:
        print(f"🎉 TEST SUCCESSFUL! Found {len(photos)} photos in {round(end_time - start_time, 2)} seconds:")
        for i, link in enumerate(photos, 1):
            print(f"  {i}. {link}")
    else:
        print("❌ Scraper sequence yielded no photos or target endpoint did not respond.")