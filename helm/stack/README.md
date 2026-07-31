# Hammrly stack (`helm/stack`)

Umbrella chart that installs **gateway**, **orchestrator**, **query**, and **catalog** as subcharts. It does **not** deploy Redis, PostgreSQL, or TAP; point `redisUrl`, database URLs, and `catalog.tap.syncUrl` at your infrastructure (or add your own deps chart).

## Layout

All Helm charts live under **`helm/`**:

| Path | Role |
|------|------|
| `helm/gateway`, `helm/orchestrator`, `helm/query`, `helm/catalog` | Component charts |
| **`helm/stack`** | This umbrella chart |

Keeping the stack here avoids scattering charts between the repo root and `helm/`.

## HTTP exposure (optional)

The **gateway**, **query**, and **catalog** subcharts can expose HTTP via **`ingress`** (classic `networking.k8s.io/v1` Ingress) and/or **`httpRoute`** (Gateway API). Both are **disabled by default**.

- **`gateway.ingress`** / **`query.ingress`** / **`catalog.ingress`**: set `enabled: true` and provide `hosts` (each with `paths` and `pathType`). Optionally set `className`, `annotations`, and `tls`.
- **`gateway.httpRoute`** / **`query.httpRoute`** / **`catalog.httpRoute`**: set `enabled: true` and **`parentRefs`** pointing at your `Gateway` (or compatible parent). Optionally set `hostnames`, override `matches`, `filters`, or `backendRefs`. Use **`apiVersion`** if your cluster serves `HTTPRoute` as `v1beta1` instead of `v1`.

Install Gateway API CRDs and a controller (e.g. Envoy Gateway, Cilium, Contour) before relying on `HTTPRoute`.

## Orchestrator database (required)

The orchestrator **requires** PostgreSQL via `HAMMRLY_DATABASE_URL` (assembled from `database.url` + Secret or set as a full dev DSN).

**Production (recommended):**

1. Put **only** `username` and `password` in a Kubernetes **Secret** (key names via **`orchestrator.database.secretKeys`**).
2. Set **`orchestrator.database.url`** to the **non-credential** segment `host:port/dbname` (no scheme, no userinfo), e.g. `postgresql.hammrly.svc.cluster.local:5432/hammrly`.
3. Set **`orchestrator.database.existingSecret`** to that Secret’s name.

The chart sets `HAMMRLY_DATABASE_URL=postgresql+psycopg2://<user>:<password>@<url>`. Passwords with `@`, `:`, `/`, etc. may need URL-encoding in the Secret values.


**Dev / CI (no Secret):** set **`orchestrator.database.url`** to a **full** SQLAlchemy DSN (must contain **`://`**, e.g. `postgresql+psycopg2://user:pass@localhost:5432/hammrly`). That mode ignores **`existingSecret`**.

See [`values.yaml`](values.yaml) under **`orchestrator.database`**.

## Query database (required)

The query service uses the same **`database` / `url` / `existingSecret` / `secretKeys`** pattern as the orchestrator: either a **full DSN** in **`query.database.url`** (must contain **`://`**) or **`host:port/dbname`** plus a Secret for **username** and **password** only. The chart sets **`HAMMRLY_DATABASE_URL`** the same way (`postgresql+psycopg2://…`). Prefer a **read-only** or **replica** role for production.

See **`query.database`** in [`values.yaml`](values.yaml).

Set **`query.redisUrl`** to the same Redis instance as gateway/orchestrator so `GET /v1/jobs/{job_id}` can fall back to the job index during the ingestion window.

Example Secret (credentials only):

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: hammrly-orchestrator-db
  namespace: hammrly   # same as Helm release namespace
type: Opaque
stringData:
  username: hammrly
  password: your-db-password
