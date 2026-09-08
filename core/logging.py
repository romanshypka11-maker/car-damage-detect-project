import logging
from pathlib import Path
from core.config import get_settings


def setup_logging() -> None:
    settings = get_settings()
    level = getattr(logging, settings.log_level.upper(), logging.INFO)
    log_dir = Path("/app/logs")
    log_dir.mkdir(exist_ok=True)
    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=[
            logging.StreamHandler(),  # лишається в docker logs
            logging.FileHandler(log_dir / "app.log"),  # + пише у файл
        ],
    )
