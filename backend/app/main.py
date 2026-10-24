import logging
import re
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from redis.asyncio import Redis
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm.exc import StaleDataError
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.api.v1 import (
    accounting,
    ai,
    audit_admin,
    audit_ai,
    audit_evidence,
    audit_execution,
    audit_methodology,
    auth,
    client_portal,
    clients,
    collaboration,
    connectors,
    engagements,
    entities,
    health,
    ifrs,
    intelligence,
    jobs,
    jurisdictions,
    periods,
    regulatory,
    tenants,
    workspace,
)
from app.core.config import settings
from app.core.exceptions import ErrorResponse
from app.core.logging import configure_logging
from app.modules.connectors.zoho import ConnectorError
from app.modules.connectors.operations import router as connector_operations

config = settings()
configure_logging()
logger = logging.getLogger("auditos")


@asynccontextmanager
async def lifespan(application):
    if config.environment == "production":
        await health.ready()
    yield


app = FastAPI(
    title="AuditOS UAE",
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/docs" if config.environment == "development" else None,
    redoc_url=None,
    responses={code: {"model": ErrorResponse} for code in [401, 403, 404, 409, 413, 422, 429, 503]},
)
app.include_router(connector_operations, prefix="/api/v1")
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH"],
    allow_headers=[
        "Authorization",
        "Content-Type",
        "X-Tenant-ID",
        "X-Request-ID",
        "Idempotency-Key",
    ],
)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=config.allowed_hosts)


@app.middleware("http")
async def safeguards(request: Request, call_next):
    started = time.perf_counter()
    supplied = request.headers.get("x-request-id", "")
    request.state.request_id = (
        supplied if re.fullmatch(r"[A-Za-z0-9_-]{1,64}", supplied) else str(uuid.uuid4())
    )
    try:
        is_upload = (
            request.url.path in {
                "/api/v1/accounting/imports",
                "/api/v1/workspace/inspect-file",
                "/api/v1/connectors/report-packages",
            }
            or "/chunks/" in request.url.path
            or "/audit/evidence-files/" in request.url.path
            or request.url.path.startswith("/api/v1/tp/engagements/")
            and "/datasets/" in request.url.path
            and request.url.path.endswith("/import")
            or request.url.path.startswith("/api/v1/grc/engagements/")
            and request.url.path.endswith("/sod/import")
            or request.url.path.startswith("/api/v1/client-portal/requests/")
            and request.url.path.endswith("/upload")
        )
        if is_upload and request.method in {"POST", "PUT"}:
            maximum = config.max_upload_bytes + 65536
            if int(request.headers.get("content-length", "0")) > maximum:
                raise HTTPException(413, "Request body too large")
            original_receive = request._receive
            received = 0

            async def limited_receive():
                nonlocal received
                message = await original_receive()
                received += len(message.get("body", b""))
                if received > maximum:
                    raise HTTPException(413, "Request body too large")
                return message

            request._receive = limited_receive
        elif request.method in {"POST", "PATCH", "PUT"}:
            body = bytearray()
            async for chunk in request.stream():
                body.extend(chunk)
                if len(body) > config.max_request_bytes:
                    raise HTTPException(413, "Request body too large")
            request._body = bytes(body)
        if (
            request.url.path.startswith("/api/v1/auth/")
            or request.url.path == "/api/v1/admin/invitations/redeem"
        ) and request.method == "POST":
            address = request.client.host if request.client else "unknown"
            async with Redis.from_url(
                config.redis_url, socket_connect_timeout=2, socket_timeout=2
            ) as redis:
                count = await redis.eval(
                    "local n=redis.call('INCR',KEYS[1]); if n==1 then redis.call('EXPIRE',KEYS[1],60) end; return n",
                    1,
                    "auth-rate:" + address,
                )
                if count > 20:
                    raise HTTPException(429, "Authentication rate limit exceeded")
        response = await call_next(request)
    except HTTPException as exc:
        response = error(request, exc.status_code, str(exc.detail))
    except Exception:
        response = error(request, 503, "Service temporarily unavailable")
    response.headers.update(
        {
            "X-Request-ID": request.state.request_id,
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
            "Referrer-Policy": "no-referrer",
            "Cache-Control": "no-store",
        }
    )
    if config.environment == "production":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    logger.info(
        "request",
        extra={
            "event": "http.request",
            "request_id": request.state.request_id,
            "status": response.status_code,
            "duration_ms": round((time.perf_counter() - started) * 1000, 3),
            "method": request.method,
            "route": getattr(request.scope.get("route"), "path", "unmatched"),
            "release": config.release_id,
        },
    )
    return response


