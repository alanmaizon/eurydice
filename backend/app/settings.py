"""Environment-driven settings for the Ancient Greek tutor service."""

from __future__ import annotations

import json
import re
from functools import lru_cache
from typing import Annotated, Any

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

from .schemas import TutorMode


class Settings(BaseSettings):
    app_name: str = "Ancient Greek Live Tutor"
    environment: str = "development"
    host: str = "0.0.0.0"
    port: int = 8000
    log_level: str = "INFO"
    cors_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: [
            "http://localhost:3000",
            "http://127.0.0.1:3000",
            "http://localhost:5173",
            "http://127.0.0.1:5173",
        ]
    )
    google_cloud_project: str | None = None
    google_cloud_location: str = "us-central1"
    gemini_api_key: str | None = None
    gemini_connect_timeout_seconds: float = 8.0
    gemini_live_model: str = "gemini-2.5-flash-native-audio-latest"
    gemini_response_model: str = "gemini-2.5-flash"
    use_google_adk: bool = True
    default_tutoring_mode: TutorMode = TutorMode.guided_reading
    websocket_path: str = "/ws/live"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="TUTOR_",
        extra="ignore",
    )

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, value: Any) -> list[str]:
        if value in (None, ""):
            return [
                "http://localhost:3000",
                "http://127.0.0.1:3000",
                "http://localhost:5173",
                "http://127.0.0.1:5173",
            ]
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        if isinstance(value, str):
            stripped = value.strip()
            if stripped.startswith("["):
                parsed = json.loads(stripped)
                if not isinstance(parsed, list):
                    raise ValueError("TUTOR_CORS_ORIGINS must decode to a list of origins")
                return [str(item).strip() for item in parsed if str(item).strip()]
            # Accept both comma and semicolon delimiters for easier Cloud Build substitutions.
            return [item.strip() for item in re.split(r"[;,]", stripped) if item.strip()]
        raise TypeError("Unsupported value for TUTOR_CORS_ORIGINS")


@lru_cache
def get_settings() -> Settings:
    return Settings()
