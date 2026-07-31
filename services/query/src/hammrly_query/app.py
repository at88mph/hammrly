from __future__ import annotations

import asyncio
import json
import logging
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Annotated, Any, AsyncIterator, Generator, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from hammrly_query.config import Settings
from hammrly_query.contract_types import PayloadSummary, WorkloadKind, parse_payload_summary
from hammrly_query.job_index import get_job_index, index_owned_by_principal, index_to_detail
from hammrly_query.jwt_auth import Principal, validate_bearer_token
from hammrly_query.repository import (
    count_unread_notifications,
    counts_int,
    get_campaign_by_id,
    get_submission_by_job_id,
    latest_notification_id,
    list_campaign_failed_sample,
    list_campaign_jobs,
    list_interactive_submissions,
    list_notifications,
    list_submission_events,
    mark_all_notifications_read,
    mark_notification_read,
)
from hammrly_query.session import (
    create_engine_from_url,
    create_session_factory,
    create_writable_engine_from_url,
)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = Settings()
    app.state.settings = settings
    app.state.redis = None
    if settings.skip_db_bootstrap:
        app.state.engine = None
        app.state.session_factory = None
        app.state.rw_engine = None
        app.state.rw_session_factory = None
        logger.info("Query service started (skip_db_bootstrap; no engine)")
    elif not settings.database_url:
        raise RuntimeError("HAMMRLY_DATABASE_URL is required unless HAMMRLY_SKIP_DB_BOOTSTRAP=true")
    else:
        engine = create_engine_from_url(settings.database_url)
        app.state.engine = engine
        app.state.session_factory = create_session_factory(engine)
        rw_engine = create_writable_engine_from_url(settings.database_url)
        app.state.rw_engine = rw_engine
        app.state.rw_session_factory = create_session_factory(rw_engine)
        logger.info("Query service started (read-only + writable DB session factories ready)")

    if settings.redis_fake:
        import fakeredis

        app.state.redis = fakeredis.FakeRedis(decode_responses=False)
        logger.info("Query using FakeRedis for job index")
    elif settings.redis_url:
        import redis as redis_sync

        app.state.redis = redis_sync.Redis.from_url(
            settings.redis_url,
            decode_responses=False,
            socket_timeout=5,
            socket_connect_timeout=5,
        )
        logger.info("Query job-index Redis client ready")

    yield

    r = app.state.redis
    if r is not None:
        r.close()
    engine = getattr(app.state, "engine", None)
    if engine is not None:
        engine.dispose()
    rw_engine = getattr(app.state, "rw_engine", None)
    if rw_engine is not None:
        rw_engine.dispose()
    logger.info("Query engines disposed")


router = APIRouter()


class SubmissionEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    event_type: str
    payload_json: Optional[dict[str, Any]] = None
    occurred_at: datetime


class FailedSampleItem(BaseModel):
    job_id: UUID
    item_key: Optional[str] = None
    status: str
    status_detail: Optional[str] = None


class CampaignDetailResponse(BaseModel):
    campaign_id: UUID
    name: str
    description: Optional[str] = None
    status: str
    item_count: Optional[int] = None
    by_status: dict[str, int] = Field(default_factory=dict)
    fail_count: int = 0
    fail_pct: float = 0.0
    progress_pct: Optional[float] = None
    output_uri: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    failed_sample: list[FailedSampleItem] = Field(default_factory=list)


class CampaignJobItem(BaseModel):
    job_id: UUID
    submission_id: UUID
    item_key: Optional[str] = None
    status: str
    status_detail: Optional[str] = None
    updated_at: datetime


class CampaignJobListResponse(BaseModel):
    items: list[CampaignJobItem]
    limit: int
    offset: int


class JobDetailResponse(BaseModel):
    job_id: UUID
    submission_id: UUID
    tenant_id: str
    project_id: Optional[str] = None
    user_id: str
    campaign_id: Optional[UUID] = None
    item_key: Optional[str] = None
    status: str
    status_detail: Optional[str] = None
    queue_name: str
    priority: Optional[int] = None
    gpu_count: int = 0
    cluster_id: str
    k8s_job_name: Optional[str] = None
    k8s_namespace: Optional[str] = None
    k8s_job_uid: Optional[str] = None
    k8s_resource_version: Optional[str] = None
    access_url: Optional[str] = None
    requested_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    payload_summary: Optional[PayloadSummary] = None
    events: list[SubmissionEventOut] = Field(default_factory=list)


class InteractiveJobItem(BaseModel):
    job_id: UUID
    submission_id: UUID
    tenant_id: str
    status: str
    status_detail: Optional[str] = None
    queue_name: str
    gpu_count: int = 0
    kind: Optional[WorkloadKind] = None
    access_url: Optional[str] = None
    updated_at: datetime


