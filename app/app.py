from __future__ import annotations

from contextlib import asynccontextmanager
import importlib
import logging
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.config import get_settings
from app.database import (
    Base,
    classify_database_exception,
    engine,
    engine_initialization_error_code,
    safe_database_target,
)
from app.email_delivery import transactional_email_configured

logger = logging.getLogger("placeai")
settings = get_settings()
runtime_readiness_errors = settings.configuration_error_codes()
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
    version="3.1.3",
    docs_url="/docs" if not settings.is_production else "/api/docs",
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


_DIAGNOSTIC_PATHS = {"/", "/health"}


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
    if settings.is_production:
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response


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
    except Exception:
        code = f"ROUTER_IMPORT_{name.upper()}_FAILED"
        logger.exception("PlaceAI router bootstrap failed: %s", name)
        if code not in runtime_readiness_errors:
            runtime_readiness_errors.append(code)
        return None


def _include_router(module) -> None:
    if module is not None and getattr(module, "router", None) is not None:
        app.include_router(module.router)


auth = _import_router("auth")
account_security = _import_router("account_security")
access = _import_router("access")
students = _import_router("students")
recruiters = _import_router("recruiters")
jobs = _import_router("jobs")
interview_compat = _import_router("interview_compat")
ai = _import_router("ai")
mock_interview = _import_router("mock_interview")
institutions = _import_router("institutions")
platform = _import_router("platform")
report_export_safe = _import_router("report_export_safe")
enterprise = _import_router("enterprise")
hardening = _import_router("hardening")
hardening2 = _import_router("hardening2")

if ai is not None:
    _RETIRED_AI_PATHS = {
        "/ai/interview/questions",
        "/ai/interview/evaluate",
        "/ai/interviews",
        "/ai/interviews/{interview_id}",
        "/ai/rank-candidates/{job_id}",
    }
    ai.router.routes = [
        route for route in ai.router.routes
        if getattr(route, "path", "") not in _RETIRED_AI_PATHS
    ]
if institutions is not None:
    _HARDENED_INSTITUTION_PATHS = {
        "/institutions/dashboard",
        "/institutions/jobs/{job_id}/approval",
    }
    institutions.router.routes = [
        route for route in institutions.router.routes
        if getattr(route, "path", "") not in _HARDENED_INSTITUTION_PATHS
    ]

if enterprise is not None:
    def _retired_enterprise_route(route) -> bool:
        path = getattr(route, "path", "")
        methods = set(getattr(route, "methods", set()) or set())
        if path in {
            "/enterprise/reports/{kind}.{fmt}",
            "/enterprise/announcements",
            "/enterprise/offers/{offer_id}/letter",
        }:
            return True
        return (
            (path == "/enterprise/drives/{drive_id}/pipeline/default" and "POST" in methods)
            or (path == "/enterprise/drives/{drive_id}/pipeline" and "POST" in methods)
            or (path == "/enterprise/offers/{offer_id}" and "PATCH" in methods)
            or (path == "/enterprise/company-verification/authorization-letter" and "POST" in methods)
        )

    enterprise.router.routes = [
        route for route in enterprise.router.routes
        if not _retired_enterprise_route(route)
    ]

for module in (
    auth,
    account_security,
    access,
    students,
    recruiters,
    jobs,
    interview_compat,
    ai,
    mock_interview,
    institutions,
    platform,
    report_export_safe,
    enterprise,
    hardening,
    hardening2,
):
    _include_router(module)

STATIC_DIR = Path(__file__).resolve().parent / "static"
TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/", include_in_schema=False)
def root():
    """Serve the production workspace shell with the role-aware access layer."""
    html = (TEMPLATE_DIR / "index.html").read_text(encoding="utf-8")
    assets = (
        '<link rel="stylesheet" href="/static/api-errors.css">\n'
        '<link rel="stylesheet" href="/static/access-portal.css">\n'
        '<link rel="stylesheet" href="/static/ui-fixes.css">\n'
        '<link rel="stylesheet" href="/static/account-security.css">\n'
        '<script src="/static/api-errors.js" defer></script>\n'
        '<script src="/static/access-portal.js" defer></script>\n'
        '<script src="/static/ui-state-fixes.js" defer></script>\n'
        '<script src="/static/account-security.js" defer></script>\n'
    )
    if "/static/access-portal.js" not in html:
        html = html.replace("</head>", f"{assets}</head>", 1)
    return HTMLResponse(html)


@app.get("/mock-interview", include_in_schema=False)
def mock_interview_page():
    return FileResponse(TEMPLATE_DIR / "mock-interview.html")


@app.get("/health", tags=["System"])
def health_check():
    service_name = settings.app_name or "PlaceAI"
    if runtime_readiness_errors:
        return JSONResponse(
            status_code=503,
            content={
                "status": "degraded",
                "service": service_name,
                "version": "3.1.3",
                "database": "not_checked",
                "configuration": "invalid",
                "configuration_errors": runtime_readiness_errors,
            },
        )

    target = safe_database_target(settings.database_url)
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
        "version": "3.1.3",
        "database": database,
        "configuration": "ok",
        "database_target": target,
        "transactional_email": "ok" if transactional_email_configured(settings) else "not_configured",
    }
    if database_error:
        payload["database_error"] = database_error
    if database != "ok":
        return JSONResponse(status_code=503, content=payload)
    return payload
