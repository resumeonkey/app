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

    # Daily digest email — Resend (resend.com)
    resend_api_key: str = ""
    digest_recipient_email: str = "faleuy@gmail.com"
    digest_from_email: str = "Resumonkey Digest <digest@resumonkey.dev>"
    digest_api_key: str = ""          # Secret for protecting /api/digest/run
    llm_fallback_exclude: str = ""    # comma-separated providers never used as fallback, e.g. "anthropic"

    # Digest lists — editable via environment variables (e.g. CHILE_MIN_SALARY_CLP)
    digest_max_per_list: int = 5
    digest_max_age_days: int = 21
    digest_max_llm_jobs_per_list: int = 60
    digest_title_keywords: str = ("implementation,onboarding,solutions,qa,quality,tester,support,analyst,product owner,functional,"
                                  "implementación,funcional,analista,consultor,soporte,calidad,product manager,customer success")
    chile_min_salary_clp: int = 2_000_000      # net monthly; published below this is discarded
    chile_good_salary_clp: int = 2_500_000     # net monthly; published at/above this scores +2
    remote_min_usd: int = 2_500                # monthly; published below this is discarded
    remote_good_usd: int = 3_500               # monthly; published at/above this scores +2
    usd_clp_rate: int = 950
    # Fixed conversion rates to USD for the remote pay rubric (the code converts, not the LLM). Editable by env var.
    cad_usd_rate: float = 0.72
    eur_usd_rate: float = 1.08
    gbp_usd_rate: float = 1.27
    digest_min_fit: int = 2                    # offers whose role fit is below this (0-4) never reach the lists
    gross_to_net_factor: float = 0.8           # used only when a Chilean salary is stated as gross (bruto)

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
