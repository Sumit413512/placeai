from __future__ import annotations

from contextlib import asynccontextmanager
import importlib
import logging
from pathlib import Path

from fastapi import APIRouter, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlalchemy.exc import DataError, IntegrityError, SQLAlchemyError

from app.config import get_settings
from app.database import (
    Base,
    classify_database_exception,
    engine,
    engine_initialization_error_code,
    safe_database_target,
)
from app.email_delivery import transactional_email_configured
from app.embedded_pages import (
    ACCEPTABLE_USE_HTML,
    INDEX_HTML,
    MOCK_INTERVIEW_HTML,
    PRIVACY_HTML,
    TERMS_HTML,
)

logger = logging.getLogger("placeai")
settings = get_settings()
runtime_readiness_errors = settings.configuration_error_codes()
_router_import_failures: dict[str, str] = {}
if engine_initialization_error_code and engine_initialization_error_code not in runtime_readiness_errors:
    runtime_readiness_errors.append(engine_initialization_error_code)


@asynccontextmanager
async def lifespan(_: FastAPI):
    if runtime_readiness_errors:
        for code in runtime_readiness_errors:
            logger.error("PlaceAI runtime readiness blocked: %s", code)
    else:
        if settings.auto_create_schema:
            Base.metadata.create_all(bind=engine)
        if not settings.uses_database_file_storage:
            settings.upload_dir.mkdir(parents=True, exist_ok=True)
    if settings.is_production and not transactional_email_configured(settings):
        logger.error(
            "PlaceAI transactional email is not configured: password recovery and operational alerts are unavailable"
        )
    yield


app = FastAPI(
    title=f"{settings.app_name} API",
    description="AI-assisted campus placement operating system for students, recruiters, and institution teams.",
    version="3.1.4",
    docs_url=None if settings.is_production else "/docs",
    openapi_url=None if settings.is_production else "/openapi.json",
    redoc_url=None,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)


_DIAGNOSTIC_PATHS = {
    "/",
    "/health",
    "/favicon.ico",
    "/privacy",
    "/terms",
    "/acceptable-use",
    "/robots.txt",
    "/sitemap.xml",
}


@app.middleware("http")
async def security_headers(request: Request, call_next):
    path = request.url.path
    reset_email_unavailable = (
        settings.is_production
        and request.method == "POST"
        and path == "/auth/forgot-password"
        and not transactional_email_configured(settings)
    )
    if reset_email_unavailable:
        response = JSONResponse(
            status_code=503,
            content={
                "detail": "Password reset email is temporarily unavailable. Please try again later or contact support.",
                "code": "PASSWORD_RESET_EMAIL_UNAVAILABLE",
            },
        )
    elif runtime_readiness_errors and path not in _DIAGNOSTIC_PATHS and not path.startswith("/static/"):
        response = JSONResponse(
            status_code=503,
            content={
                "detail": "PlaceAI backend is not ready for authenticated traffic.",
                "code": "SERVICE_CONFIGURATION_ERROR",
            },
        )
    else:
        response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self'; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "font-src 'self' https://fonts.gstatic.com; "
        "img-src 'self' data: https:; "
        "connect-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'; form-action 'self'"
    )
    if path == "/health" or path.startswith("/auth/") or path in {
        "/", "/privacy", "/terms", "/acceptable-use"
    }:
        response.headers["Cache-Control"] = "no-store"
        response.headers["Pragma"] = "no-cache"
    if settings.is_production:
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response


@app.exception_handler(DataError)
async def database_data_error_handler(request: Request, exc: DataError):
    logger.warning("Database rejected invalid input on %s", request.url.path)
    return JSONResponse(
        status_code=422,
        content={"detail": "One or more input values are invalid or too large.", "code": "INVALID_INPUT"},
    )


@app.exception_handler(IntegrityError)
async def database_integrity_error_handler(request: Request, exc: IntegrityError):
    logger.warning("Database integrity conflict on %s", request.url.path)
    return JSONResponse(
        status_code=409,
        content={"detail": "The requested change conflicts with existing data.", "code": "DATA_CONFLICT"},
    )


@app.exception_handler(SQLAlchemyError)
async def database_exception_handler(request: Request, exc: SQLAlchemyError):
    logger.exception("Database operation failed on %s", request.url.path)
    if settings.is_production:
        return JSONResponse(
            status_code=503,
            content={"detail": "Database temporarily unavailable", "code": "DATABASE_UNAVAILABLE"},
        )
    raise exc


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled PlaceAI request failure on %s", request.url.path)
    if settings.is_production:
        return JSONResponse(status_code=500, content={"detail": "Unexpected server error"})
    raise exc


