import os
from dataclasses import dataclass
from urllib.parse import quote_plus

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    app_env: str = os.getenv("APP_ENV", "development")
    database_url: str = os.getenv("DATABASE_URL", "")
    postgres_user: str = os.getenv("POSTGRES_USER", "")
    postgres_password: str = os.getenv("POSTGRES_PASSWORD", "")
    postgres_host: str = os.getenv("POSTGRES_HOST", "")
    postgres_port: int = int(os.getenv("POSTGRES_PORT", "5432"))
    postgres_db: str = os.getenv("POSTGRES_DB", "postgres")
    supabase_url: str = os.getenv("SUPABASE_URL", "").rstrip("/")
    supabase_jwt_audience: str = os.getenv("SUPABASE_JWT_AUDIENCE", "authenticated")
    supabase_jwt_secret: str = os.getenv("SUPABASE_JWT_SECRET", "")
    admin_emails: str = os.getenv("ADMIN_EMAILS", "")
    admin_user_ids: str = os.getenv("ADMIN_USER_IDS", "")
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    openai_model: str = os.getenv("OPENAI_MODEL", "")
    llm_provider: str = os.getenv("LLM_PROVIDER", "gemini").lower()
    gemini_api_key: str = os.getenv("GEMINI_API_KEY", "")
    gemini_model: str = os.getenv("GEMINI_MODEL", "")
    llm_timeout_seconds: float = float(os.getenv("LLM_TIMEOUT_SECONDS", "60"))
    # Servidor propio: vLLM/Ollama exponen la API de OpenAI en esta dirección (p. ej. http://vllm:8000/v1).
    openai_base_url: str = os.getenv("OPENAI_BASE_URL", "").strip()
    # El agente sigue en Gemini salvo que se pida otro proveedor (openai = OpenAI o vLLM con OPENAI_BASE_URL).
    agent_llm_provider: str = os.getenv("AGENT_LLM_PROVIDER", "gemini").strip().lower()
    # Proveedor de respaldo cuando la GPU propia está llena o caída (vacío = sin respaldo).
    llm_fallback_provider: str = os.getenv("LLM_FALLBACK_PROVIDER", "").strip().lower()
    # Consultas de IA a la vez por proceso de la API (0 = sin tope) y cuánto espera una consulta por un cupo.
    ai_max_concurrent: int = int(os.getenv("AI_MAX_CONCURRENT", "8"))
    ai_queue_timeout_seconds: float = float(os.getenv("AI_QUEUE_TIMEOUT_SECONDS", "8"))
    # Límites por usuario o IP (0 = sin límite).
    ai_rate_limit_per_hour: int = int(os.getenv("AI_RATE_LIMIT_PER_HOUR", "30"))
    # Por IP: apagado por defecto, porque detrás del proxy de Next.js todos llegan con la misma IP.
    # Se activa (p. ej. 120) solo donde la IP real llega a la API (Caddy + uvicorn --proxy-headers).
    catalog_rate_limit_per_minute: int = int(os.getenv("CATALOG_RATE_LIMIT_PER_MINUTE", "0"))
    # Caché del catálogo: Redis si hay REDIS_URL; si no, memoria del proceso (0 = sin caché).
    redis_url: str = os.getenv("REDIS_URL", "").strip()
    catalog_cache_ttl_seconds: int = int(os.getenv("CATALOG_CACHE_TTL_SECONDS", "300"))
    # Conexiones a PostgreSQL por proceso: con 8 procesos x (5 + 5) = 80, bajo el máximo de 100.
    db_pool_size: int = int(os.getenv("DB_POOL_SIZE", "5"))
    db_max_overflow: int = int(os.getenv("DB_MAX_OVERFLOW", "5"))
    # Crear tablas al arrancar solo en desarrollo; en producción manda Alembic.
    db_create_all: bool = os.getenv("DB_CREATE_ALL", "true").strip().lower() in {"1", "true", "yes", "on"}
    ai_max_tool_calls: int = int(os.getenv("AI_MAX_TOOL_CALLS", "3"))
    research_enabled: bool = os.getenv("RESEARCH_ENABLED", "true").strip().lower() in {"1", "true", "yes", "on"}
    # Hard ceilings for any research pass (depth budgets stay below these).
    max_research_queries: int = int(os.getenv("MAX_RESEARCH_QUERIES", "5"))
    max_research_sources: int = int(os.getenv("MAX_RESEARCH_SOURCES", "6"))
    max_research_documents: int = int(os.getenv("MAX_RESEARCH_DOCUMENTS", "4"))
    max_research_chunks: int = int(os.getenv("MAX_RESEARCH_CHUNKS", "24"))
    max_research_chars: int = int(os.getenv("MAX_RESEARCH_CHARS", "6000"))
    research_timeout_seconds: float = float(os.getenv("RESEARCH_TIMEOUT_SECONDS", "10"))
    research_cache_ttl_seconds: int = int(os.getenv("RESEARCH_CACHE_TTL_SECONDS", "1800"))
    # Per-depth budgets (configurable; research is never unlimited).
    research_light_max_queries: int = int(os.getenv("RESEARCH_LIGHT_MAX_QUERIES", "2"))
    research_light_max_sources: int = int(os.getenv("RESEARCH_LIGHT_MAX_SOURCES", "3"))
    research_light_max_documents: int = int(os.getenv("RESEARCH_LIGHT_MAX_DOCUMENTS", "2"))
    research_deep_max_queries: int = int(os.getenv("RESEARCH_DEEP_MAX_QUERIES", "4"))
    research_deep_max_sources: int = int(os.getenv("RESEARCH_DEEP_MAX_SOURCES", "6"))
    research_deep_max_documents: int = int(os.getenv("RESEARCH_DEEP_MAX_DOCUMENTS", "3"))
    # Freshness-aware cache: short TTL for volatile data, long for stable specs.
    research_cache_price_ttl_seconds: int = int(os.getenv("RESEARCH_CACHE_PRICE_TTL_SECONDS", "300"))
    research_cache_spec_ttl_seconds: int = int(os.getenv("RESEARCH_CACHE_SPEC_TTL_SECONDS", "86400"))
    research_cache_benchmark_ttl_seconds: int = int(os.getenv("RESEARCH_CACHE_BENCHMARK_TTL_SECONDS", "3600"))
    research_cache_review_ttl_seconds: int = int(os.getenv("RESEARCH_CACHE_REVIEW_TTL_SECONDS", "7200"))
    embedding_provider: str = os.getenv("EMBEDDING_PROVIDER", "local").lower()
    embedding_model: str = os.getenv("EMBEDDING_MODEL", "")
    embedding_dimensions: int = int(os.getenv("EMBEDDING_DIMENSIONS", "256"))
    embedding_use_pgvector: bool = os.getenv("EMBEDDING_USE_PGVECTOR", "false").strip().lower() in {"1", "true", "yes", "on"}
    rag_enabled: bool = os.getenv("RAG_ENABLED", "true").strip().lower() in {"1", "true", "yes", "on"}
    rag_hybrid_top_k: int = int(os.getenv("RAG_HYBRID_TOP_K", "6"))
    rag_rerank_weights: str = os.getenv("RAG_RERANK_WEIGHTS", "")
    rag_token_budget: int = int(os.getenv("RAG_TOKEN_BUDGET", "1600"))

    @property
    def sqlalchemy_database_url(self) -> str:
        """Return an explicit URL or build the Supabase PostgreSQL connection URL."""
        if self.database_url:
            # Supabase's connection dialog commonly provides ``postgresql://``.
            # Select the project's installed psycopg v3 dialect explicitly instead
            # of making SQLAlchemy fall back to the unavailable psycopg2 driver.
            if self.database_url.startswith("postgresql://"):
                return self.database_url.replace("postgresql://", "postgresql+psycopg://", 1)
            return self.database_url
        if all((self.postgres_user, self.postgres_password, self.postgres_host)):
            password = quote_plus(self.postgres_password)
            return f"postgresql+psycopg://{self.postgres_user}:{password}@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        # Allows local tests and first-run development without fabricating Supabase credentials.
        return "sqlite:///./solotodo.db"


settings = Settings()
