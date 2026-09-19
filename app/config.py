from __future__ import annotations

from functools import lru_cache
from pathlib import Path
import os
import tempfile
from urllib.parse import urlparse

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


def _is_vercel_platform_url(value: str | None) -> bool:
    """Return True for Vercel-owned deployment hostnames, not custom domains."""
    raw = (value or "").strip()
    if not raw:
        return False
    # urlparse treats a schemeless hostname as a path, so normalize it first.
    candidate = raw if "://" in raw else f"https://{raw.lstrip('/')}"
    try:
        host = (urlparse(candidate).hostname or "").lower().rstrip(".")
    except ValueError:
        return False
    return host == "vercel.app" or host.endswith(".vercel.app")


def _bounded_env_int(name: str, default: int, minimum: int, maximum: int) -> int:
    """Parse an integer environment variable without allowing bootstrap crashes.

    Vercel environment variables are user-controlled strings. A stale placeholder such as
    ``ACCESS_TOKEN_MINUTES=replace-me`` must not terminate the Python worker before FastAPI
    can expose readiness. Invalid/out-of-range values fall back to conservative defaults.
    """
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        value = int(raw.strip())
    except (TypeError, ValueError):
        return default
    if value < minimum or value > maximum:
        return default
    return value


def _first_env(*names: str) -> str:
    """Return the first non-empty environment value from a list of compatible aliases."""
    for name in names:
        value = os.getenv(name, "").strip()
        if value:
            return value
    return ""


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
            default_environment = "production"
        self.environment = os.getenv("ENVIRONMENT", default_environment).lower()

        if self.running_on_vercel:
            temp_database_path = Path(tempfile.gettempdir()) / "placeai.db"
            default_database_url = f"sqlite:///{temp_database_path}"
        else:
            default_database_url = "sqlite:///./placeai.db"
        database_url = os.getenv("DATABASE_URL", default_database_url).strip()
        if database_url.startswith("postgresql://"):
            database_url = "postgresql+psycopg://" + database_url[len("postgresql://") :]
        self.database_url = database_url

        self.jwt_secret_key = os.getenv("JWT_SECRET_KEY", "dev-access-secret-change-me")
        self.jwt_refresh_secret_key = os.getenv("JWT_REFRESH_SECRET_KEY", "dev-refresh-secret-change-me")
        self.access_token_minutes = _bounded_env_int("ACCESS_TOKEN_MINUTES", 30, 1, 1440)
        self.refresh_token_days = _bounded_env_int("REFRESH_TOKEN_DAYS", 14, 1, 365)

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

        default_backend_url = vercel_default_url or "http://localhost:8000"
        self.backend_base_url = os.getenv("BASE_URL", default_backend_url).rstrip("/")

        # External links sent to users must point at the stable public application.
        # PlaceAI's production canonical domain is provider-independent. A Vercel
        # platform hostname is a deployment origin, never a public canonical URL,
        # even if runtime provider flags are absent or stale.
        default_public_app_url = "https://www.placeai.in" if self.is_production else self.backend_base_url
        canonical_public_url = _first_env("PLACEAI_CANONICAL_PUBLIC_URL").rstrip("/")
        legacy_public_url = _first_env("PUBLIC_APP_URL", "PASSWORD_RESET_BASE_URL").rstrip("/")
        if self.is_production:
            if canonical_public_url and _is_vercel_platform_url(canonical_public_url):
                canonical_public_url = ""
            if legacy_public_url and _is_vercel_platform_url(legacy_public_url):
                legacy_public_url = ""
        self.base_url = (canonical_public_url or legacy_public_url or default_public_app_url).rstrip("/")

        default_allowed_origins = self.base_url if self.is_production else (vercel_default_url or "http://localhost:8000")
        configured_origins = [
            x.strip()
            for x in os.getenv("ALLOWED_ORIGINS", default_allowed_origins).split(",")
            if x.strip()
        ]
        self.allowed_origins = list(dict.fromkeys(configured_origins + ([self.base_url] if self.is_production else [])))

        self.upload_dir = Path(os.getenv("UPLOAD_DIR", "uploads/resumes"))
        self.max_resume_mb = _bounded_env_int("MAX_RESUME_MB", 5, 1, 50)
        self.public_recruiter_signup = os.getenv("PUBLIC_RECRUITER_SIGNUP", "false").lower() == "true"
        self.allow_talent_pool_search = os.getenv("ALLOW_TALENT_POOL_SEARCH", "false").lower() == "true"
        self.google_client_id = os.getenv("GOOGLE_CLIENT_ID", "")
        self.openai_api_key = os.getenv("OPENAI_API_KEY", "")
        self.openai_backup_api_key = os.getenv("OPENAI_BACKUP_API_KEY", "")
        self.openai_model = os.getenv("OPENAI_MODEL", "gpt-5.6-terra").strip() or "gpt-5.6-terra"
        self.ai_request_timeout_seconds = _bounded_env_int("AI_REQUEST_TIMEOUT_SECONDS", 45, 5, 120)
        self.ai_max_output_tokens = _bounded_env_int("AI_MAX_OUTPUT_TOKENS", 5000, 512, 12000)
        self.gemini_api_key = os.getenv("GEMINI_API_KEY", "")
        self.gemini_model = os.getenv("GEMINI_MODEL", "gemini-3.8-flash").strip() or "gemini-3.8-flash"
        self.dev_show_reset_token = os.getenv("DEV_SHOW_RESET_TOKEN", "false").lower() == "true"
        self.student_individual_trial_days = _bounded_env_int("STUDENT_INDIVIDUAL_TRIAL_DAYS", 3, 1, 30)
        self.student_individual_monthly_price_inr = _bounded_env_int("STUDENT_INDIVIDUAL_MONTHLY_PRICE_INR", 299, 49, 9999)
        self.student_payment_provider = os.getenv("STUDENT_PAYMENT_PROVIDER", "pending").strip().lower() or "pending"
        self.razorpay_key_id = os.getenv("RAZORPAY_KEY_ID", "").strip()
        self.razorpay_key_secret = os.getenv("RAZORPAY_KEY_SECRET", "").strip()
        self.razorpay_webhook_secret = os.getenv("RAZORPAY_WEBHOOK_SECRET", "").strip()

        brevo_smtp_user = _first_env("BREVO_SMTP_USER", "BREVO_SMTP_LOGIN")
        brevo_smtp_password = _first_env("BREVO_SMTP_PASSWORD", "BREVO_SMTP_KEY")
        self.smtp_user = _first_env("SMTP_USER") or brevo_smtp_user
        self.smtp_password = _first_env("SMTP_PASSWORD") or brevo_smtp_password
        self.smtp_from = _first_env("SMTP_FROM", "BREVO_FROM_EMAIL", "BREVO_SENDER_EMAIL")
        self.smtp_host = _first_env("SMTP_HOST", "BREVO_SMTP_HOST")
        if not self.smtp_host and (brevo_smtp_user or brevo_smtp_password):
            self.smtp_host = "smtp-relay.brevo.com"
        self.smtp_port = _bounded_env_int("SMTP_PORT", 587, 1, 65535)
        self.smtp_tls = os.getenv("SMTP_TLS", "true").lower() == "true"
        self.brevo_api_key = _first_env("BREVO_API_KEY")

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
                issues.append(("BASE_URL_NOT_HTTPS", "The public application URL must use HTTPS in production."))
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
