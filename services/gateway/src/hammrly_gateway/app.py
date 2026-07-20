from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Any, Literal, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from jsonschema.exceptions import ValidationError
from pydantic import BaseModel, ConfigDict
import redis.asyncio as redis

from hammrly_gateway.campaign import (
    build_campaign_expansion_envelope,
    campaign_body_hash,
    cross_validate_campaign_submit,
    load_campaign_validator,
    normalize_campaign_body,
    reject_headless_on_session,
    validate_campaign_submit,
)
from hammrly_gateway.campaign_idempotency import (
    get_campaign_completed,
    is_campaign_pending,
    release_campaign_claim,
    save_campaign_result,
    try_campaign_claim,
)
from hammrly_gateway.config import Settings
from hammrly_gateway.envelope import (
    build_envelope,
    canonical_body_hash,
    job_status_url,
    new_job_id,
    resolve_tenant_id,
)
from hammrly_gateway.idempotency import get_completed, is_pending, release_claim, save_result, try_claim
from hammrly_gateway.job_index import delete_job_index, put_job_index
from hammrly_gateway.jwt_auth import Principal, validate_bearer_token
from hammrly_gateway.publisher import publish_envelope
from hammrly_gateway.redis_async import maybe_await
from hammrly_gateway.validation import (
    cross_validate_envelope,
    load_validator,
    normalize_workload_ephemeral_storage,
    normalize_workload_networking,
    validation_error_message,
    validate_envelope,
)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = Settings()
    app.state.settings = settings
    if settings.redis_fake:
        import fakeredis

        app.state.redis = fakeredis.FakeRedis(decode_responses=False)
    else:
        app.state.redis = redis.from_url(settings.redis_url, decode_responses=False)
    load_validator(settings.contract_schema_path)
    load_campaign_validator(settings.campaign_schema_path)
    logger.info(
        "Gateway started; stream=%s campaign_stream=%s fake_redis=%s",
        settings.redis_stream_key,
        settings.campaign_stream_key,
        settings.redis_fake,
    )
    yield
    r = app.state.redis
    aclose = getattr(r, "aclose", None)
    if callable(aclose):
        await aclose()
    else:
        close = getattr(r, "close", None)
        if callable(close):
            maybe = close()
            if asyncio.iscoroutine(maybe):
                await maybe
    logger.info("Redis connection closed")


router = APIRouter()


class Correlation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    trace_id: Optional[str] = None
    span_id: Optional[str] = None
    client_request_id: Optional[str] = None


class CreateJobRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workload: dict[str, Any]
    tenant_id: Optional[str] = None
    project_id: Optional[str] = None
    correlation: Optional[Correlation] = None


class CreateJobResponse(BaseModel):
    job_id: str
    submission_id: str
    status: Literal["PENDING"] = "PENDING"
    status_url: str


class CreateCampaignRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str
    campaign: dict[str, Any]
    template: dict[str, Any]
    items: Optional[list[dict[str, Any]]] = None
    manifest_uri: Optional[str] = None
    manifest_sha256: Optional[str] = None
    item_count: Optional[int] = None
    tenant_id: Optional[str] = None
    project_id: Optional[str] = None
    correlation: Optional[Correlation] = None


class CreateCampaignResponse(BaseModel):
    campaign_id: str
    status: str
    item_count: Optional[int] = None
    status_url: str


def _problem(status_code: int, error: str, message: str, details: Optional[dict] = None) -> JSONResponse:
    body: dict[str, Any] = {"error": error, "message": message}
    if details is not None:
        body["details"] = details
    return JSONResponse(status_code=status_code, content=body)


async def require_principal(
    request: Request,
    authorization: Optional[str] = Header(None),
) -> Principal:
    settings: Settings = request.app.state.settings
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail={
                "error": "unauthenticated",
                "message": "Missing or invalid Authorization header (expected Bearer token)",
            },
        )
    token = authorization[7:].strip()
    if not token:
        raise HTTPException(
            status_code=401,
            detail={"error": "unauthenticated", "message": "Empty bearer token"},
        )
    try:
        return validate_bearer_token(token, settings)
    except PermissionError as e:
        raise HTTPException(
            status_code=403,
            detail={"error": "forbidden", "message": str(e)},
        ) from e
    except ValueError:
        raise HTTPException(
            status_code=401,
            detail={"error": "unauthenticated", "message": "Invalid or expired token"},
        ) from None
    except RuntimeError as e:
        logger.error("JWT configuration error: %s", e)
        raise HTTPException(
            status_code=500,
            detail={"error": "server_misconfigured", "message": "JWT validation is not configured"},
        ) from e


