from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from app.config import get_settings
from app.database import Base, engine
from app.routers import ai, auth, enterprise, institutions, jobs, platform, public, recruiters, students

settings = get_settings()
settings.validate_for_startup()
if settings.auto_create_schema:
    Base.metadata.create_all(bind=engine)
if not settings.uses_database_file_storage:
    settings.upload_dir.mkdir(parents=True, exist_ok=True)

app = FastAPI(
    title=f"{settings.app_name} API",
    description="AI-assisted campus placement operating system for students, recruiters, and institution teams.",
    version="3.1.3",
    docs_url="/docs" if not settings.is_production else "/api/docs",
    redoc_url=None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)


@app.middleware("http")
async def security_headers(request: Request, call_next):
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


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    if settings.is_production:
        return JSONResponse(status_code=500, content={"detail": "Unexpected server error"})
    raise exc


app.include_router(auth.router)
app.include_router(students.router)
app.include_router(recruiters.router)
app.include_router(jobs.router)
app.include_router(ai.router)
app.include_router(institutions.router)
app.include_router(platform.router)
app.include_router(public.router)
app.include_router(enterprise.router)

STATIC_DIR = Path(__file__).resolve().parent / "static"
TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/", include_in_schema=False)
def root():
    return FileResponse(TEMPLATE_DIR / "index.html")


@app.get("/health", tags=["System"])
def health_check():
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        database = "ok"
    except Exception:
        database = "degraded"
    return {"status": "healthy" if database == "ok" else "degraded", "service": settings.app_name, "version": "3.1.3", "database": database}