class InteractiveJobListResponse(BaseModel):
    items: list[InteractiveJobItem]
    limit: int
    offset: int


class NotificationItem(BaseModel):
    id: int
    kind: str
    subject: str
    body_json: dict[str, Any] = Field(default_factory=dict)
    resource_type: Optional[str] = None
    resource_id: Optional[str] = None
    created_at: datetime
    read_at: Optional[datetime] = None


class NotificationListResponse(BaseModel):
    items: list[NotificationItem]
    limit: int
    offset: int


class UnreadCountResponse(BaseModel):
    unread_count: int


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_db(request: Request) -> Generator[Session, None, None]:
    factory: Optional[sessionmaker[Session]] = request.app.state.session_factory
    if factory is None:
        raise HTTPException(
            status_code=503,
            detail={"error": "database_unconfigured", "message": "Session factory not available"},
        )
    session = factory()
    try:
        yield session
    finally:
        session.close()


def get_rw_db(request: Request) -> Generator[Session, None, None]:
    factory: Optional[sessionmaker[Session]] = getattr(request.app.state, "rw_session_factory", None)
    if factory is None:
        raise HTTPException(
            status_code=503,
            detail={"error": "database_unconfigured", "message": "Writable session factory not available"},
        )
    session = factory()
    try:
        yield session
    finally:
        session.close()


SettingsDep = Annotated[Settings, Depends(get_settings)]
SessionDep = Annotated[Session, Depends(get_db)]
RwSessionDep = Annotated[Session, Depends(get_rw_db)]


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


PrincipalDep = Annotated[Principal, Depends(require_principal)]


def _to_detail(row: Any, events: list[Any]) -> JobDetailResponse:
    return JobDetailResponse(
        job_id=UUID(row.job_id),
        submission_id=UUID(row.submission_id),
        tenant_id=row.tenant_id,
        project_id=row.project_id,
        user_id=row.user_id,
        campaign_id=UUID(row.campaign_id) if getattr(row, "campaign_id", None) else None,
        item_key=getattr(row, "item_key", None),
        status=row.status,
        status_detail=row.status_detail,
        queue_name=row.queue_name,
        priority=row.priority,
        gpu_count=row.gpu_count,
        cluster_id=row.cluster_id,
        k8s_job_name=row.k8s_job_name,
        k8s_namespace=row.k8s_namespace,
        k8s_job_uid=row.k8s_job_uid,
        k8s_resource_version=row.k8s_resource_version,
        access_url=row.access_url,
        requested_at=row.requested_at,
        created_at=row.created_at,
        updated_at=row.updated_at,
        payload_summary=parse_payload_summary(row.payload_summary),
        events=[SubmissionEventOut.model_validate(e) for e in events],
    )


def _to_interactive_item(row: Any) -> InteractiveJobItem:
    ps = parse_payload_summary(getattr(row, "payload_summary", None))
    return InteractiveJobItem(
        job_id=UUID(row.job_id),
        submission_id=UUID(row.submission_id),
        tenant_id=row.tenant_id,
        status=row.status,
        status_detail=row.status_detail,
        queue_name=row.queue_name,
        gpu_count=row.gpu_count,
        kind=ps.kind if ps else None,
        access_url=row.access_url,
        updated_at=row.updated_at,
    )


@router.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/readyz")
def readyz(request: Request) -> dict[str, str]:
    factory: Optional[sessionmaker[Session]] = request.app.state.session_factory
    if factory is None:
        raise HTTPException(
            status_code=503,
            detail={"error": "not_ready", "message": "Database not configured"},
        )
    try:
        db = factory()
        try:
            db.execute(text("SELECT 1"))
        finally:
            db.close()
    except Exception as e:
        logger.warning("readiness DB check failed: %s", e)
        raise HTTPException(
            status_code=503,
            detail={"error": "not_ready", "message": "Database unavailable"},
        ) from e
    return {"status": "ready"}


@router.get("/.well-known/openapi.json", include_in_schema=False)
def well_known_openapi(request: Request) -> JSONResponse:
    return JSONResponse(content=request.app.openapi())