@router.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/readyz")
async def readyz(request: Request) -> dict[str, str]:
    r: redis.Redis = request.app.state.redis
    try:
        if await maybe_await(r.ping()):
            return {"status": "ready"}
    except Exception as e:
        logger.warning("readiness redis ping failed: %s", e)
    raise HTTPException(
        status_code=503,
        detail={"error": "not_ready", "message": "Redis unavailable"},
    )


@router.get("/.well-known/openapi.json", include_in_schema=False)
async def well_known_openapi(request: Request) -> JSONResponse:
    return JSONResponse(content=request.app.openapi())


async def _poll_idempotency(
    settings: Settings,
    r: redis.Redis,
    idem_key: str,
    body_hash: str,
) -> tuple[Optional[CreateJobResponse], bool]:
    """
    Wait for another worker to finish idempotent submit.
    Returns (response, conflict) where conflict means wrong body hash.
    """
    for _ in range(40):
        await asyncio.sleep(0.05)
        rec = await get_completed(r, settings, idem_key)
        if rec:
            if rec.body_hash != body_hash:
                return None, True
            return CreateJobResponse(
                job_id=rec.job_id,
                submission_id=rec.submission_id,
                status_url=job_status_url(settings, rec.job_id),
            ), False
        if not await is_pending(r, settings, idem_key):
            return None, False
    return None, False


@router.post(
    "/v2/session",
    response_model=CreateJobResponse,
    status_code=202,
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Not authorized"},
        400: {"description": "Invalid submission"},
        409: {"description": "Idempotency key reuse with different body"},
        503: {"description": "Redis or transient failure"},
    },
)
async def create_session(
    body: CreateJobRequest,
    request: Request,
    principal: Principal = Depends(require_principal),
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
) -> CreateJobResponse | JSONResponse:
    settings: Settings = request.app.state.settings
    r: redis.Redis = request.app.state.redis

    try:
        reject_headless_on_session(body.workload)
        workload_norm = normalize_workload_networking(body.workload)
        workload_norm = normalize_workload_ephemeral_storage(
            workload_norm,
            default_request=settings.ephemeral_storage_default,
            maximum=settings.ephemeral_storage_max,
        )
    except ValueError as e:
        msg = str(e)
        if "POST /v2/campaigns" in msg:
            return _problem(400, "use_campaign_submit", msg)
        return _problem(400, "invalid_submission", msg)

    corr = body.correlation.model_dump(exclude_none=True) if body.correlation else None
    idem_parts = {
        "tenant_id": body.tenant_id,
        "project_id": body.project_id,
        "correlation": corr,
        "workload": workload_norm,
    }
    body_hash = canonical_body_hash(idem_parts)

    submission_uuid: Optional[UUID] = None
    idem_str: Optional[str] = None
    claimed = False

    if idempotency_key:
        idem_str = idempotency_key.strip()
        try:
            submission_uuid = UUID(idem_str)
        except ValueError:
            return _problem(
                400,
                "invalid_idempotency_key",
                "Idempotency-Key must be a UUID",
            )

        existing = await get_completed(r, settings, idem_str)
        if existing:
            if existing.body_hash != body_hash:
                return _problem(
                    409,
                    "idempotency_conflict",
                    "Idempotency-Key was already used with a different request body",
                )
            return CreateJobResponse(
                job_id=existing.job_id,
                submission_id=existing.submission_id,
                status_url=job_status_url(settings, existing.job_id),
            )

        if await is_pending(r, settings, idem_str):
            alt, conflict = await _poll_idempotency(settings, r, idem_str, body_hash)
            if conflict:
                return _problem(
                    409,
                    "idempotency_conflict",
                    "Idempotency-Key was already used with a different request body",
                )
            if alt:
                return alt
            return _problem(
                503,
                "idempotency_in_progress",
                "Submission with this Idempotency-Key is being processed; retry shortly",
            )

        claimed = await try_claim(r, settings, idem_str)
        if not claimed:
            alt, conflict = await _poll_idempotency(settings, r, idem_str, body_hash)
            if conflict:
                return _problem(
                    409,
                    "idempotency_conflict",
                    "Idempotency-Key was already used with a different request body",
                )
            if alt:
                return alt
            return _problem(
                503,
                "idempotency_in_progress",
                "Submission with this Idempotency-Key is being processed; retry briefly",
            )
    else:
        submission_uuid = new_job_id()

    job_uuid = new_job_id()

    try:
        tenant_id = resolve_tenant_id(body.tenant_id, principal, settings)
    except PermissionError as e:
        if claimed and idem_str:
            await release_claim(r, settings, idem_str)
        return _problem(403, "forbidden", str(e))
    except ValueError as e:
        if claimed and idem_str:
            await release_claim(r, settings, idem_str)
        return _problem(400, "invalid_submission", str(e))

    envelope = build_envelope(
        settings=settings,
        principal=principal,
        tenant_id=tenant_id,
        project_id=body.project_id,
        workload=workload_norm,
        correlation=corr,
        submission_id=submission_uuid,
        job_id=job_uuid,
    )

    try:
        cross_validate_envelope(envelope)
        validate_envelope(envelope, schema_path=settings.contract_schema_path)
    except ValidationError as e:
        if claimed and idem_str:
            await release_claim(r, settings, idem_str)
        return _problem(
            400,
            "invalid_submission",
            "Envelope failed JSON Schema validation",
            details={"errors": [validation_error_message(e)]},
        )
    except ValueError as e:
        if claimed and idem_str:
            await release_claim(r, settings, idem_str)
        return _problem(400, "invalid_submission", str(e))

    try:
        await put_job_index(r, settings, envelope, status="pending")
    except Exception as e:
        logger.exception("Redis job index SET failed: %s", e)
        if claimed and idem_str:
            await release_claim(r, settings, idem_str)
        return _problem(
            503,
            "queue_unavailable",
            "Could not record job submission; retry later",
        )

    try:
        await publish_envelope(r, settings.redis_stream_key, envelope)
    except Exception as e:
        logger.exception("Redis XADD failed: %s", e)
        await delete_job_index(r, settings, str(job_uuid))
        if claimed and idem_str:
            await release_claim(r, settings, idem_str)
        return _problem(
            503,
            "queue_unavailable",
            "Could not publish job submission; retry later",
        )

    if idem_str:
        await save_result(
            r,
            settings,
            idem_str,
            job_id=str(job_uuid),
            submission_id=str(submission_uuid),
            body_hash=body_hash,
        )

    return CreateJobResponse(
        job_id=str(job_uuid),
        submission_id=str(submission_uuid),
        status_url=job_status_url(settings, str(job_uuid)),
    )