def _import_router(name: str):
    """Import one router without allowing an import-time failure to kill Vercel."""
    try:
        return importlib.import_module(f"app.routers.{name}")
    except Exception as exc:
        code = f"ROUTER_IMPORT_{name.upper()}_FAILED"
        _router_import_failures[name] = f"{type(exc).__name__}: {exc}"
        logger.exception("PlaceAI router bootstrap failed: %s", name)
        if code not in runtime_readiness_errors:
            runtime_readiness_errors.append(code)
        return None


def _route_is_excluded(route, exclusions: set[tuple[str, str]]) -> bool:
    path = getattr(route, "path", "")
    methods = getattr(route, "methods", set()) or set()
    return any((path, method) in exclusions for method in methods)


def _include_router(module, exclusions: set[tuple[str, str]] | None = None) -> None:
    """Include a router without mutating its canonical module-level route registry."""
    if module is None or getattr(module, "router", None) is None:
        return
    if not exclusions:
        app.include_router(module.router)
        return
    filtered = APIRouter()
    filtered.routes.extend(
        route for route in module.router.routes if not _route_is_excluded(route, exclusions)
    )
    app.include_router(filtered)


auth = _import_router("auth")
account_security = _import_router("account_security")
account_security_secure = _import_router("account_security_secure")
access = _import_router("access")
students = _import_router("students")
recruiters = _import_router("recruiters")
jobs = _import_router("jobs")
jobs_secure = _import_router("jobs_secure")
interview_compat = _import_router("interview_compat")
ai = _import_router("ai")
ai_experience = _import_router("ai_experience")
mock_interview = _import_router("mock_interview")
mock_interview_v2 = _import_router("mock_interview_v2")
institutions = _import_router("institutions")
institution_secure = _import_router("institution_secure")
institution_access = _import_router("institution_access")
platform = _import_router("platform")
enterprise = _import_router("enterprise")
enterprise_secure = _import_router("enterprise_secure")
student_workspace_v2 = _import_router("student_workspace_v2")
telemetry = _import_router("telemetry")

ACCOUNT_SECURITY_REPLACEMENTS = {
    ("/auth/change-password", "POST"),
}
JOB_REPLACEMENTS = {
    ("/jobs", "GET"),
    ("/jobs/{job_id}", "GET"),
}
AI_REPLACEMENTS = {
    ("/ai/parse-resume", "POST"),
    ("/ai/generate-summary", "POST"),
}
MOCK_INTERVIEW_REPLACEMENTS = {
    ("/mock-interview/start", "POST"),
    ("/mock-interview/evaluate", "POST"),
}
INSTITUTION_REPLACEMENTS = {
    ("/institutions/dashboard", "GET"),
    ("/institutions/jobs/{job_id}/approval", "PATCH"),
    ("/institutions/drives", "POST"),
    ("/institutions/drives/{drive_id}", "PUT"),
    ("/institutions/applications", "GET"),
}
ENTERPRISE_REPLACEMENTS = {
    ("/enterprise/drives", "GET"),
    ("/enterprise/drives/{drive_id}/pipeline", "GET"),
    ("/enterprise/drives/{drive_id}/eligibility", "GET"),
    ("/enterprise/communications", "GET"),
    ("/enterprise/attendance/sessions", "GET"),
    ("/enterprise/attendance/check-in", "POST"),
    ("/enterprise/search", "GET"),
    ("/enterprise/calendar", "GET"),
    ("/enterprise/announcements", "GET"),
    ("/enterprise/custom-fields", "GET"),
}
ENTERPRISE_SECURE_EXCLUSIONS = {
    ("/enterprise/announcements", "GET"),
    ("/enterprise/calendar", "GET"),
}

_include_router(auth)
_include_router(account_security, ACCOUNT_SECURITY_REPLACEMENTS)
_include_router(account_security_secure)
_include_router(access)
_include_router(students)
_include_router(recruiters)
_include_router(jobs, JOB_REPLACEMENTS)
_include_router(jobs_secure)
_include_router(interview_compat)
_include_router(ai, AI_REPLACEMENTS)
_include_router(ai_experience)
_include_router(mock_interview, MOCK_INTERVIEW_REPLACEMENTS)
_include_router(mock_interview_v2)
_include_router(institutions, INSTITUTION_REPLACEMENTS)
_include_router(institution_secure)
_include_router(institution_access)
_include_router(platform)
_include_router(enterprise, ENTERPRISE_REPLACEMENTS)
_include_router(enterprise_secure, ENTERPRISE_SECURE_EXCLUSIONS)
_include_router(student_workspace_v2)
_include_router(telemetry)

STATIC_DIR = Path(__file__).resolve().parent / "static"
TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


