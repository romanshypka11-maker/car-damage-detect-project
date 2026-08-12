from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Paths ---
    base_dir: Path = Field(default_factory=lambda: Path(__file__).resolve().parent.parent)
    models_dir: Path | None = None
    feature_columns_path: Path | None = None

    # --- Database ---
    db_name: str = Field(default="car_listings", alias="DB_NAME")
    db_user: str = Field(default="postgres", alias="DB_USER")
    db_password: str = Field(default="", alias="DB_PASSWORD")
    db_host: str = Field(default="localhost", alias="DB_HOST")
    db_port: int = Field(default=5432, alias="DB_PORT")
    db_table: str = Field(default="car_listings", alias="DB_TABLE")

    # --- External services ---
    ollama_url: str = Field(default="http://127.0.0.1:11434", alias="OLLAMA_URL")
    ollama_model: str = Field(default="qwen3:8b", alias="OLLAMA_MODEL")
    ai_service_url: str = Field(default="http://api_server:8000", alias="AI_SERVICE_URL")
    flaresolverr_url: str = Field(default="http://flaresolverr:8191", alias="FLARESOLVERR_URL")

    # --- Telegram ---
    bot_token: str = Field(default="", alias="BOT_TOKEN")

    # --- Runtime ---
    is_docker: bool = Field(default=False, alias="IS_DOCKER")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    def model_post_init(self, __context) -> None:
        if self.models_dir is None:
            self.models_dir = self.base_dir / "models_ML"
        if self.feature_columns_path is None:
            self.feature_columns_path = self.base_dir / "feature_columns.json"

    @property
    def db_connect_args(self) -> dict:
        host = self.db_host
        if self.is_docker and host in ("127.0.0.1", "localhost"):
            host = "host.docker.internal"
        return {
            "database": self.db_name,
            "user": self.db_user,
            "password": self.db_password,
            "host": host,
            "port": self.db_port,
        }

    @property
    def catboost_model_path(self) -> Path:
        return self.models_dir / "current_model_for_car_predict_price_cat_boost"

    @property
    def cv_zone_model_path(self) -> Path:
        return self.models_dir / "detect_damage_zone_final.pth"

    @property
    def cv_defects_model_path(self) -> Path:
        return self.models_dir / "rf_detr_car_damage_final_auction_damage.pth"


@lru_cache
def get_settings() -> Settings:
    return Settings()
