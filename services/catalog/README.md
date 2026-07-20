# Hammrly Catalog

TAP-backed read API for Software Discovery records used by the Browser GUI.

The catalog service is a thin query facade over the SKA Software Discovery
Metadata Model v1.0 from the
[SKA SRC-MM Software Data Model](https://gitlab.com/ska-telescope/src/src-mm/ska-src-mm-software-data-model)
repository. It accepts POST-only form searches, generates bounded ADQL, queries
a configured TAP sync endpoint, and returns a compact UI projection of the
underlying Software Discovery records.

## Quick start

```bash
cd services/catalog
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

export HAMMRLY_TAP_SYNC_URL='https://example.org/tap/sync'
export HAMMRLY_TAP_SEARCH_COLUMNS='uri,description,tools_included,status,supported_modes'
export HAMMRLY_TAP_COLUMN_URI='uri'
export HAMMRLY_TAP_COLUMN_DESCRIPTION='description'
export HAMMRLY_TAP_COLUMN_STATUS='status'
export HAMMRLY_TAP_COLUMN_TOOLS_INCLUDED='tools_included'
export HAMMRLY_TAP_COLUMN_SUPPORTED_MODES='supported_modes'
export HAMMRLY_TAP_COLUMN_CPU_ARCHITECTURE='cpu_architecture'
export HAMMRLY_TAP_COLUMN_MIN_MEMORY='min_memory'
export HAMMRLY_TAP_COLUMN_RECOMMENDED_MEMORY='recommended_memory'
export HAMMRLY_TAP_COLUMN_REQUIRES_GPU='requires_gpu'
export HAMMRLY_JWT_DEV_HMAC_SECRET='your-dev-secret-at-least-32-chars-long!!'   # dev only

hammrly-catalog
# or: python -m hammrly_catalog.main
```

- **OpenAPI**: `/.well-known/openapi.json`
- **Software search**: `POST /v1/software/query`

Default listen port is **8082**.

## Software Discovery model

The upstream Software Discovery model describes each software package version as
an immutable `Software` snapshot identified by a `uri` in the form
`{publisher}:{name}:{version}`. Each record includes discovery metadata,
data compatibility, resource requirements, provenance, and one or more
deployment artifacts.

Catalog expects deployments to expose those records through a TAP table or view,
defaulting to `software_discovery`. The service does not store or register
software itself; it only searches the configured TAP endpoint and normalizes the
results for Hammrly clients.

The compact response projection includes the fields the Browser needs for
selection and filtering:

- `id` from Software Discovery `uri`
- `name` derived from `uri`
- `description`
- `status`
- `tools_included`
- `supported_modes`
- `cpu_architecture`
- `memory.min` and `memory.recommended`
- `gpu_required` from `requires_gpu`

## Search

Repeated `term` fields are ANDed together:

```bash
curl -X POST http://localhost:8082/v1/software/query \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  --data-urlencode "term=gpu" \
  --data-urlencode "term=radio"
```

Terms are matched against deployer-configured TAP text columns. The Helm chart
defaults to `uri`, `description`, `tools_included`, `status`, and
`supported_modes`, but the service itself only uses columns supplied through
configuration. It never accepts raw ADQL from the Browser GUI.

## Configuration

Environment variables use the `HAMMRLY_` prefix.

| Variable | Default | Description |
|----------|---------|-------------|
| `HAMMRLY_TAP_SYNC_URL` | _(unset)_ | TAP sync endpoint used for ADQL queries. |
| `HAMMRLY_TAP_TABLE` | `software_discovery` | TAP table/view to query. |
| `HAMMRLY_TAP_SEARCH_COLUMNS` | _(unset)_ | Comma-separated text columns searched for every submitted term. |
| `HAMMRLY_TAP_COLUMN_*` | _(unset)_ | Column mappings for the compact response projection, e.g. `HAMMRLY_TAP_COLUMN_URI=uri`. |
| `HAMMRLY_TAP_TIMEOUT_SECONDS` | `10` | TAP request timeout. |
| `HAMMRLY_LIST_DEFAULT_LIMIT` | `50` | Default response limit. |
| `HAMMRLY_LIST_MAX_LIMIT` | `200` | Maximum response limit. |
| `HAMMRLY_SEARCH_MAX_TERMS` | `8` | Maximum repeated `term` fields. |
| `HAMMRLY_SEARCH_MAX_TERM_LENGTH` | `64` | Maximum length for each term. |
| `HAMMRLY_JWT_*` | — | Same JWT validation model as gateway/query. Default required scope is `hammrly:catalog:read`. |

## Tests

```bash
python3 -m pytest tests/ -v
```