def _public_base(request: Request) -> str:
    if settings.is_production and settings.base_url:
        return settings.base_url.rstrip("/")
    return str(request.base_url).rstrip("/")


def _template_html(name: str, fallback: str) -> str:
    """Read the editable template, with an imported fallback for serverless bundles."""
    try:
        return (TEMPLATE_DIR / name).read_text(encoding="utf-8")
    except OSError as exc:
        logger.warning("Using embedded PlaceAI page for %s: %s", name, type(exc).__name__)
        return fallback


@app.get("/", include_in_schema=False)
def root():
    """Serve the production workspace shell with the role-aware access layer."""
    html = _template_html("index.html", INDEX_HTML)
    assets = (
        '<link rel="stylesheet" href="/static/api-errors.css">\n'
        '<link rel="stylesheet" href="/static/access-portal.css">\n'
        '<link rel="stylesheet" href="/static/ui-fixes.css">\n'
        '<link rel="stylesheet" href="/static/account-security.css">\n'
        '<script src="/static/workspace-runtime.js" defer></script>\n'
        '<script src="/static/api-errors.js" defer></script>\n'
        '<script src="/static/access-portal.js" defer></script>\n'
        '<script src="/static/ui-state-fixes.js" defer></script>\n'
        '<script src="/static/account-security.js" defer></script>\n'
        '<script src="/static/provisioning-password-fix.js" defer></script>\n'
        '<script src="/static/release-ux-fixes.js" defer></script>\n'
        '<script src="/static/integration-readiness.js" defer></script>\n'
        '<script src="/static/ai-readiness.js" defer></script>\n'
        '<script src="/static/legal-links.js" defer></script>\n'
    )
    if "/static/access-portal.js" not in html:
        html = html.replace("</head>", f"{assets}</head>", 1)
    return HTMLResponse(html)


@app.get("/favicon.ico", include_in_schema=False)
def favicon() -> Response:
    svg = (STATIC_DIR / "placeai-icon.svg").read_text(encoding="utf-8")
    return Response(
        content=svg,
        media_type="image/svg+xml",
        headers={"Cache-Control": "public, max-age=86400"},
    )


@app.get("/mock-interview", include_in_schema=False)
def mock_interview_page() -> HTMLResponse:
    return HTMLResponse(_template_html("mock-interview.html", MOCK_INTERVIEW_HTML))


@app.api_route("/privacy", methods=["GET", "HEAD"], include_in_schema=False)
def privacy_page() -> HTMLResponse:
    return HTMLResponse(_template_html("privacy.html", PRIVACY_HTML))


@app.api_route("/terms", methods=["GET", "HEAD"], include_in_schema=False)
def terms_page() -> HTMLResponse:
    return HTMLResponse(_template_html("terms.html", TERMS_HTML))


@app.api_route("/acceptable-use", methods=["GET", "HEAD"], include_in_schema=False)
def acceptable_use_page() -> HTMLResponse:
    return HTMLResponse(_template_html("acceptable-use.html", ACCEPTABLE_USE_HTML))


@app.get("/robots.txt", include_in_schema=False)
def robots(request: Request) -> Response:
    body = f"User-agent: *\nAllow: /\nSitemap: {_public_base(request)}/sitemap.xml\n"
    return Response(content=body, media_type="text/plain")


@app.get("/sitemap.xml", include_in_schema=False)
def sitemap(request: Request) -> Response:
    base = _public_base(request)
    urls = ["/", "/privacy", "/terms", "/acceptable-use"]
    body = '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
    body += "\n".join(f"  <url><loc>{base}{path}</loc></url>" for path in urls)
    body += "\n</urlset>\n"
    return Response(content=body, media_type="application/xml")


@app.get("/health", tags=["System"])
def health_check():
    service_name = settings.app_name or "PlaceAI"
    if runtime_readiness_errors:
        return JSONResponse(
            status_code=503,
            content={
                "status": "degraded",
                "service": service_name,
                "version": "3.1.4",
                "database": "not_checked",
                "configuration": "invalid",
                "configuration_errors": runtime_readiness_errors,
            },
        )

    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        database = "ok"
        database_error = None
    except Exception as exc:
        logger.exception("PlaceAI health database probe failed")
        database = "degraded"
        database_error = classify_database_exception(exc)

    payload = {
        "status": "healthy" if database == "ok" else "degraded",
        "service": service_name,
        "version": "3.1.4",
        "database": database,
        "configuration": "ok",
        "transactional_email": "ok" if transactional_email_configured(settings) else "not_configured",
    }
    if not settings.is_production:
        payload["database_target"] = safe_database_target(settings.database_url)
    if database_error:
        payload["database_error"] = database_error
    if database != "ok":
        return JSONResponse(status_code=503, content=payload)
    return payload