def _campaign_status_url(settings: Settings, campaign_id: str) -> str:
    return settings.query_campaign_status_path_template.format(campaign_id=campaign_id)


async def _poll_campaign_idempotency(
    settings: Settings,
    r: redis.Redis,
    idem_key: str,
    body_hash: str,
) -> tuple[Optional[CreateCampaignResponse], bool]:
    for _ in range(40):
        await asyncio.sleep(0.05)
        rec = await get_campaign_completed(r, settings, idem_key)
        if rec:
            if rec.body_hash != body_hash:
                return None, True
            return CreateCampaignResponse(
                campaign_id=rec.campaign_id,
                status=rec.status,
                item_count=rec.item_count,
                status_url=rec.status_url,
            ), False
        if not await is_campaign_pending(r, settings, idem_key):
            return None, False
    return None, False


@router.post(
    "/v2/campaigns",
    response_model=CreateCampaignResponse,
    status_code=202,
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Not authorized"},
        400: {"description": "Invalid campaign"},
        409: {"description": "Idempotency key reuse with different body"},
        503: {"description": "Redis or transient failure"},
    },
)
async def create_campaign(
    body: CreateCampaignRequest,
    request: Request,
    principal: Principal = Depends(require_principal),
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
) -> CreateCampaignResponse | JSONResponse:
    settings: Settings = request.app.state.settings
    r: redis.Redis = request.app.state.redis

    raw_body = body.model_dump(exclude_none=True)
    if body.correlation:
        raw_body["correlation"] = body.correlation.model_dump(exclude_none=True)

    try:
        norm = normalize_campaign_body(
            raw_body,
            ephemeral_default=settings.ephemeral_storage_default,
            ephemeral_max=settings.ephemeral_storage_max,
        )
        cross_validate_campaign_submit(norm, max_inline_items=settings.campaign_max_inline_items)
        validate_campaign_submit(norm, schema_path=settings.campaign_schema_path)
    except ValidationError as e:
        return _problem(
            400,
            "invalid_campaign",
            "Campaign failed JSON Schema validation",
            details={"errors": [validation_error_message(e)]},
        )
    except ValueError as e:
        err = str(e)
        code = "use_campaign_submit" if "POST /v2/campaigns" in err else "invalid_campaign"
        return _problem(400, code, err)

    body_hash = campaign_body_hash(norm)

    campaign_uuid: Optional[UUID] = None
    idem_str: Optional[str] = None
    claimed = False

    if idempotency_key:
        idem_str = idempotency_key.strip()
        try:
            campaign_uuid = UUID(idem_str)
        except ValueError:
            return _problem(400, "invalid_idempotency_key", "Idempotency-Key must be a UUID")

        existing = await get_campaign_completed(r, settings, idem_str)
        if existing:
            if existing.body_hash != body_hash:
                return _problem(
                    409,
                    "idempotency_conflict",
                    "Idempotency-Key was already used with a different request body",
                )
            return CreateCampaignResponse(
                campaign_id=existing.campaign_id,
                status=existing.status,
                item_count=existing.item_count,
                status_url=existing.status_url,
            )

        if await is_campaign_pending(r, settings, idem_str):
            alt, conflict = await _poll_campaign_idempotency(settings, r, idem_str, body_hash)
            if conflict:
                return _problem(409, "idempotency_conflict", "Idempotency-Key conflict")
            if alt:
                return alt
            return _problem(503, "idempotency_in_progress", "Campaign submit in progress; retry shortly")

        claimed = await try_campaign_claim(r, settings, idem_str)
        if not claimed:
            alt, conflict = await _poll_campaign_idempotency(settings, r, idem_str, body_hash)
            if conflict:
                return _problem(409, "idempotency_conflict", "Idempotency-Key conflict")
            if alt:
                return alt
            return _problem(503, "idempotency_in_progress", "Campaign submit in progress; retry briefly")
    else:
        campaign_uuid = new_job_id()

    try:
        tenant_id = resolve_tenant_id(body.tenant_id, principal, settings)
    except PermissionError as e:
        if claimed and idem_str:
            await release_campaign_claim(r, settings, idem_str)
        return _problem(403, "forbidden", str(e))
    except ValueError as e:
        if claimed and idem_str:
            await release_campaign_claim(r, settings, idem_str)
        return _problem(400, "invalid_campaign", str(e))

    envelope = build_campaign_expansion_envelope(
        settings=settings,
        principal=principal,
        tenant_id=tenant_id,
        body=norm,
        campaign_id=campaign_uuid,
    )

    try:
        await publish_envelope(r, settings.campaign_stream_key, envelope)
    except Exception as e:
        logger.exception("Redis XADD campaign failed: %s", e)
        if claimed and idem_str:
            await release_campaign_claim(r, settings, idem_str)
        return _problem(503, "queue_unavailable", "Could not publish campaign; retry later")

    items = norm.get("items")
    item_count: Optional[int] = len(items) if isinstance(items, list) else norm.get("item_count")
    status_url = _campaign_status_url(settings, str(campaign_uuid))

    if idem_str:
        await save_campaign_result(
            r,
            settings,
            idem_str,
            campaign_id=str(campaign_uuid),
            body_hash=body_hash,
            item_count=item_count,
            status_url=status_url,
        )

    return CreateCampaignResponse(
        campaign_id=str(campaign_uuid),
        status="accepted",
        item_count=item_count,
        status_url=status_url,
    )


_route_settings = Settings()
_root = _route_settings.http_path_prefix
_docs_url = f"{_root}/docs" if _root else "/docs"
_redoc_url = f"{_root}/redoc" if _root else "/redoc"
_openapi_url = f"{_root}/internal/openapi.json" if _root else "/internal/openapi.json"

app = FastAPI(
    title="Hammrly Gateway",
    version="0.1.0",
    lifespan=lifespan,
    docs_url=_docs_url,
    redoc_url=_redoc_url,
    openapi_url=_openapi_url,
)


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    if isinstance(exc.detail, dict) and "error" in exc.detail:
        return JSONResponse(status_code=exc.status_code, content=exc.detail)
    return _problem(exc.status_code, "http_error", str(exc.detail))


app.include_router(router, prefix=_route_settings.http_path_prefix)


def mount_cors(application: FastAPI, settings: Settings) -> None:
    origins = settings.cors_origins_list
    if not origins:
        return
    application.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


mount_cors(app, _route_settings)
