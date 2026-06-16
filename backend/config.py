from functools import lru_cache
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "Resumonkey"
    debug: bool = False

    # Database — SQLite for local dev, PostgreSQL (Supabase) for prod
    database_url: str = "sqlite:///./resume_adapter.db"

    # Local fallback dirs (only used when Supabase is not configured)
    upload_dir: str = "./uploads"
    output_dir: str = "./outputs"
    max_upload_mb: int = 20

    # Supabase (Storage + optionally DB) — leave empty for local dev
    supabase_url: str = ""
    supabase_service_key: str = ""
    supabase_bucket: str = "resumes"

    # CORS — comma-separated list of allowed origins
    allowed_origins: str = "http://localhost:3000"

    # AI providers
    openai_api_key: str = ""
    groq_api_key: str = ""
    gemini_api_key: str = ""
    anthropic_api_key: str = ""

    # Jina Reader (job scraping). Optional API key — without it the free tier
    # rate-limits aggressively (causes intermittent 0-result searches). A free
    # key from jina.ai raises the limit dramatically.
    jina_api_key: str = ""

    # LLM defaults
    default_llm_provider: str = "openai"
    default_llm_model: str = "gpt-4o"
    max_retries: int = 3
    retry_delay_seconds: float = 2.0

    class Config:
        env_file = ".env"
        case_sensitive = False


@lru_cache
def get_settings() -> Settings:
    return Settings()