```

Example install flags (shared Secret; often the same DB host and credentials as the orchestrator):

```bash
--set orchestrator.database.existingSecret=hammrly-orchestrator-db \
--set orchestrator.database.url=postgresql.hammrly.svc.cluster.local:5432/hammrly \
--set query.database.existingSecret=hammrly-orchestrator-db \
--set query.database.url=postgresql.hammrly.svc.cluster.local:5432/hammrly
```

## Prerequisites

- Helm 3.14+
- Images built from the repo (see Dockerfiles under each service).
- **Orchestrator** `k8sWorkloadNamespace` is the namespace where user Jobs/Services/Ingresses are created. Defaults to the release namespace. RBAC `Role`/`RoleBinding` are created in that namespace; the workload `ServiceAccount` lives in the release namespace (cross-namespace binding when the two differ).

## Build images

From the **repository root**:

```bash
docker build -f services/gateway/Dockerfile -t hammrly/gateway:0.1.0 .
docker build -f services/orchestrator/Dockerfile -t hammrly/orchestrator:0.1.0 .
docker build -f services/query/Dockerfile -t hammrly/query:0.1.0 .
docker build -f services/catalog/Dockerfile -t hammrly/catalog:0.1.0 .
```

Push to your registry and set `gateway.image.repository` (etc.) accordingly.

## Package dependencies

Vendor subcharts into `charts/`:

```bash
cd helm/stack
helm dependency update
```

## Install from GHCR (OCI)

Release builds publish charts to GitHub Container Registry as OCI artifacts:

`oci://ghcr.io/<owner>/<repo>/charts`

```bash
# Public packages: no login. Private: helm registry login ghcr.io -u USER --password-stdin
helm install hammrly oci://ghcr.io/at88mph/hammrly/charts/hammrly-stack \
  --version 0.2.0 \
  -n hammrly --create-namespace \
  -f values.yaml \
  --set gateway.redisUrl=redis://your-redis:6379/0 \
  --set orchestrator.redisUrl=redis://your-redis:6379/0 \
  --set orchestrator.database.url='postgresql+psycopg2://user:pass@postgres:5432/hammrly' \
  --set query.redisUrl='redis://your-redis:6379/0' \
  --set query.database.url='postgresql+psycopg2://user:pass@postgres:5432/hammrly' \
  --set catalog.tap.syncUrl='https://example.tap.host/tap/sync' \
  --set gateway.jwt.devHmacSecret='use-secrets-in-prod' \
  --set query.jwt.devHmacSecret='use-secrets-in-prod' \
  --set catalog.jwt.devHmacSecret='use-secrets-in-prod'
```

Individual charts: `hammrly-gateway`, `hammrly-orchestrator`, `hammrly-query`, `hammrly-catalog`, `hammrly-portal`.

## Install from source

From **`helm/stack`** (demo: full DSN in `database.url` for orchestrator — must contain `://`):

```bash
cd helm/stack
helm install hammrly . -n hammrly --create-namespace \
  -f values.yaml \
  --set gateway.redisUrl=redis://your-redis:6379/0 \
  --set orchestrator.redisUrl=redis://your-redis:6379/0 \
  --set orchestrator.database.url='postgresql+psycopg2://user:pass@postgres:5432/hammrly' \
  --set query.redisUrl='redis://your-redis:6379/0' \
  --set query.database.url='postgresql+psycopg2://user:pass@postgres:5432/hammrly' \
  --set catalog.tap.syncUrl='https://example.tap.host/tap/sync' \
  --set gateway.jwt.devHmacSecret='use-secrets-in-prod' \
  --set query.jwt.devHmacSecret='use-secrets-in-prod' \
  --set catalog.jwt.devHmacSecret='use-secrets-in-prod'
```

Or from the repo root: `helm install hammrly ./helm/stack ...` (add `-f ./helm/stack/values.yaml` if you use the default values file).

Use `jwt.jwksUrl` / issuer / audience in production instead of `jwt.devHmacSecret`.

## Session ingress auth (optional)

Interactive session Ingresses can be protected with **oauth2-proxy** via the orchestrator sub-chart. Enable on the orchestrator values tree only (the stack chart does not add a separate oauth2-proxy dependency):

```yaml
orchestrator:
  ingress:
    host: sessions.example.com
    className: traefik
    auth:
      enabled: true
      profile: traefik   # traefik | nginx | custom
      jwt:
        issuer: "https://idp.example.com/"
        audience: "hammrly"
  oauth2-proxy:
    enabled: true
    ingressHost: sessions.example.com
    clientId: hammrly-sessions
    existingSecret: oauth2-proxy
    jwt:
      issuer: "https://idp.example.com/"
      audience: "hammrly"
```

See [`helm/orchestrator/README.md`](../orchestrator/README.md) for profile details and browser authentication flow.

## Individual charts

Install only one service from `helm/gateway`, `helm/orchestrator`, `helm/query`, or `helm/catalog` if needed.
