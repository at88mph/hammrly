# Catalog service — specification

The **catalog** service exposes a Browser-friendly read API over a configured IVOA TAP service. It does not own Hammrly job metadata and does not write to the orchestrator database.

## Underlying Model

Catalog queries Software Discovery records described by the SKA Software
Discovery Metadata Model v1.0 in the
[SKA SRC-MM Software Data Model](https://gitlab.com/ska-telescope/src/src-mm/ska-src-mm-software-data-model)
repository. The model treats each software package version as an immutable
`Software` snapshot with a `uri` of `{publisher}:{name}:{version}` plus
discovery metadata, data compatibility, resource requirements, provenance, and
deployment artifacts.

The deployed TAP service is expected to expose a flattened table or view over
that model. Catalog is not the registration service and does not persist
Software Discovery records; it translates constrained Browser search forms into
bounded ADQL and projects TAP rows into Hammrly list items.

## Responsibilities

| Concern | Owner |
|---------|-------|
| JWT authentication + read authorization | catalog |
| Translate constrained software search forms into ADQL | catalog |
| Execute bounded TAP sync queries | catalog |
| Normalize SoftwareDiscovery records into compact UI list items | catalog |
| Job submission and lifecycle state | gateway / orchestrator / query |

## HTTP API

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/v1/software/query` | Search software discovery records using repeated form `term` fields. |
| `GET` | `/.well-known/openapi.json` | OpenAPI document. |
| `GET` | `/healthz` | Liveness. |
| `GET` | `/readyz` | Configuration readiness. |

`POST /v1/software/query` accepts `application/x-www-form-urlencoded` bodies:

```text
term=gpu&term=radio
```

Terms are ANDed together. Each term is matched against deployer-configured TAP text columns. The service never accepts raw ADQL from the Browser GUI.

Query parameters:

- `limit` default `50`, capped by `HAMMRLY_LIST_MAX_LIMIT`
- `offset` default `0`; implemented by fetching `limit + offset` rows from TAP and slicing locally

## Response Projection

Search results are compact list items derived from the Software Discovery model,
including:

- `id` from `uri`
- `name` derived from `uri`
- `description`
- `status`
- `tools_included`
- `supported_modes`
- `cpu_architecture`
- `memory.min` and `memory.recommended`
- `gpu_required`

## TAP Notes

The TAP table and column names are deployment-specific and configured through
environment variables. Result columns are discovered from configured
`HAMMRLY_TAP_COLUMN_*` variables; the service does not carry its own default
projection column list. The Helm chart provides defaults for a flattened TAP
view over the Software Discovery model. If a TAP service stores nested JSON
differently, expose a view that maps to the configured columns.
