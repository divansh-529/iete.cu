import secrets
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.audit.router import router as audit_router
from app.auth.deps import CSRF_COOKIE
from app.auth.router import router as auth_router
from app.core.config import settings
from app.core.db import SessionLocal
from app.core.errors import error_body, install_error_handlers
from app.core.request_context import client_ip, from_trusted_proxy, request_ip
from app.events.router import router as events_router
from app.members.router import router as members_router
from app.notifications.router import router as notifications_router
from app.org.router import router as org_router
from app.permissions.catalogue import sync_catalogue
from app.permissions.router import router as permissions_router
from app.scores.router import router as scores_router
from app.tasks.router import router as tasks_router
from app.users.router import router as users_router

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
# Endpoints a browser calls before it has a CSRF cookie.
CSRF_EXEMPT = {"/api/auth/login", "/api/auth/accept-invite"}
# Reachable without logging in. Everything else must declare an auth dependency (see tests).
PUBLIC_PATHS = {"/api/health", "/api/auth/login", "/api/auth/accept-invite",
                "/api/auth/invite/{token}"}
# Require a login but no specific permission (users acting on their own session).
SELF_PATHS = {"/api/auth/me", "/api/auth/logout", "/api/auth/change-password",
              "/api/me/org", "/api/me/profile", "/api/notifications", "/api/notifications/read"}


@asynccontextmanager
async def lifespan(_: FastAPI):
    with SessionLocal() as db:
        sync_catalogue(db)
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="IETE Student Forum ERP", lifespan=lifespan, docs_url="/api/docs",
                  openapi_url="/api/openapi.json", redoc_url=None)
    install_error_handlers(app)

    @app.middleware("http")
    async def security_middleware(request: Request, call_next):
        path = request.url.path
        # In production only the website's /api proxy may reach the API (health stays open for uptime checks).
        if settings.proxy_secret and path != "/api/health" and not from_trusted_proxy(request):
            return JSONResponse(error_body("FORBIDDEN", "Use the portal website."), status_code=403)
        client_ip.set(request_ip(request))
        if (request.method not in SAFE_METHODS and path.startswith("/api/")
                and path not in CSRF_EXEMPT):
            cookie = request.cookies.get(CSRF_COOKIE)
            header = request.headers.get("x-csrf-token")
            if not cookie or not header or not secrets.compare_digest(cookie, header):
                return JSONResponse(error_body("CSRF_FAILED", "Security check failed. Reload the page."),
                                    status_code=403)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "same-origin"
        if path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/api/health", tags=["meta"])
    def health():
        return {"status": "ok"}

    app.include_router(auth_router)
    app.include_router(users_router)
    app.include_router(permissions_router)
    app.include_router(org_router)
    app.include_router(audit_router)
    app.include_router(events_router)
    app.include_router(tasks_router)
    app.include_router(notifications_router)
    app.include_router(members_router)
    app.include_router(scores_router)
    return app


app = create_app()
