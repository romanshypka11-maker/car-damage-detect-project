import asyncio
import os
import asyncpg
import aiohttp
from spider import Spider, SpiderConfig
import random
from scraper_main.scraper import parse_car_html, DB_CONFIG, MAX_CONCURRENT_REQUESTS
import time

async def save_to_db(pool, car_data):
    """Вставляє дані в PostgreSQL на основі ключів словника"""
    if not car_data:
        return print("Немає даних")

    keys = car_data.keys()
    columns = ", ".join(car_data.keys())
    placeholders = ", ".join([f"${i+1}" for i in range(len(car_data))])
    table_name = DB_CONFIG.get("table") or "car_listings"

    query = f"""
    INSERT INTO {table_name} ({columns})
    VALUES ({placeholders})
    ON CONFLICT (url) DO NOTHING;
    """
    async with pool.acquire() as conn:
        try:
            await conn.execute(query, *car_data.values())
        except Exception as e:
            print(f"Помилка БД: {e}")

async def worker(url, session, pool,semaphore):
    """Обробка одного посилання"""
    async with semaphore:
        try:
            await asyncio.sleep(random.uniform(1.5, 2.5))

            async with session.get(url, timeout=15) as response:
                if response.status == 200:
                    html = await response.text()

                    car_data = parse_car_html(html, url)
                    await save_to_db(pool, car_data)
                    print(f" Оброблено: {car_data.get('make')} {car_data.get('model')} | {url}")
                else:
                    print(f"Помилка з посиланням {response.status}: {url}")
        except Exception as e:
            print(f"Помилка при завантаженні {url}: {e}")

async def run_scraper_stage():
    """ Асинхронний скрапінг посилань з файлу"""
    if not os.path.exists("links/audi_links.txt"):
        print("File _links.txt not found!")
        return
    START_LINE = 0

    with open("electro_clean.txt", "r", encoding="utf-8") as f:
        all_urls = [line.strip() for line in f if line.strip()]
        urls = all_urls[START_LINE:]

        total_links = len(urls)
        print(f" Завантажено {total_links} лінків. Починаємо скрапінг...")

        # Фіксуємо час старту
        start_time = time.time()

        pg_config = DB_CONFIG.copy()
        pg_config.pop("table",None)

        poll = await asyncpg.create_pool(**pg_config)

        semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)

        async with aiohttp.ClientSession() as session:
            tasks = [worker(url,session,poll,semaphore) for url in urls]
            await asyncio.gather(*tasks)
        await poll.close()

        # 2. Фіксуємо час завершення
        end_time = time.time()

        # 3. РАХУЄМО РЕЗУЛЬТАТИ
        duration = end_time - start_time  # загальний час у секундах
        minutes = duration / 60
        speed = total_links / duration if duration > 0 else 0

        print(f" АНАЛІЗ ШВИДКОСТІ:")
        print(f" Загальний час: {duration:.2f} сек ({minutes:.2f} хв)")
        print(f" Оброблено машин: {total_links}")
        print(f" Середня швидкість: {speed:.2f} маш/сек")
        print("=" * 30)

def run_spider_stage():
    """Get links"""
    print("Run spider....")
    config = SpiderConfig()
    bot = Spider(config)
    bot.run()

def main():
    #run_spider_stage()
    print("\n Let’s move on to processing the adverts... ")
    asyncio.run(run_scraper_stage())

    print("All data in PostgreSQL")
if __name__ == "__main__":
    main()