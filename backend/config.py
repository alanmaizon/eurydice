from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    # Google AI Studio (API key auth)
    gemini_api_key: Optional[str] = None

    # Vertex AI (ADC auth) — set gcp_project_id to enable Vertex AI mode
    gcp_project_id: Optional[str] = None
    gcp_region: str = "us-central1"

    gemini_model: str = "gemini-2.5-flash-native-audio-preview-12-2025"
    mock_mode: bool = False
    allowed_origins: str = "http://localhost:3000"

    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()

# Priority: AI Studio (GEMINI_API_KEY) > Vertex AI (GCP_PROJECT_ID) > Mock
# Vertex AI is only used when no API key is available.
USE_VERTEX_AI = bool(settings.gcp_project_id) and not bool(settings.gemini_api_key)
USE_MOCK = settings.mock_mode or (not settings.gemini_api_key and not USE_VERTEX_AI)
