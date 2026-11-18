import os
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(str(Path(__file__).resolve().parents[3] / ".env"), ".env"),
        extra="ignore",
    )
    app_env: str = "development"
    database_url: str = (
        "postgresql+psycopg://galvanise:galvanise@localhost:5433/galvanise"
    )
    clerk_secret_key: str = ""
    clerk_jwt_key: str = ""
    clerk_issuer: str = ""
    clerk_authorized_parties: list[str] = []
    clerk_audience: str = ""
    web_url: str = "http://localhost:3000"
    source_token_encryption_key: str = ""
    openai_api_key: str = ""
    design_model: str = ""
    openai_model: str = "gpt-5.5"
    max_upload_bytes: int = 10 * 1024 * 1024
    auto_create_tables: bool = False


settings = Settings(_env_file=None) if os.getenv("APP_ENV") == "test" else Settings()
