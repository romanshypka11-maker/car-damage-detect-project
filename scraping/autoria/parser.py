import logging
import httpx
from .html_parser import parse_car_html

logger = logging.getLogger(__name__)


class AutoRiaParser:
    def __init__(self):
        self.headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
        }
        self.timeout = httpx.Timeout(10.0, connect=5.0)

    async def get_data(self, url: str) -> dict:
        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(
                    url,
                    follow_redirects=True,
                    headers=self.headers,
                    timeout=self.timeout,
                )
                if response.status_code != 200:
                    return {"error": f"Сайт повернув статус {response.status_code}"}

                return parse_car_html(response.text, url)

            except httpx.RequestError as e:
                return {"error": f"Помилка мережі: {str(e)}"}
            except Exception as e:
                logger.exception("Parsing error in AutoRiaParser")
                return {"error": f"Сталася помилка при парсингу: {str(e)}"}