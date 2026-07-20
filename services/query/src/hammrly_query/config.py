from __future__ import annotations

from typing import Optional

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from hammrly_query.contract_types import WorkloadKind


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="HAMMRLY_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    host: str = Field(default="0.0.0.0")
    port: int = Field(default=8081, ge=1, le=65535)
    log_level: str = Field(default="info")

    database_url: Optional[str] = Field(
        default=None,
        description="SQLAlchemy URL (read replica or ro user), e.g. postgresql+psycopg2://ro:pass@host:5432/db",
    )
    skip_db_bootstrap: bool = Field(
        default=False,
        description="If true, do not open a DB engine at startup (use dependency_overrides in tests).",
    )

    redis_url: Optional[str] = Field(
        default=None,
        description="Redis URL for job-index fallback on GET /v1/jobs/{job_id}. Omit for Postgres-only.",
    )
    redis_fake: bool = Field(
        default=False,
        description="Use in-memory FakeRedis (tests only).",
    )
    job_index_redis_prefix: str = Field(default="hammrly:jobs:")

    cluster_id: Optional[str] = Field(
        default=None,
        description="If set, only return rows where submissions.cluster_id matches (multi-cluster).",
    )

    interactive_kinds: str = Field(
        default="desktop,notebook,carta,contributed",
        description="Comma-separated workload.kind values for /v1/me/jobs/interactive.",
    )
    list_default_limit: int = Field(default=50, ge=1, le=200)
    list_max_limit: int = Field(default=200, ge=1, le=500)

    jwt_jwks_url: Optional[str] = Field(default=None)
    jwt_issuer: Optional[str] = Field(default=None)
    jwt_audience: Optional[str] = Field(default=None)
    jwt_leeway_seconds: int = Field(default=10, ge=0)
    jwt_dev_hmac_secret: Optional[str] = Field(default=None)
    jwt_required_scopes: str = Field(
        default="hammrly:jobs:read",
        description="Space/comma-separated scopes required in JWT when jwt_require_scope_check is true.",
    )
    jwt_require_scope_check: bool = Field(default=True)
    jwt_tenant_claim: str = Field(default="hammrly_tenant_id")
    jwt_user_id_claim: str = Field(default="sub")

    cors_origins: str = Field(default="")
    http_path_prefix: str = Field(
        default="",
        description=(
            "HTTP path prefix for all routes (e.g. /hammrly/query). "
            "Empty serves API at /. Use with an ingress PathPrefix matching this value."
        ),
    )

    @field_validator("http_path_prefix", mode="before")
    @classmethod
    def _http_path_prefix_strip(cls, v: object) -> object:
        if v is None or v == "":
            return ""
        return str(v).strip()

    @field_validator("http_path_prefix", mode="after")
    @classmethod
    def _normalize_http_path_prefix(cls, v: str) -> str:
        if not v:
            return ""
        p = v if v.startswith("/") else f"/{v}"
        p = p.rstrip("/")
        return "" if p == "/" else p

    @field_validator("redis_url", mode="before")
    @classmethod
    def _redis_url_empty(cls, v: object) -> object:
        if v == "":
            return None
        return v

    @field_validator("jwt_jwks_url", "jwt_issuer", "jwt_audience", "jwt_dev_hmac_secret", mode="before")
    @classmethod
    def _empty_to_none(cls, v: object) -> object:
        if v == "":
            return None
        return v

    @field_validator("cluster_id", mode="before")
    @classmethod
    def _cluster_empty(cls, v: object) -> object:
        if v == "":
            return None
        return v

    @model_validator(mode="after")
    def _interactive_kinds_match_contract(self) -> Settings:
        allowed = {m.value for m in WorkloadKind}
        bad = [k for k in self.interactive_kinds_list if k not in allowed]
        if bad:
            raise ValueError(
                "HAMMRLY_INTERACTIVE_KINDS must only list workload.kind values from "
                f"contracts/job-submission/v1/schema.json ($defs.WorkloadKind); unknown: {bad!r}. "
                f"Allowed: {sorted(allowed)}"
            )
        return self

    @property
    def required_scope_list(self) -> list[str]:
        parts: list[str] = []
        for chunk in self.jwt_required_scopes.replace(",", " ").split():
            s = chunk.strip()
            if s:
                parts.append(s)
        return parts

    @property
    def interactive_kinds_list(self) -> tuple[str, ...]:
        return tuple(s.strip() for s in self.interactive_kinds.split(",") if s.strip())

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]
