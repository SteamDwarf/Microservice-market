import os
from typing import List

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    DEBUG: bool = True

    SECRET_KEY: str = os.getenv(
        "SECRET_KEY", "dev-secret-key-change-in-production"
    )
    ALGORITHM: str = "HS256"

    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24

    DATABASE_URL: str = os.getenv("DATABASE_URL")

    TIME_ZONE: str = "Europe/Moscow"
    LANGUAGE_CODE: str = "ru-ru"

    ALLOWED_HOSTS: List[str] = os.getenv(
        "ALLOWED_HOSTS", "localhost,127.0.0.1"
    ).split(",")

    model_config = SettingsConfigDict(env_file=".env")

    @field_validator("DEBUG", mode="before")
    @classmethod
    def parse_debug(cls, value):
        if isinstance(value, bool):
            return value
        if value is None:
            return True

        normalized = str(value).strip().lower()
        if normalized in {"1", "true", "yes", "on", "debug", "dev"}:
            return True
        if normalized in {
            "0",
            "false",
            "no",
            "off",
            "release",
            "prod",
            "production",
        }:
            return False
        raise ValueError("DEBUG must be a boolean-like value")


settings = Settings()
