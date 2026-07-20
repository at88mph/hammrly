from __future__ import annotations

from typing import Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="HAMMRLY_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    host: str = Field(default="0.0.0.0", description="Bind address.")
    port: int = Field(default=8080, ge=1, le=65535)
    log_level: str = Field(default="info")

    redis_url: str = Field(default="redis://127.0.0.1:6379/0")
    redis_stream_key: str = Field(default="hammrly:job-submissions")
    campaign_stream_key: str = Field(default="hammrly:campaign-submissions")
    campaign_schema_path: Optional[str] = Field(
        default=None,
        description="Path to job-campaign JSON Schema.",
    )
    campaign_schema_version: str = Field(default="1.0")
    campaign_max_inline_items: int = Field(default=10_000, ge=1, le=100_000)
    campaign_idempotency_redis_prefix: str = Field(default="hammrly:gateway:campaign-idempotency:")
    query_campaign_status_path_template: str = Field(
        default="/v1/me/campaigns/{campaign_id}",
        description="Path template for status_url in 202 responses (Query API).",
    )
    query_job_status_path_template: str = Field(
        default="/v1/jobs/{job_id}",
        description="Path template for status_url in POST /v2/session 202 responses (Query API).",
    )
    query_public_base_url: Optional[str] = Field(
        default=None,
        description=(
            "Optional public Query API origin (e.g. https://query.example.com). "
            "When set, session status_url is an absolute URL; otherwise a path only."
        ),
    )
    redis_fake: bool = Field(
        default=False,
        description="Use in-memory FakeRedis (no TCP; for tests).",
    )

    contract_schema_path: Optional[str] = Field(
        default=None,
        description=(
            "Path to job-submission JSON Schema. Default: repository "
            "contracts/job-submission/v1/schema.json relative to cwd."
        ),
    )
    submission_schema_version: str = Field(
        default="1.0",
        description="Value for envelope schema_version (major.minor).",
    )
    ephemeral_storage_default: str = Field(
        default="20",
        description="Default workload.resources.ephemeral_storage quantity in GB when callers omit it.",
    )
    ephemeral_storage_max: str = Field(
        default="20",
        description="Maximum accepted workload.resources.ephemeral_storage quantity in GB.",
    )

    jwt_jwks_url: Optional[str] = Field(
        default=None,
        description="OIDC JWKS URL (RS256). Omit when using dev HMAC secret.",
    )
    jwt_issuer: Optional[str] = Field(default=None, description="Expected iss claim.")
    jwt_audience: Optional[str] = Field(default=None, description="Expected aud claim (if set, verified).")
    jwt_leeway_seconds: int = Field(default=10, ge=0)
    jwt_dev_hmac_secret: Optional[str] = Field(
        default=None,
        description="**Dev only**: HS256 symmetric secret; disables JWKS when set.",
    )
    jwt_required_scopes: str = Field(
        default="hammrly:jobs:submit",
        description="Space or comma separated scopes; required when jwt_require_scope_check is true.",
    )
    jwt_require_scope_check: bool = Field(
        default=True,
        description="If false, skip scope checks (emergency / misconfigured IdP).",
    )
    jwt_tenant_claim: str = Field(
        default="hammrly_tenant_id",
        description="JWT claim for tenant id when not supplied in request body.",
    )
    jwt_user_id_claim: str = Field(
        default="sub",
        description="JWT claim used as envelope user_id.",
    )

    tenant_body_allowed: bool = Field(
        default=True,
        description="Allow tenant_id in JSON body when JWT has no tenant claim.",
    )
    tenant_mismatch_forbidden: bool = Field(
        default=True,
        description="If JWT has tenant claim and body sends tenant_id, they must match.",
    )

    idempotency_ttl_seconds: int = Field(default=86_400, ge=60)
    idempotency_redis_prefix: str = Field(default="hammrly:gateway:idempotency:")
    idempotency_lock_seconds: int = Field(default=120, ge=10)

    job_index_redis_prefix: str = Field(default="hammrly:jobs:")
    job_index_ttl_seconds: int = Field(default=86_400, ge=60)

    cors_origins: str = Field(
        default="",
        description="Comma-separated allowed origins; empty disables CORS middleware.",
    )
    http_path_prefix: str = Field(
        default="",
        description=(
            "HTTP path prefix for all routes (e.g. /hammrly/gateway). "
            "Empty serves API at /. Use with an ingress PathPrefix matching this value."
        ),
    )

    @field_validator("query_public_base_url", mode="before")
    @classmethod
    def _query_public_base_url_strip(cls, v: object) -> object:
        if v is None or v == "":
            return None
        return str(v).strip().rstrip("/") or None

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

    @field_validator("ephemeral_storage_default", "ephemeral_storage_max", mode="after")
    @classmethod
    def _normalize_ephemeral_storage_quantity(cls, v: str) -> str:
        s = str(v).strip()
        return s if s else "20"

    @field_validator("jwt_jwks_url", "jwt_issuer", "jwt_audience", "jwt_dev_hmac_secret", mode="before")
    @classmethod
    def _empty_to_none(cls, v: object) -> object:
        if v == "":
            return None
        return v

    @property
    def required_scope_list(self) -> list[str]:
        parts: list[str] = []
        for chunk in self.jwt_required_scopes.replace(",", " ").split():
            s = chunk.strip()
            if s:
                parts.append(s)
        return parts

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]
