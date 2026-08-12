import requests
from bs4 import BeautifulSoup
import time
import random
from scraper_main.config_brands import BRANDS_TO_SCRAPE


class SpiderConfig:
    def __init__(self, brand_id, brand_name):
        self.MARK_ID = brand_id
        self.BRAND_NAME = brand_name
        self.MODELS = None
        self.YEARS = range(1990, 2027)
        self.MODE = "GLOBAL"


class URLBuilder:
    @staticmethod
    def build_url(config, model=None, year=None, page=0):
        base_url = "https://auto.ria.com/uk/search/?"
        query_parts = [
            "search_type=1",
            "category=1",
            "all[0].any[0].fuel[0]=6",
            "abroad=0",
            "customs_cleared=1",
            f"page={page}",
            "limit=100"
        ]

        if config.MODE == "DETAILED" and year:
            query_parts.append(f"all[0].any[0].year[0]={year}")
            query_parts.append(f"all[0].any[0].year[1]={year}")
            if model:
                query_parts.append(f"all[0].any[0].model[0]={model}")
        else:
            # Режим GLOBAL або якщо рік не передано
            query_parts.append(f"all[0].any[0].year[0]={config.YEARS.start}")
            query_parts.append(f"all[0].any[0].year[1]={config.YEARS.stop - 1}")

        return base_url + "&".join(query_parts)


class Spider:
    def __init__(self, config):
        self.config = config
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
        }
        # Завантажуємо старі лінки ОДРАЗУ, щоб не дублювати їх у файлі
        self.seen_links = self._load_existing_links()

    def _load_existing_links(self):
        try:
            with open("links.txt", "r", encoding="utf-8") as f:
                return set(line.strip() for line in f if line.strip())
        except FileNotFoundError:
            return set()

    def scrape_detailed(self):
        # Проходимо по кожному року з твого конфігу
        for yr in self.config.YEARS:
            print(f"\n--- 📅 Обробляємо {yr} рік ---")
            page = 0
            while True:
                # Будуємо URL для конкретного року та сторінки
                url = URLBuilder.build_url(self.config, year=yr, page=page)

                # Отримуємо кількість знайдених оголошень на сторінці
                found_on_page = self._fetch_and_save(url)

                # Якщо повернулося -1 (помилка), спробуємо наступну сторінку, не зупиняючи весь рік
                if found_on_page == -1:
                    page += 1
                    continue

                # Якщо знайдено 0 — значить оголошення за цей рік закінчилися
                if found_on_page == 0:
                    print(f"🏁 Рік {yr} завершено на сторінці {page}")
                    break

                page += 1
                time.sleep(random.uniform(1.5, 2))

    def run(self):
        start_time = time.perf_counter()
        print(f" Старт у режимі: {self.config.MODE}")

        initial_count = len(self.seen_links)

        if self.config.MODE == "GLOBAL":
            # Збирає перші 100 сторінок (те, що ти вже зробив)
            last_page = self.scrape_logic(is_global=True)
            print(f"Зупинився на сторінці: {last_page}")

        elif self.config.MODE == "DETAILED":
            # Збирає все по роках, обходячи ліміт у 100 сторінок
            self.scrape_detailed()

        end_time = time.perf_counter()
        # Розрахунки
        total_seconds = end_time - start_time
        minutes = int(total_seconds // 60)
        seconds = int(total_seconds % 60)

        new_links_count = len(self.seen_links) - initial_count


        print(f" Збір завершено!")
        print(f" Час виконання: {minutes} хв {seconds} сек")
        print(f" Додано нових лінків: {new_links_count}")
        print(f" Усього унікальних лінків у базі: {len(self.seen_links)}")

        if new_links_count > 0:
            avg_speed = total_seconds / new_links_count
            print(f"⚡ Темп: {avg_speed:.2f} сек на один НОВИЙ лінк")




    def scrape_logic(self, is_global):
        if is_global:
            page = 0
            while True:
                url = URLBuilder.build_url(self.config, page=page)
                res = self._fetch_and_save(url)

                if res == 0:
                    print(f"Оголошення закінчились на сторінці{page}")
                    return page

                if res == -1:
                    print(f"Пропускаємо помилкову сторінку {page}")

                page += 1
                print(f" Готуємося до сторінки {page}...")
                time.sleep(random.uniform(2, 3))
        else:
            # Логіка для DETAILED (по роках і моделях)
            for m_id in (self.config.MODELS or []):
                for yr in self.config.YEARS:
                    url = URLBuilder.build_url(self.config, model=m_id, year=yr, page=0)
                    self._fetch_and_save(url)
                    time.sleep(random.uniform(2, 3))
                return "N/A (Detailed Mode)"

    def _fetch_and_save(self, url):
        try:
            response = requests.get(url, headers=self.headers, timeout=30)
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, "lxml")
                # Шукаємо всі картки (клас може бути product-card або ticket-item)
                links = soup.find_all("a", class_="product-card")

                total_on_page = len(links)
                if total_on_page == 0:
                    return 0

                current_batch = []
                for a in links:
                    href = a.get("href")
                    if href and "/auto_" in href:
                        full_url = href if href.startswith("http") else "https://auto.ria.com" + href
                        if full_url not in self.seen_links:
                            current_batch.append(full_url)
                            self.seen_links.add(full_url)

                if current_batch:
                    self._write_to_file(current_batch)
                    print(f"   ✅ Додано нових: {len(current_batch)}")

                return total_on_page  # Повертаємо 100 (або скільки там є)

            return -1  # Помилка сервера
        except Exception as e:
            print(f"⚠️ Помилка: {e}")
            return -1

    def _write_to_file(self, new_links):
         #Записуємо в загальну базу (Master Log) для уникнення дублів
        with open("electro_links.txt", "a", encoding="utf-8") as f:
            for link in new_links:
                f.write(link + "\n")


if __name__ == "__main__":
    for brand_name, brand_id in BRANDS_TO_SCRAPE.items():
        # Створюємо унікальний конфіг для кожної марки
        config = SpiderConfig(brand_id, brand_name)
        bot = Spider(config)
        bot.run()

        # Пауза між марками, щоб Wi-Fi не ліг і IP не забанили
        wait = random.randint(15, 35)
        print(f"🏁 {brand_name.upper()} завершено. Відпочиваємо {wait}с...")
        time.sleep(wait)