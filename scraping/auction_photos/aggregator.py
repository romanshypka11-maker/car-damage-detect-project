import logging
from .sources.plc_ua import PlcUaSource
from .sources.bidfax import BidfaxSource

logger = logging.getLogger(__name__)


class PhotoAggregator:
    def __init__(self):
        # Тут ми задаємо пріоритет джерел.
        self.sources = [
            BidfaxSource(),
            PlcUaSource()
        ]

    async def get_photos(self, vin: str) -> list[str]:
        """
        Метод-менеджер: опитує джерела по черзі, доки не знайде фото.
        """
        if not vin or vin == "Прихований":
            return []

        for source in self.sources:
            try:
                logger.info(f"[Aggregator] Спроба отримати фото через {source.name}...")
                photos = await source.search_by_vin(vin)

                # Якщо знайшли — повертаємо одразу і виходимо (коротке замикання)
                if photos:
                    logger.info(f"[Aggregator] Успішно! Знайдено {len(photos)} фото через {source.name}")
                    return photos

                logger.info(f"[Aggregator] {source.name} нічого не знайшов.")

            except Exception as e:
                # Якщо джерело впало (таймаут, помилка сайту), логуємо і йдемо далі
                logger.error(f"[Aggregator] Помилка джерела {source.name}: {e}")
                continue

        logger.warning(f"[Aggregator] Фото для VIN {vin} не знайдено на жодному з джерел.")
        return []