@router.get(
    "/v1/jobs/{job_id}",
    response_model=JobDetailResponse,
    responses={401: {"description": "Unauthenticated"}, 403: {"description": "Forbidden"}, 404: {"description": "Not found"}},
)
def get_job_by_id(
    job_id: UUID,
    request: Request,
    settings: SettingsDep,
    principal: PrincipalDep,
    db: SessionDep,
) -> JobDetailResponse:
    row = get_submission_by_job_id(db, settings, principal, str(job_id))
    if row is not None:
        events = list_submission_events(db, row.submission_id)
        return _to_detail(row, events)

    redis_client = request.app.state.redis
    if redis_client is not None:
        record = get_job_index(redis_client, settings, str(job_id))
        if record is not None and index_owned_by_principal(record, principal, settings):
            return JobDetailResponse.model_validate(index_to_detail(record, settings))

    raise HTTPException(
        status_code=404,
        detail={"error": "not_found", "message": "Job not found or access denied"},
    )


def _campaign_metrics(counts: dict[str, Any], item_count: Optional[int]) -> tuple[dict[str, int], int, float, Optional[float]]:
    by_status = {k: counts_int(counts, k) for k in counts if counts_int(counts, k) > 0}
    fail_count = counts_int(counts, "failed")
    ic = item_count or 0
    fail_pct = round(100.0 * fail_count / ic, 1) if ic > 0 else 0.0
    if ic <= 0:
        return by_status, fail_count, fail_pct, None
    terminal = sum(
        counts_int(counts, s)
        for s in ("succeeded", "failed", "unknown", "cancelled", "dead_letter")
    )
    progress_pct = round(100.0 * terminal / ic, 1)
    return by_status, fail_count, fail_pct, progress_pct


@router.get(
    "/v1/me/campaigns/{campaign_id}",
    response_model=CampaignDetailResponse,
    responses={401: {"description": "Unauthenticated"}, 403: {"description": "Forbidden"}, 404: {"description": "Not found"}},
)
def get_campaign_detail(
    campaign_id: UUID,
    settings: SettingsDep,
    principal: PrincipalDep,
    db: SessionDep,
) -> CampaignDetailResponse:
    row = get_campaign_by_id(db, settings, principal, str(campaign_id))
    if row is None:
        raise HTTPException(
            status_code=404,
            detail={"error": "not_found", "message": "Campaign not found or access denied"},
        )
    counts = row.counts_json if isinstance(row.counts_json, dict) else {}
    by_status, fail_count, fail_pct, progress_pct = _campaign_metrics(counts, row.item_count)
    failed_rows = list_campaign_failed_sample(db, settings, principal, str(campaign_id), limit=10)
    failed_sample = [
        FailedSampleItem(
            job_id=UUID(r.job_id),
            item_key=r.item_key,
            status=r.status,
            status_detail=r.status_detail,
        )
        for r in failed_rows
    ]
    return CampaignDetailResponse(
        campaign_id=UUID(row.campaign_id),
        name=row.name,
        description=row.description,
        status=row.status,
        item_count=row.item_count,
        by_status=by_status,
        fail_count=fail_count,
        fail_pct=fail_pct,
        progress_pct=progress_pct,
        output_uri=row.output_uri,
        created_at=row.created_at,
        updated_at=row.updated_at,
        failed_sample=failed_sample,
    )


