from __future__ import annotations

from functools import lru_cache
from pathlib import Path
import os
import tempfile

from dotenv import load_dotenv

load_dotenv()


def _https_url_from_vercel_host(value: str | None) -> str:
    """Convert a Vercel hostname system variable into an absolute HTTPS URL."""
    host = (value or "").strip().rstrip("/")
    if not host:
        return ""
    if host.startswith("https://") or host.startswith("http://"):
        return host
    return f"https://{host}"


class Settings:
    def __init__(self) -> None:
        self.app_name = os.getenv("APP_NAME", "PlaceAI")
        self.running_on_vercel = bool(os.getenv("VERCEL"))
        self.vercel_environment = os.getenv("VERCEL_ENV", "").strip().lower()
        if not self.running_on_vercel:
            default_environment = "development"
        elif self.vercel_environment == "preview":
            default_environment = "test"
        elif self.vercel_environment == "development":
            default_environment = "development"
        else:
            # VERCEL_ENV=production is the normal production path. Unknown/missing
            # Vercel environment values deliberately fail closed as production.
            default_environment = "production"
        self.environment = os.getenv("ENVIRONMENT", default_environment).lower()

        if self.running_on_vercel:
            temp_database_path = Path(tempfile.gettempdir()) / "placeai.db"
            default_database_url = f"sqlite:///{temp_database_path}"
        else:
            default_database_url = "sqlite:///./placeai.db"
        database_url = os.getenv("DATABASE_URL", default_database_url).strip()
        # Supabase and most Postgres dashboards emit postgresql:// URLs. PlaceAI
        # ships psycopg3, so normalize the generic scheme to SQLAlchemy's psycopg3
        # dialect instead of accidentally requiring the legacy psycopg2 driver.
        if database_url.startswith("postgresql://"):
            database_url = "postgresql+psycopg://" + database_url[len("postgresql://") :]
        self.database_url = database_url

        self.jwt_secret_key = os.getenv("JWT_SECRET_KEY", "dev-access-secret-change-me")
        self.jwt_refresh_secret_key = os.getenv("JWT_REFRESH_SECRET_KEY", "dev-refresh-secret-change-me")
        self.access_token_minutes = int(os.getenv("ACCESS_TOKEN_MINUTES", "30"))
        self.refresh_token_days = int(os.getenv("REFRESH_TOKEN_DAYS", "14"))

        # Vercel exposes generated/production hostnames as system environment
        # variables. Use them only as non-secret URL defaults; explicit application
        # configuration always wins.
        if self.running_on_vercel:
            if self.vercel_environment == "production":
                vercel_host = (
                    os.getenv("VERCEL_PROJECT_PRODUCTION_URL")
                    or os.getenv("VERCEL_BRANCH_URL")
                    or os.getenv("VERCEL_URL")
                )
            else:
                vercel_host = (
                    os.getenv("VERCEL_BRANCH_URL")
                    or os.getenv("VERCEL_URL")
                    or os.getenv("VERCEL_PROJECT_PRODUCTION_URL")
                )
            vercel_default_url = _https_url_from_vercel_host(vercel_host)
        else:
            vercel_default_url = ""
        default_base_url = vercel_default_url or "http://localhost:8000"
        self.base_url = os.getenv("BASE_URL", default_base_url).rstrip("/")
        default_allowed_origins = vercel_default_url or "http://localhost:8000"
        self.allowed_origins = [
            x.strip()
            for x in os.getenv("ALLOWED_ORIGINS", default_allowed_origins).split(",")
            if x.strip()
        ]

        self.upload_dir = Path(os.getenv("UPLOAD_DIR", "uploads/resumes"))
        self.max_resume_mb = int(os.getenv("MAX_RESUME_MB", "5"))
        self.public_recruiter_signup = os.getenv("PUBLIC_RECRUITER_SIGNUP", "false").lower() == "true"
        self.allow_talent_pool_search = os.getenv("ALLOW_TALENT_POOL_SEARCH", "false").lower() == "true"
        self.enable_ai_demo_fallback = os.getenv("ENABLE_AI_DEMO_FALLBACK", "false").lower() == "true"
        self.google_client_id = os.getenv("GOOGLE_CLIENT_ID", "")
        self.gemini_api_key = os.getenv("GEMINI_API_KEY", "")
        self.gemini_model = os.getenv("GEMINI_MODEL", "gemini-3.8-flash").strip() or "gemini-3.8-flash"
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

    @property
    def uses_database_file_storage(self) -> bool:
        return self.running_on_vercel or self.is_production

    def configuration_issues(self) -> list[tuple[str, str]]:
        """Return safe error codes plus owner-facing messages without secret values."""
        issues: list[tuple[str, str]] = []
        if self.environment not in {"development", "test", "production"}:
            issues.append(("ENVIRONMENT_INVALID", "ENVIRONMENT must be development, test, or production."))
            return issues

        if self.is_production:
            weak = {
                "dev-access-secret-change-me",
                "dev-refresh-secret-change-me",
                "super-secret-jwt-key-change-in-production-32chars",
            }
            if self.jwt_secret_key in weak or len(self.jwt_secret_key) < 32:
                issues.append(("JWT_SECRET_KEY_MISSING_OR_WEAK", "JWT_SECRET_KEY must be a strong production secret (32+ chars)."))
            if self.jwt_refresh_secret_key in weak or len(self.jwt_refresh_secret_key) < 32:
                issues.append(("JWT_REFRESH_SECRET_KEY_MISSING_OR_WEAK", "JWT_REFRESH_SECRET_KEY must be a strong production secret (32+ chars)."))
            if self.jwt_secret_key == self.jwt_refresh_secret_key:
                issues.append(("JWT_SECRETS_NOT_DISTINCT", "JWT access and refresh secrets must be different."))
            if self.database_url.startswith("sqlite") or not self.database_url.startswith("postgresql+psycopg://"):
                issues.append(("DATABASE_URL_NOT_POSTGRESQL", "Production requires a persistent PostgreSQL DATABASE_URL using psycopg3; SQLite is development-only."))
            if self.auto_create_schema:
                issues.append(("AUTO_CREATE_SCHEMA_ENABLED", "AUTO_CREATE_SCHEMA must be false in production; use reviewed migrations instead."))
            if not self.base_url.startswith("https://"):
                issues.append(("BASE_URL_NOT_HTTPS", "BASE_URL must be an HTTPS URL in production."))
            if "*" in self.allowed_origins:
                issues.append(("CORS_WILDCARD_NOT_ALLOWED", "Wildcard CORS origins are not allowed with production credentials."))
            if any(not origin.startswith("https://") for origin in self.allowed_origins):
                issues.append(("CORS_ORIGIN_NOT_HTTPS", "All production ALLOWED_ORIGINS must use HTTPS."))
            if self.dev_show_reset_token:
                issues.append(("DEV_RESET_TOKEN_EXPOSED", "DEV_SHOW_RESET_TOKEN must be false in production."))
        return issues

    def configuration_error_codes(self) -> list[str]:
        return [code for code, _ in self.configuration_issues()]

    def validate_for_startup(self) -> None:
        issues = self.configuration_issues()
        if issues:
            raise RuntimeError(issues[0][1])


@lru_cache
def get_settings() -> Settings:
    return Settings()
