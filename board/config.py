from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    board_host: str = "0.0.0.0"
    board_port: int = 8000
    board_db_path: str = "./data/board.db"
    board_admin_key: str
    poll_interval_seconds: int = 5


@lru_cache
def get_settings() -> Settings:
    return Settings()
