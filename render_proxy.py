from __future__ import annotations

from contextlib import asynccontextmanager
import logging
import os
from pathlib import Path

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

UPSTREAM_BASE = os.getenv("UPSTREAM_BASE", "https://placeai-rxpp.vercel.app").rstrip("/")
ASSET_VERSION = os.getenv("ASSET_VERSION", "20260913-2")
ROOT = Path(__file__).resolve().parent
STATIC_DIR = ROOT / "app" / "static"
TEMPLATE_DIR = ROOT / "app" / "templates"
LOGGER = logging.getLogger("placeai.render_gateway")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Reuse upstream TCP/TLS connections instead of paying a new Vercel handshake for
    # every API request. This materially reduces proxy latency on normal workspace use.
    app.state.upstream_client = httpx.AsyncClient(
        timeout=httpx.Timeout(60.0, connect=8.0, read=60.0, write=30.0, pool=8.0),
        follow_redirects=False,
        limits=httpx.Limits(max_connections=100, max_keepalive_connections=20, keepalive_expiry=30.0),
    )
    try:
        yield
    finally:
        await app.state.upstream_client.aclose()


app = FastAPI(title="PlaceAI Render Gateway", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

ASSET_INJECTION = (
    f'<link rel="stylesheet" href="/static/api-errors.css?v={ASSET_VERSION}">\n'
    f'<link rel="stylesheet" href="/static/access-portal.css?v={ASSET_VERSION}">\n'
    f'<link rel="stylesheet" href="/static/ui-fixes.css?v={ASSET_VERSION}">\n'
    f'<link rel="stylesheet" href="/static/account-security.css?v={ASSET_VERSION}">\n'
    f'<script src="/static/workspace-runtime.js?v={ASSET_VERSION}" defer></script>\n'
    f'<script src="/static/api-errors.js?v={ASSET_VERSION}" defer></script>\n'
    f'<script src="/static/access-portal.js?v={ASSET_VERSION}" defer></script>\n'
    f'<script src="/static/ui-state-fixes.js?v={ASSET_VERSION}" defer></script>\n'
    f'<script src="/static/account-security.js?v={ASSET_VERSION}" defer></script>\n'
    f'<script src="/static/provisioning-password-fix.js?v={ASSET_VERSION}" defer></script>\n'
    f'<script src="/static/release-ux-fixes.js?v={ASSET_VERSION}" defer></script>\n'
    f'<script src="/static/integration-readiness.js?v={ASSET_VERSION}" defer></script>\n'
    f'<script src="/static/ai-readiness.js?v={ASSET_VERSION}" defer></script>\n'
    f'<script src="/static/legal-links.js?v={ASSET_VERSION}" defer></script>\n'
)

HOP_BY_HOP_HEADERS = {
    "connection", "keep-alive", "proxy-authenticate", "proxy-authorization", "te",
    "trailers", "transfer-encoding", "upgrade", "host", "content-length",
}


def _safe_validation_fields(payload: object) -> list[str]:
    if not isinstance(payload, dict):
        return []
    detail = payload.get("detail")
    if not isinstance(detail, list):
        return []
    fields: set[str] = set()
    for item in detail:
        if not isinstance(item, dict):
            continue
        loc = item.get("loc")
        if not isinstance(loc, list):
            continue
        for part in reversed(loc):
            if isinstance(part, str) and part not in {"body", "query", "path", "header"}:
                fields.add(part)
                break
    return sorted(fields)


def _public_base(request: Request) -> str:
    return str(request.base_url).rstrip("/")


@app.middleware("http")
async def recovery_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    response.headers["X-PlaceAI-Gateway"] = "render"
    if request.url.path in {"/", "/mock-interview", "/privacy", "/terms", "/acceptable-use"}:
        response.headers["Cache-Control"] = "no-store"
    elif request.url.path.startswith("/static/"):
        response.headers["Cache-Control"] = "no-cache, must-revalidate"
    response.headers.setdefault(
        "Content-Security-Policy",
        "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "font-src 'self' https://fonts.gstatic.com; img-src 'self' data: https:; connect-src 'self'; "
        "object-src 'none'; base-uri 'self'; frame-ancestors 'none'; form-action 'self'",
    )
    return response


@app.api_route("/", methods=["GET", "HEAD"], include_in_schema=False)
def root() -> HTMLResponse:
    html = (TEMPLATE_DIR / "index.html").read_text(encoding="utf-8")
    if "/static/access-portal.js" not in html:
        html = html.replace("</head>", f"{ASSET_INJECTION}</head>", 1)
    return HTMLResponse(html)


@app.get("/favicon.ico", include_in_schema=False)
def favicon() -> FileResponse:
    return FileResponse(STATIC_DIR / "placeai-icon.svg", media_type="image/svg+xml")


@app.get("/mock-interview", include_in_schema=False)
def mock_interview_page() -> FileResponse:
    return FileResponse(TEMPLATE_DIR / "mock-interview.html")


@app.api_route("/privacy", methods=["GET", "HEAD"], include_in_schema=False)
def privacy_page() -> FileResponse:
    return FileResponse(TEMPLATE_DIR / "privacy.html", media_type="text/html")


@app.api_route("/terms", methods=["GET", "HEAD"], include_in_schema=False)
def terms_page() -> FileResponse:
    return FileResponse(TEMPLATE_DIR / "terms.html", media_type="text/html")


@app.api_route("/acceptable-use", methods=["GET", "HEAD"], include_in_schema=False)
def acceptable_use_page() -> FileResponse:
    return FileResponse(TEMPLATE_DIR / "acceptable-use.html", media_type="text/html")


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


@app.get("/_recovery/health", include_in_schema=False)
async def recovery_health(request: Request) -> Response:
    try:
        client: httpx.AsyncClient = request.app.state.upstream_client
        upstream = await client.get(
            f"{UPSTREAM_BASE}/health",
            headers={"accept-encoding": "identity"},
            timeout=15.0,
        )
        if upstream.status_code != 200:
            return JSONResponse(
                status_code=503,
                content={"status": "degraded", "gateway": "ok", "release_target": "render", "upstream_status": upstream.status_code},
            )
        payload = upstream.json()
        return JSONResponse(
            status_code=200,
            content={
                "status": "healthy", "gateway": "ok", "release_target": "render",
                "upstream": payload.get("status"), "database": payload.get("database"),
                "configuration": payload.get("configuration"),
                "transactional_email": payload.get("transactional_email"),
            },
        )
    except Exception:
        return JSONResponse(
            status_code=503,
            content={"status": "degraded", "gateway": "ok", "release_target": "render", "upstream": "unreachable"},
        )


@app.api_route(
    "/{path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"],
    include_in_schema=False,
)
async def proxy(path: str, request: Request) -> Response:
    upstream_url = f"{UPSTREAM_BASE}/{path}"
    if request.url.query:
        upstream_url = f"{upstream_url}?{request.url.query}"

    forwarded_headers = {
        key: value for key, value in request.headers.items()
        if key.lower() not in HOP_BY_HOP_HEADERS
    }
    forwarded_headers["accept-encoding"] = "identity"
    forwarded_headers["x-forwarded-host"] = request.headers.get("host", "")
    forwarded_headers["x-forwarded-proto"] = "https"
    body = await request.body()
    try:
        client: httpx.AsyncClient = request.app.state.upstream_client
        upstream = await client.request(
            request.method,
            upstream_url,
            headers=forwarded_headers,
            content=body,
            timeout=60.0,
        )
    except httpx.HTTPError:
        return JSONResponse(
            status_code=502,
            content={"detail": "PlaceAI backend is temporarily unreachable", "code": "UPSTREAM_UNAVAILABLE"},
        )

    if upstream.status_code == 422:
        try:
            fields = _safe_validation_fields(upstream.json())
        except ValueError:
            fields = []
        if fields:
            LOGGER.warning("UPSTREAM_VALIDATION path=/%s fields=%s", path, ",".join(fields))

    response = Response(content=upstream.content, status_code=upstream.status_code)
    for key, value in upstream.headers.multi_items():
        lower = key.lower()
        if lower in HOP_BY_HOP_HEADERS or lower in {"content-length", "content-encoding"}:
            continue
        if lower == "location" and value.startswith(UPSTREAM_BASE):
            value = str(request.base_url).rstrip("/") + value[len(UPSTREAM_BASE):]
        response.headers.append(key, value)
    return response



# Preview-only escape hatch: allow an existing non-production Render gateway service
# to serve the real PlaceAI application without proxying to another deployment.
# This is intentionally blocked in production.
if os.getenv("PLACEAI_RENDER_DIRECT_APP", "false").strip().lower() == "true":
    if os.getenv("ENVIRONMENT", "development").strip().lower() == "production":
        raise RuntimeError("PLACEAI_RENDER_DIRECT_APP cannot be enabled in production")
    from app.app import app as _direct_placeai_app

    app = _direct_placeai_app
