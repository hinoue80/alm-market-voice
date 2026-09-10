import os
from pydantic_settings import BaseSettings, SettingsConfigDict

# Resolve .env path relative to this file — works regardless of where uvicorn is launched from
_ENV_FILE = os.path.join(os.path.dirname(__file__), "..", "..", ".env")

# Default SQLite file lives at <repo>/alm-market-voice/data/alm_market_voice.db locally,
# or /data/alm_market_voice.db inside the container (DATABASE_URL env var overrides this).
# __file__ is backend/app/config.py → go up two levels to reach backend/, then one more to alm-market-voice/
_DEFAULT_DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data")
_DEFAULT_DB_URL = f"sqlite:///{os.path.abspath(_DEFAULT_DATA_DIR)}/alm_market_voice.db"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Tavily
    tavily_api_key: str = ""

    # watsonx.ai
    watsonx_api_key: str = ""
    watsonx_project_id: str = ""
    watsonx_url: str = "https://us-south.ml.cloud.ibm.com"

    # Anthropic Claude (enrichment — fast, high quality, low cost)
    # Get key at https://console.anthropic.com/settings/keys
    # Uses claude-haiku-3-5 (~$0.001 per signal). Leave blank to disable.
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-haiku-4-5"

    # OpenAI (fallback enrichment when watsonx quota is exhausted)
    openai_api_key: str = ""

    # Ollama (local LLM — free, no quota, runs on Apple Silicon)
    ollama_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.2"

    # Database — SQLite by default (free, no server needed).
    # Override with DATABASE_URL=postgresql://... to use PostgreSQL.
    # In production (Code Engine): DATABASE_URL=sqlite:////data/alm_market_voice.db
    database_url: str = _DEFAULT_DB_URL

    # App
    app_env: str = "development"
    secret_key: str = "change-me"
    cors_origins: str = "http://localhost:5173,https://hinoue80.github.io"

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",")]


settings = Settings()

# Ensure the directory for a SQLite database file exists at import time
if settings.database_url.startswith("sqlite:///"):
    _db_path = settings.database_url.replace("sqlite:///", "")
    os.makedirs(os.path.dirname(_db_path), exist_ok=True)
