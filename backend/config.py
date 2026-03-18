from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    # ── Anthropic (Eurydice / Claude orchestration) ───────────────────────────
    anthropic_api_key: Optional[str] = None
    claude_model: str = "claude-sonnet-4-6"
    claude_haiku_model: str = "claude-haiku-4-5-20251001"

    # ── Google AI Studio (Logos / Gemini Live) ────────────────────────────────
    gemini_api_key: Optional[str] = None

    # Vertex AI (ADC auth) — set gcp_project_id to enable Vertex AI mode
    gcp_project_id: Optional[str] = None
    gcp_region: str = "us-central1"

    gemini_model: str = "gemini-2.5-flash-native-audio-preview-12-2025"

    # ── Domain routing ────────────────────────────────────────────────────────
    # "eurydice" → Claude Messages API + Eurydice guitar tools
    # "logos"    → Gemini Live API + Logos Greek philology tools (default)
    domain: str = "logos"

    mock_mode: bool = False
    allowed_origins: str = "http://localhost:3000"

    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()

# ── Mode flags ────────────────────────────────────────────────────────────────

# Eurydice: Claude API available and domain is set to eurydice
USE_CLAUDE = bool(settings.anthropic_api_key) and settings.domain == "eurydice"

# Logos: Vertex AI is only used when no API key is available.
USE_VERTEX_AI = bool(settings.gcp_project_id) and not bool(settings.gemini_api_key)

# Fall back to mock when no AI backend is configured
USE_MOCK = settings.mock_mode or (
    not USE_CLAUDE
    and not settings.gemini_api_key
    and not USE_VERTEX_AI
)
