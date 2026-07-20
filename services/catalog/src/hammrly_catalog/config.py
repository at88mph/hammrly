from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Optional

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_ADQL_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*$")
_COLUMN_NAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")
_TAP_COLUMN_ENV_PREFIX = "HAMMRLY_TAP_COLUMN_"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="HAMMRLY_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    host: str = Field(default="0.0.0.0")
    port: int = Field(default=8082, ge=1, le=65535)
    log_level: str = Field(default="info")

    tap_sync_url: Optional[str] = Field(
        default=None,
        description="TAP sync endpoint, e.g. https://example.org/tap/sync",
    )
    tap_table: str = Field(
        default="software_discovery",
        description="ADQL table/view containing SoftwareDiscovery metadata.",
    )
    tap_response_format: str = Field(
        default="json",
        description="TAP FORMAT parameter. The service currently expects a JSON TAP result.",
    )
    tap_timeout_seconds: float = Field(default=10.0, gt=0)
    tap_cache_ttl_seconds: float = Field(
        default=300.0,
        ge=0,
        description="Seconds to cache the full TAP table in memory. 0 disables caching.",
    )
    tap_cache_max_rows: int = Field(
        default=1000,
        ge=1,
        le=10000,
        description="Maximum rows fetched when refreshing the in-memory TAP cache.",
    )

    tap_search_columns: str = Field(
        default="",
        description="Comma-separated text columns searched for every term.",
    )
    tap_columns: dict[str, str] = Field(
        default_factory=dict,
        description=(
            "Logical response field to TAP column mappings. Usually populated "
            "from HAMMRLY_TAP_COLUMN_* environment variables."
        ),
    )

    list_default_limit: int = Field(default=50, ge=1, le=200)
    list_max_limit: int = Field(default=200, ge=1, le=500)
    search_max_terms: int = Field(default=8, ge=1, le=25)
    search_max_term_length: int = Field(default=64, ge=1, le=256)

    jwt_jwks_url: Optional[str] = Field(default=None)
    jwt_issuer: Optional[str] = Field(default=None)
    jwt_audience: Optional[str] = Field(default=None)
    jwt_leeway_seconds: int = Field(default=10, ge=0)
    jwt_dev_hmac_secret: Optional[str] = Field(default=None)
    jwt_required_scopes: str = Field(default="hammrly:catalog:read")
    jwt_require_scope_check: bool = Field(default=True)
    jwt_tenant_claim: str = Field(default="hammrly_tenant_id")
    jwt_user_id_claim: str = Field(default="sub")

    cors_origins: str = Field(default="")
    http_path_prefix: str = Field(default="")

    @field_validator(
        "tap_sync_url",
        "jwt_jwks_url",
        "jwt_issuer",
        "jwt_audience",
        "jwt_dev_hmac_secret",
        mode="before",
    )
    @classmethod
    def _empty_to_none(cls, v: object) -> object:
        if v == "":
            return None
        return v

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

    @model_validator(mode="after")
    def _validate_adql_identifiers(self) -> Settings:
        if not self.tap_columns:
            self.tap_columns = _tap_columns_from_environment(self.model_config.get("env_file"))
        else:
            self.tap_columns = _normalize_tap_columns(self.tap_columns)

        bad_column_names = [
            name for name in self.tap_columns if not _COLUMN_NAME_RE.fullmatch(name)
        ]
        if bad_column_names:
            raise ValueError(
                "TAP column mapping names must be lowercase identifiers; "
                f"invalid: {bad_column_names!r}"
            )

        names = [
            self.tap_table,
            *self.tap_search_columns_list,
            *self.tap_result_columns,
        ]
        bad = [name for name in names if name and not _ADQL_IDENTIFIER_RE.fullmatch(name)]
        if bad:
            raise ValueError(f"TAP table/column names must be simple ADQL identifiers; invalid: {bad!r}")
        return self

    @property
    def tap_search_columns_list(self) -> tuple[str, ...]:
        return tuple(s.strip() for s in self.tap_search_columns.split(",") if s.strip())

    @property
    def tap_result_columns(self) -> tuple[str, ...]:
        return tuple(self.tap_columns.values())

    def tap_column(self, name: str) -> Optional[str]:
        return self.tap_columns.get(name)

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


def _tap_columns_from_environment(env_file: object) -> dict[str, str]:
    values: dict[str, str] = {}
    for source in (*_dotenv_values(env_file), os.environ):
        for key, value in source.items():
            key_upper = str(key).upper()
            if not key_upper.startswith(_TAP_COLUMN_ENV_PREFIX):
                continue
            name = key_upper[len(_TAP_COLUMN_ENV_PREFIX) :].lower()
            column = str(value).strip()
            if name and column:
                values[name] = column
    return _normalize_tap_columns(values)


def _dotenv_values(env_file: object) -> list[dict[str, str]]:
    if not env_file:
        return []

    if isinstance(env_file, (str, Path)):
        paths = [env_file]
    else:
        try:
            paths = list(env_file)
        except TypeError:
            return []

    values: list[dict[str, str]] = []
    for raw_path in paths:
        path = Path(raw_path)
        if not path.exists():
            continue
        parsed: dict[str, str] = {}
        for line in path.read_text(encoding="utf-8").splitlines():
            s = line.strip()
            if not s or s.startswith("#") or "=" not in s:
                continue
            key, value = s.split("=", 1)
            parsed[key.strip()] = value.strip().strip("'\"")
        values.append(parsed)
    return values


def _normalize_tap_columns(columns: dict[str, str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for raw_name, raw_column in columns.items():
        name = str(raw_name).strip().lower().replace("-", "_")
        column = str(raw_column).strip()
        if name and column:
            out[name] = column
    return out