@router.get(
    "/v1/me/campaigns/{campaign_id}/jobs",
    response_model=CampaignJobListResponse,
    responses={401: {"description": "Unauthenticated"}, 403: {"description": "Forbidden"}, 404: {"description": "Not found"}},
)
def list_campaign_jobs_route(
    campaign_id: UUID,
    settings: SettingsDep,
    principal: PrincipalDep,
    db: SessionDep,
    status: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> CampaignJobListResponse:
    if get_campaign_by_id(db, settings, principal, str(campaign_id)) is None:
        raise HTTPException(
            status_code=404,
            detail={"error": "not_found", "message": "Campaign not found or access denied"},
        )
    lim = min(limit, settings.list_max_limit)
    rows = list_campaign_jobs(
        db,
        settings,
        principal,
        str(campaign_id),
        status=status,
        limit=lim,
        offset=offset,
    )
    return CampaignJobListResponse(
        items=[
            CampaignJobItem(
                job_id=UUID(r.job_id),
                submission_id=UUID(r.submission_id),
                item_key=r.item_key,
                status=r.status,
                status_detail=r.status_detail,
                updated_at=r.updated_at,
            )
            for r in rows
        ],
        limit=lim,
        offset=offset,
    )


@router.get(
    "/v1/me/jobs/interactive",
    response_model=InteractiveJobListResponse,
    responses={401: {"description": "Unauthenticated"}, 403: {"description": "Forbidden"}},
)
def list_my_interactive_jobs(
    settings: SettingsDep,
    principal: PrincipalDep,
    db: SessionDep,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> InteractiveJobListResponse:
    lim = min(limit, settings.list_max_limit)
    rows = list_interactive_submissions(db, settings, principal, limit=lim, offset=offset)
    return InteractiveJobListResponse(
        items=[_to_interactive_item(r) for r in rows],
        limit=lim,
        offset=offset,
    )


def _to_notification_item(row: Any) -> NotificationItem:
    return NotificationItem(
        id=row.id,
        kind=row.kind,
        subject=row.subject,
        body_json=row.body_json if isinstance(row.body_json, dict) else {},
        resource_type=row.resource_type,
        resource_id=row.resource_id,
        created_at=row.created_at,
        read_at=row.read_at,
    )


@router.get(
    "/v1/me/notifications",
    response_model=NotificationListResponse,
    responses={401: {"description": "Unauthenticated"}, 403: {"description": "Forbidden"}},
)
def list_my_notifications(
    settings: SettingsDep,
    principal: PrincipalDep,
    db: SessionDep,
    unread_only: bool = Query(False),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> NotificationListResponse:
    lim = min(limit, settings.list_max_limit)
    rows = list_notifications(
        db, principal, unread_only=unread_only, limit=lim, offset=offset
    )
    return NotificationListResponse(
        items=[_to_notification_item(r) for r in rows],
        limit=lim,
        offset=offset,
    )


@router.get(
    "/v1/me/notifications/unread_count",
    response_model=UnreadCountResponse,
    responses={401: {"description": "Unauthenticated"}, 403: {"description": "Forbidden"}},
)
def get_unread_notification_count(
    principal: PrincipalDep,
    db: SessionDep,
) -> UnreadCountResponse:
    return UnreadCountResponse(unread_count=count_unread_notifications(db, principal))


@router.post(
    "/v1/me/notifications/{notification_id}/read",
    response_model=NotificationItem,
    responses={
        401: {"description": "Unauthenticated"},
        403: {"description": "Forbidden"},
        404: {"description": "Not found"},
    },
)
def mark_my_notification_read(
    notification_id: int,
    principal: PrincipalDep,
    db: RwSessionDep,
) -> NotificationItem:
    row = mark_notification_read(db, principal, notification_id)
    if row is None:
        raise HTTPException(
            status_code=404,
            detail={"error": "not_found", "message": "Notification not found or access denied"},
        )
    return _to_notification_item(row)


@router.post(
    "/v1/me/notifications/read_all",
    response_model=UnreadCountResponse,
    responses={401: {"description": "Unauthenticated"}, 403: {"description": "Forbidden"}},
)
def mark_all_my_notifications_read(
    principal: PrincipalDep,
    db: RwSessionDep,
) -> UnreadCountResponse:
    mark_all_notifications_read(db, principal)
    return UnreadCountResponse(unread_count=0)


@router.get(
    "/v1/me/notifications/stream",
    responses={401: {"description": "Unauthenticated"}, 403: {"description": "Forbidden"}},
)
async def stream_my_notifications(
    request: Request,
    principal: PrincipalDep,
) -> StreamingResponse:
    """SSE stream of unread_count bumps for the authenticated user (Bearer via fetch)."""

    async def event_gen() -> AsyncIterator[str]:
        factory: Optional[sessionmaker[Session]] = request.app.state.session_factory
        if factory is None:
            yield f"event: error\ndata: {json.dumps({'error': 'database_unconfigured'})}\n\n"
            return

        last_id = 0
        last_unread = -1
        # Initial snapshot
        db = factory()
        try:
            last_id = int(latest_notification_id(db, principal) or 0)
            last_unread = count_unread_notifications(db, principal)
        finally:
            db.close()
        yield f"event: snapshot\ndata: {json.dumps({'unread_count': last_unread, 'latest_id': last_id})}\n\n"

        while True:
            if await request.is_disconnected():
                break
            await asyncio.sleep(2.0)
            db = factory()
            try:
                latest = int(latest_notification_id(db, principal) or 0)
                unread = count_unread_notifications(db, principal)
            finally:
                db.close()
            if latest != last_id or unread != last_unread:
                last_id = latest
                last_unread = unread
                yield (
                    "event: notification\n"
                    f"data: {json.dumps({'unread_count': unread, 'latest_id': latest})}\n\n"
                )
            else:
                yield ": keepalive\n\n"

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


_route_settings = Settings()
_root = _route_settings.http_path_prefix
_docs_url = f"{_root}/docs" if _root else "/docs"
_redoc_url = f"{_root}/redoc" if _root else "/redoc"
_openapi_url = f"{_root}/internal/openapi.json" if _root else "/internal/openapi.json"

app = FastAPI(
    title="Hammrly Query",
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
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": "http_error", "message": str(exc.detail)},
    )


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
