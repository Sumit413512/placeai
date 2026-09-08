from __future__ import annotations

from functools import lru_cache
from pathlib import Path
import os

from dotenv import load_dotenv

load_dotenv()


class Settings:
    def __init__(self) -> None:
        self.app_name = os.getenv("APP_NAME", "PlaceAI")
        self.environment = os.getenv("ENVIRONMENT", "development").lower()
        self.running_on_vercel = bool(os.getenv("VERCEL"))
        default_database_url = "sqlite:////tmp/placeai.db" if self.running_on_vercel else "sqlite:///./placeai.db"
        self.database_url = os.getenv("DATABASE_URL", default_database_url)
        self.jwt_secret_key = os.getenv("JWT_SECRET_KEY", "dev-access-secret-change-me")
        self.jwt_refresh_secret_key = os.getenv("JWT_REFRESH_SECRET_KEY", "dev-refresh-secret-change-me")
        self.access_token_minutes = int(os.getenv("ACCESS_TOKEN_MINUTES", "30"))
        self.refresh_token_days = int(os.getenv("REFRESH_TOKEN_DAYS", "14"))
        self.allowed_origins = [x.strip() for x in os.getenv("ALLOWED_ORIGINS", "http://localhost:8000").split(",") if x.strip()]
        default_upload_dir = "/tmp/placeai/uploads/resumes" if self.running_on_vercel else "uploads/resumes"
        self.upload_dir = Path(os.getenv("UPLOAD_DIR", default_upload_dir))
        self.max_resume_mb = int(os.getenv("MAX_RESUME_MB", "5"))
        self.public_recruiter_signup = os.getenv("PUBLIC_RECRUITER_SIGNUP", "false").lower() == "true"
        self.allow_talent_pool_search = os.getenv("ALLOW_TALENT_POOL_SEARCH", "false").lower() == "true"
        self.enable_ai_demo_fallback = os.getenv("ENABLE_AI_DEMO_FALLBACK", "false").lower() == "true"
        self.google_client_id = os.getenv("GOOGLE_CLIENT_ID", "")
        self.gemini_api_key = os.getenv("GEMINI_API_KEY", "")
        self.gemini_model = os.getenv("GEMINI_MODEL", "gemini-3.8-flash").strip() or "gemini-3.8-flash"
        self.base_url = os.getenv("BASE_URL", "http://localhost:8000").rstrip("/")
        self.dev_show_reset_token = os.getenv("DEV_SHOW_RESET_TOKEN", "false").lower() == "true"
        self.smtp_host = os.getenv("SMTP_HOST", "")
        self.smtp_port = int(os.getenv("SMTP_PORT", "587"))
        self.smtp_user = os.getenv("SMTP_USER", "")
        self.smtp_password = os.getenv("SMTP_PASSWORD", "")
        self.smtp_from = os.getenv("SMTP_FROM", "")
        self.smtp_tls = os.getenv("SMTP_TLS", "true").lower() == "true"
        default_auto_schema = "false" if self.is_production else "true"
        self.auto_create_schema = os.getenv("AUTO_CREATE_SCHEMA", default_auto_schema).lower() == "true"

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    def validate_for_startup(self) -> None:
        if self.environment not in {"development", "test", "production"}:
            raise RuntimeError("ENVIRONMENT must be development, test, or production.")
        if self.is_production:
            weak = {"dev-access-secret-change-me", "dev-refresh-secret-change-me", "super-secret-jwt-key-change-in-production-32chars"}
            if self.jwt_secret_key in weak or len(self.jwt_secret_key) < 32:
                raise RuntimeError("JWT_SECRET_KEY must be a strong production secret (32+ chars).")
            if self.jwt_refresh_secret_key in weak or len(self.jwt_refresh_secret_key) < 32:
                raise RuntimeError("JWT_REFRESH_SECRET_KEY must be a strong production secret (32+ chars).")
            if self.jwt_secret_key == self.jwt_refresh_secret_key:
                raise RuntimeError("JWT access and refresh secrets must be different.")
            if self.database_url.startswith("sqlite") or not self.database_url.startswith(("postgresql://", "postgresql+psycopg://")):
                raise RuntimeError("Production requires a persistent PostgreSQL DATABASE_URL; SQLite is development-only.")
            if self.auto_create_schema:
                raise RuntimeError("AUTO_CREATE_SCHEMA must be false in production; use reviewed migrations instead.")
            if not self.base_url.startswith("https://"):
                raise RuntimeError("BASE_URL must be an HTTPS URL in production.")
            if "*" in self.allowed_origins:
                raise RuntimeError("Wildcard CORS origins are not allowed with production credentials.")
            if any(not origin.startswith("https://") for origin in self.allowed_origins):
                raise RuntimeError("All production ALLOWED_ORIGINS must use HTTPS.")
            if self.dev_show_reset_token:
                raise RuntimeError("DEV_SHOW_RESET_TOKEN must be false in production.")


@lru_cache
def get_settings() -> Settings:
    return Settings()
