from functools import lru_cache
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "Resume Adapter"
    debug: bool = False

    # Storage
    database_url: str = "sqlite:///./resume_adapter.db"
    upload_dir: str = "./uploads"
    output_dir: str = "./outputs"
    max_upload_mb: int = 20

    # AI providers
    openai_api_key: str = ""
    groq_api_key: str = ""

    # LLM defaults
    default_llm_provider: str = "openai"
    default_llm_model: str = "gpt-4o"   # 4o for better instruction following
    max_retries: int = 3
    retry_delay_seconds: float = 2.0

    class Config:
        env_file = ".env"
        case_sensitive = False


@lru_cache
def get_settings() -> Settings:
    return Settings()
