import httpx
from modules.base import BaseParser
from scraper_main.scraper import parse_car_html


class AutoRiaParser(BaseParser):
    def __init__(self):
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        self.timeout = httpx.Timeout(10.0, connect=5.0)
    async def get_data(self, url:str):
        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(url, follow_redirects=True,headers = self.headers)
                if response.status_code != 200:
                    return {"error": f"Сайт повернув статус {response.status_code}"}

                car_data = parse_car_html(response.text,url)
                return car_data
            except httpx.RequestError as e:
                return {"error": f"Помилка мережі: {str(e)}"}
            except Exception as e:
                return {"error": f"Сталася помилка при парсингу: {str(e)}"}





