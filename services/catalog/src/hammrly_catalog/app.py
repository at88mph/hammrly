from __future__ import annotations

import logging
import urllib.parse
from contextlib import asynccontextmanager
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from hammrly_catalog.config import Settings
from hammrly_catalog.jwt_auth import Principal, validate_bearer_token
from hammrly_catalog.projection import SoftwareSearchResponse, project_rows
from hammrly_catalog.software_search import SoftwareSearchService
from hammrly_catalog.tap import TapClient, TapError, normalize_terms

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = Settings()
    tap_client = TapClient(settings)
    app.state.settings = settings
    app.state.tap_client = tap_client
    app.state.software_search = SoftwareSearchService(settings, tap_client)
    logger.info("Catalog service started")
    yield


router = APIRouter()


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_software_search(request: Request) -> SoftwareSearchService:
    return request.app.state.software_search


SettingsDep = Annotated[Settings, Depends(get_settings)]
SoftwareSearchDep = Annotated[SoftwareSearchService, Depends(get_software_search)]


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


@router.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/readyz")
def readyz(settings: SettingsDep) -> dict[str, str]:
    if not settings.tap_sync_url:
        raise HTTPException(
            status_code=503,
            detail={"error": "not_ready", "message": "HAMMRLY_TAP_SYNC_URL is not configured"},
        )
    if not settings.tap_search_columns_list:
        raise HTTPException(
            status_code=503,
            detail={"error": "not_ready", "message": "HAMMRLY_TAP_SEARCH_COLUMNS is not configured"},
        )
    if not settings.tap_columns:
        raise HTTPException(
            status_code=503,
            detail={"error": "not_ready", "message": "No HAMMRLY_TAP_COLUMN_* variables are configured"},
        )
    return {"status": "ready"}


@router.get("/.well-known/openapi.json", include_in_schema=False)
def well_known_openapi(request: Request) -> JSONResponse:
    return JSONResponse(content=request.app.openapi())


@router.post(
    "/v1/software/query",
    response_model=SoftwareSearchResponse,
    responses={
        400: {"description": "Invalid search request"},
        401: {"description": "Unauthenticated"},
        403: {"description": "Forbidden"},
        502: {"description": "TAP service error"},
    },
)
async def query_software(
    request: Request,
    settings: SettingsDep,
    principal: PrincipalDep,
    software_search: SoftwareSearchDep,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> SoftwareSearchResponse:
    del principal
    lim = min(limit, settings.list_max_limit)
    terms = await _form_terms(request)
    try:
        normalized_terms = normalize_terms(
            terms,
            max_terms=settings.search_max_terms,
            max_term_length=settings.search_max_term_length,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail={"error": "invalid_search", "message": str(e)},
        ) from e

    try:
        rows = software_search.search(
            terms=normalized_terms,
            limit=lim,
            offset=offset,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=500,
            detail={"error": "server_misconfigured", "message": str(e)},
        ) from e
    except TapError as e:
        raise HTTPException(
            status_code=502,
            detail={"error": "tap_query_failed", "message": str(e)},
        ) from e

    return project_rows(rows, settings, limit=lim, offset=offset)


async def _form_terms(request: Request) -> list[str]:
    content_type = request.headers.get("content-type", "")
    if "application/x-www-form-urlencoded" not in content_type:
        raise HTTPException(
            status_code=400,
            detail={"error": "invalid_search", "message": "Expected form submission with repeated term fields"},
        )
    body = (await request.body()).decode("utf-8")
    parsed = urllib.parse.parse_qs(body, keep_blank_values=True)
    return parsed.get("term", [])


_route_settings = Settings()
_root = _route_settings.http_path_prefix
_docs_url = f"{_root}/docs" if _root else "/docs"
_redoc_url = f"{_root}/redoc" if _root else "/redoc"
_openapi_url = f"{_root}/internal/openapi.json" if _root else "/internal/openapi.json"

app = FastAPI(
    title="Hammrly Catalog",
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
