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
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    openai_model: str = os.getenv("OPENAI_MODEL", "")
    llm_provider: str = os.getenv("LLM_PROVIDER", "gemini").lower()
    gemini_api_key: str = os.getenv("GEMINI_API_KEY", "")
    gemini_model: str = os.getenv("GEMINI_MODEL", "")
    llm_timeout_seconds: float = float(os.getenv("LLM_TIMEOUT_SECONDS", "20"))
    ai_max_tool_calls: int = int(os.getenv("AI_MAX_TOOL_CALLS", "3"))

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
