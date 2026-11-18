import os
import secrets
from pathlib import Path
from typing import Literal

from pydantic import model_validator
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
    auth_secret: str = ""
    auth_mode: Literal["legacy", "clerk"] = "clerk"
    clerk_secret_key: str = ""
    clerk_jwt_key: str = ""
    clerk_issuer: str = ""
    clerk_authorized_parties: list[str] = []
    clerk_audience: str = ""
    web_url: str = "http://localhost:3000"
    openai_api_key: str = ""
    design_model: str = ""
    openai_model: str = "gpt-5.5"
    github_client_id: str = ""
    github_client_secret: str = ""
    github_callback_url: str = "http://localhost:3000/api/auth/github/callback"
    cookie_secure: bool = False
    max_upload_bytes: int = 10 * 1024 * 1024
    auto_create_tables: bool = False

    @model_validator(mode="after")
    def secure_defaults(self):
        if self.app_env not in ("development", "test"):
            if len(self.auth_secret) < 32 or not self.cookie_secure:
                raise ValueError(
                    "Production requires AUTH_SECRET of 32+ characters and COOKIE_SECURE=true"
                )
            if self.auto_create_tables:
                raise ValueError("Use migrations in production")
        if not self.auth_secret:
            self.auth_secret = secrets.token_urlsafe(48)
        return self


settings = Settings(_env_file=None) if os.getenv("APP_ENV") == "test" else Settings()