def error(request: Request, status: int, message: str):
    return JSONResponse(
        status_code=status,
        content={
            "error": {
                "code": str(status),
                "message": message,
                "request_id": getattr(request.state, "request_id", "unavailable"),
            }
        },
    )


@app.exception_handler(StarletteHTTPException)
async def http_error(request: Request, exc: StarletteHTTPException):
    return error(request, exc.status_code, str(exc.detail))


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError):
    return error(request, 422, "Request validation failed")


@app.exception_handler(IntegrityError)
async def integrity_error(request: Request, exc: IntegrityError):
    return error(request, 409, "Database constraint conflict")


@app.exception_handler(StaleDataError)
async def stale_error(request: Request, exc: StaleDataError):
    return error(request, 409, "Resource version conflict")


@app.exception_handler(ConnectorError)
async def connector_error(request: Request, exc: ConnectorError):
    return error(request, 422, str(exc))


for router in [
    ifrs.router,
    audit_admin.router,
    audit_evidence.router,
    client_portal.router,
    audit_ai.router,
    audit_methodology.router,
    audit_execution.router,
    workspace.router,
    accounting.router,
    connectors.router,
    auth.router,
    tenants.router,
    clients.router,
    entities.router,
    engagements.router,
    periods.router,
    ai.router,
    jobs.router,
]:
    app.include_router(router, prefix="/api/v1")
app.include_router(jurisdictions.router, prefix="/api/v1")
app.include_router(intelligence.router, prefix="/api/v1")
app.include_router(regulatory.router, prefix="/api/v1")
app.include_router(collaboration.router, prefix="/api/v1")
app.include_router(health.router)

from app.api.v1.ifrs_ai import router as ifrs_ai_router  # noqa: E402

app.include_router(ifrs_ai_router, prefix="/api/v1")

from app.api.v1.tax import router as tax_router  # noqa: E402

app.include_router(tax_router, prefix="/api/v1")

from app.api.v1.tax_ai import router as tax_ai_router  # noqa: E402

app.include_router(tax_ai_router, prefix="/api/v1")

from app.api.v1.vat import router as vat_router  # noqa: E402

app.include_router(vat_router, prefix="/api/v1")

from app.api.v1.vat_ai import router as vat_ai_router  # noqa: E402

app.include_router(vat_ai_router, prefix="/api/v1")

from app.api.v1.tp import router as tp_router  # noqa: E402

app.include_router(tp_router, prefix="/api/v1")

from app.api.v1.tp_ai import router as tp_ai_router  # noqa: E402

app.include_router(tp_ai_router, prefix="/api/v1")

from app.api.v1.ml import router as ml_router  # noqa: E402

app.include_router(ml_router, prefix="/api/v1")
from app.api.v1.dmtt import router as dmtt_router  # noqa: E402

app.include_router(dmtt_router, prefix="/api/v1")
from app.api.v1.dmtt_ai import router as dmtt_ai_router  # noqa: E402

app.include_router(dmtt_ai_router, prefix="/api/v1")

from app.api.v1.grc import router as grc_router  # noqa: E402

app.include_router(grc_router, prefix="/api/v1")

from app.api.v1.grc_ai import router as grc_ai_router  # noqa: E402

app.include_router(grc_ai_router, prefix="/api/v1")

from app.api.v1.enterprise_ai import router as enterprise_ai_router  # noqa: E402

app.include_router(enterprise_ai_router, prefix="/api/v1")

from app.api.v1.platform_admin import router as platform_router  # noqa: E402

app.include_router(platform_router, prefix="/api/v1")
