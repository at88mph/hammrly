# Hammrly portal Helm chart

Deploys the Hammrly **portal** — a static browser UI (nginx) for listing sessions, browsing the software catalog, and submitting new sessions via the gateway API.

The chart renders a **Deployment**, **Service**, and **ConfigMap** (`config.json`). Optional **Ingress** and **HTTPRoute** resources expose the UI outside the cluster.

## Install

**Standalone:**

```bash
helm install hammrly-portal ./helm/portal -f my-values.yaml
```

**Via the stack umbrella chart** ([`helm/stack`](../stack/)):

```bash
helm install hammrly ./helm/stack -f my-values.yaml
```

Set values under the `portal:` key (see [Stack integration](#stack-integration)).

## What gets deployed

| Resource | Always | Notes |
|----------|--------|-------|
| `Deployment` | yes | Single container; mounts `config.json` from ConfigMap |
| `Service` | yes | ClusterIP on `service.port` (default 8080) |
| `ConfigMap` | yes | Frontend runtime config (`config.json`) |
| `ConfigMap` (nginx) | yes | nginx `portal.conf` from `httpPathPrefix` (mounted read-only; image envsubst disabled) |
| `Ingress` | if `ingress.enabled` | Classic `networking.k8s.io/v1` |
| `HTTPRoute` | if `httpRoute.enabled` | Gateway API; requires `parentRefs` |

Health probes hit `/` on the container port. The portal image is built with base path `/hammrly/portal/` by default; align external routes with that path (see [Path prefix](#path-prefix)).

## Configuration reference

All options live in [`values.yaml`](values.yaml). Summary by section:

### Deployment and naming

| Value | Default | Description |
|-------|---------|-------------|
| `replicaCount` | `1` | Pod replicas. The UI is stateless; increase for availability. |
| `nameOverride` | `""` | Short name override for labels and resource names. |
| `fullnameOverride` | `""` | Full resource name override (truncated to 63 characters). |

### Container image

| Value | Default | Description |
|-------|---------|-------------|
| `image.repository` | `registry.gitlab.com/djenkins.cadc/hammrly/portal` | Container image. |
| `image.tag` | chart `appVersion` | Image tag. |
| `image.pullPolicy` | `IfNotPresent` | Kubernetes pull policy. |

### Service

| Value | Default | Description |
|-------|---------|-------------|
| `service.type` | `ClusterIP` | Service type. |
| `service.port` | `8080` | Service port and Ingress/HTTPRoute backend port. |

### Security contexts

| Value | Default | Description |
|-------|---------|-------------|
| `podSecurityContext` | `{}` | Pod-level `securityContext` on the Deployment pod spec. |
| `securityContext` | `{}` | Container-level `securityContext` on the portal container. |

Example (restricted pod):

```yaml
podSecurityContext:
  runAsNonRoot: true
  fsGroup: 101
securityContext:
  allowPrivilegeEscalation: false
  readOnlyRootFilesystem: false
  runAsUser: 101
  runAsGroup: 101
```

### Path prefix

| Value | Default | Description |
|-------|---------|-------------|
| `httpPathPrefix` | `"/hammrly/portal"` | URL path prefix for the UI. Drives the **nginx ConfigMap** (asset alias + SPA fallback), health probes, and should match **`ingress`/`httpRoute` paths** and the image **`VITE_BASE_PATH`** (with trailing slash at build time, e.g. `/hammrly/portal/`). |

### nginx (reverse proxy)

The portal pod listens on plain HTTP. TLS terminates at your ingress or other edge proxy. The rendered nginx config disables absolute redirects (so nginx does not emit `http://` locations based on the pod’s `$scheme`) and optionally trusts **`X-Forwarded-For`** from in-cluster proxies.

| Value | Default | Description |
|-------|---------|-------------|
| `nginx.trustedProxyCidrs` | RFC1918 + loopback | CIDRs allowed to set `X-Forwarded-For` via `real_ip`. Set to `[]` to omit `real_ip` directives. |

Ensure your ingress forwards **`X-Forwarded-Proto`**, **`X-Forwarded-Host`**, and **`X-Forwarded-For`** to the portal Service (most controllers do this by default). Do **not** strip `httpPathPrefix` at the edge unless you also change `VITE_BASE_PATH` and the nginx alias layout.

### Frontend config (`config`)

Values under `config` are serialized into `config.json` and mounted at `/usr/share/nginx/html/config.json`. The portal loads this at runtime; see [`services/portal`](../../services/portal/) for UI behaviour.

| Value | Required | Description |
|-------|----------|-------------|
| `config.queryBaseUrl` | yes | Public base URL for the **query** API (session list/detail). |
| `config.gatewayBaseUrl` | yes | Public base URL for the **gateway** API (session submission). |
| `config.catalogBaseUrl` | yes | Public base URL for the **catalog** API (software search). |
| `config.defaultSearchTerms` | no | Initial catalog search terms in the UI (default `["desktop"]`). |
| `config.imageMap` | no | Map of catalog image IDs to container image references used when submitting jobs. |
| `config.oidcProviders` | no | OIDC login providers (see below). Default `[]`. |
| `config.devBypass` | no | Dev-only HS256 JWT auth when no OIDC providers are configured (see below). |

**`config.oidcProviders`** — array of objects:

| Field | Description |
|-------|-------------|
| `id` | Stable provider id (used in callback routing). |
| `displayName` | Label shown on the login page. |
| `authority` | OIDC issuer URL (e.g. `https://idp.example.com/`). |
| `clientId` | Public OIDC client id (browser flow). |
| `scope` | OIDC scope string; must include Hammrly API scopes (see [OIDC client registration](#oidc-client-registration)). |
| `extraQueryParams` | Optional map of extra authorize-query parameters. |

### OIDC client registration

Register a **public OIDC client** (Authorization Code + **PKCE**, no client secret) with each identity provider listed in `config.oidcProviders`. Every provider uses the **same callback path** on the portal’s public origin; the portal records which provider the user chose in `sessionStorage` before redirecting to the IdP.

#### URL formula

Let:

- **`ORIGIN`** — public browser origin of the portal (scheme + host, no path), e.g. `https://sessions.example.com`
- **`PREFIX`** — UI path prefix with **no** trailing slash. Must match Helm `httpPathPrefix` and the image `VITE_BASE_PATH` / `PORTAL_HTTP_PATH_PREFIX` (without trailing slash), e.g. `/hammrly/portal`

| Purpose | Path (relative to `PREFIX`) | Full URL |
|---------|----------------------------|----------|
| **Redirect URI** (required) | `/auth/callback` | `{ORIGIN}{PREFIX}/auth/callback` |
| Login page | `/login` | `{ORIGIN}{PREFIX}/login` |
| Post-logout redirect (recommended) | `/login` | `{ORIGIN}{PREFIX}/login` |

The portal sets `redirect_uri` to the **Redirect URI** row at runtime (`getRedirectUri()` in the portal source). Register that exact URL on the IdP client. **Silent token refresh** (`automaticSilentRenew`) uses the same redirect URI by default.

#### Examples

| Deployment | `httpPathPrefix` | Register redirect URI |
|------------|------------------|-------------------------|
| Default stack / Helm values | `/hammrly/portal` | `https://sessions.example.com/hammrly/portal/auth/callback` |
| Root path (`PREFIX` empty) | `""` (image built with `VITE_BASE_PATH=/`) | `https://portal.example.com/auth/callback` |
| Local Vite dev server | `/` (default dev build) | `http://localhost:5173/auth/callback` |

If ingress serves the portal at `https://sessions.example.com/hammrly/portal` (Prefix match), use that host in `ORIGIN` — not an internal Service DNS name.

#### IdP client settings

| Setting | Value |
|---------|--------|
| Application type | Single-page application (SPA) / public client |
| Grant type | Authorization code |
| PKCE | Required (`S256`) |
| Client authentication | None (no client secret in the browser) |
| Redirect URI(s) | `{ORIGIN}{PREFIX}/auth/callback` (exact match; no wildcards unless your IdP documents them) |
| Post-logout redirect URI(s) | `{ORIGIN}{PREFIX}/login` (if the IdP supports end-session / RP-initiated logout) |

#### Access token scopes

The portal sends the `scope` string from each `oidcProviders[]` entry on authorize. Tokens must be accepted by **gateway**, **query**, and **catalog** (`HAMMRLY_JWT_*` / JWKS on those services). Include at least:

```text
openid profile hammrly:jobs:read hammrly:jobs:submit hammrly:catalog:read
```

Adjust `profile` / `email` to what your IdP issues. Optional tenant claim: `hammrly_tenant_id` (same claim name as gateway/query `JWT_TENANT_CLAIM`).

#### Multiple providers

Each `oidcProviders[].id` can point to a different IdP or the same federation with different `clientId` / `authority`. Register the **same** redirect URI on every OIDC client the portal uses. Users pick a provider on `/login`; only one provider is active per browser tab.

#### Checklist

1. Ingress (or HTTPRoute) exposes `{ORIGIN}{PREFIX}` and forwards `X-Forwarded-Proto` / `Host`.
2. Portal image `VITE_BASE_PATH` matches `PREFIX` (with trailing slash at build time, e.g. `/hammrly/portal/`).
3. IdP client redirect URI = `{ORIGIN}{PREFIX}/auth/callback`.
4. Gateway, query, and catalog trust the IdP JWT (JWKS URL, issuer, audience) and required scopes.
5. `HAMMRLY_CORS_ORIGINS` on those APIs includes `{ORIGIN}` (portal origin for API calls).

**`config.devBypass`** — for non-production only; omitted from `config.json` when unset:

| Field | Description |
|-------|-------------|
| `enabled` | Enable dev bypass login. |
| `hmacSecret` | Shared secret; must match `HAMMRLY_JWT_DEV_HMAC_SECRET` on gateway/query/catalog. |
| `userId` | Optional JWT `sub` claim. |
| `tenantId` | Optional tenant claim. |

Production deployments should use **`oidcProviders`** and set **`devBypass.enabled: false`**. Gateway, query, and catalog must accept the same JWT issuer/audience (or dev HMAC in dev).

### HTTP exposure — Ingress

Both Ingress and HTTPRoute are optional; enable one or both depending on your cluster.

| Value | Default | Description |
|-------|---------|-------------|
| `ingress.enabled` | `true` | Render an Ingress resource. |
| `ingress.className` | `""` | `ingressClassName` when non-empty. |
| `ingress.annotations` | `{}` | Ingress metadata annotations. |
| `ingress.hosts` | `[]` | Host rules; each entry has `host` and `paths` (`path`, `pathType`). |
| `ingress.tls` | `[]` | TLS entries (`hosts`, `secretName`). |

Example:

```yaml
ingress:
  enabled: true
  className: traefik
  hosts:
    - host: sessions.example.com
      paths:
        - path: /hammrly/portal
          pathType: Prefix
  tls:
    - hosts:
        - sessions.example.com
      secretName: sessions-tls
```

### HTTP exposure — HTTPRoute (Gateway API)

Install Gateway API CRDs and a controller (Envoy Gateway, Cilium, Contour, etc.) before use.

| Value | Default | Description |
|-------|---------|-------------|
| `httpRoute.enabled` | `false` | Render an `HTTPRoute`. |
| `httpRoute.apiVersion` | `gateway.networking.k8s.io/v1` | API version; use `gateway.networking.k8s.io/v1beta1` on older clusters. |
| `httpRoute.annotations` | `{}` | HTTPRoute metadata annotations. |
| `httpRoute.extraLabels` | `{}` | Extra labels on the HTTPRoute. |
| `httpRoute.parentRefs` | `[]` | **Required when enabled** — parent Gateway (or compatible) references. |
| `httpRoute.hostnames` | `[]` | Optional hostname list. |
| `httpRoute.matches` | `[{ path: { type: PathPrefix, value: / } }]` | Path (and optional header) matches; set `value` to `/hammrly/portal` in typical installs. |
| `httpRoute.filters` | `[]` | Gateway API filters (redirect, request header, etc.). |
| `httpRoute.backendRefs` | `[]` | Custom backends; when empty, routes to this chart’s Service on `service.port`. |

Example:

```yaml
httpRoute:
  enabled: true
  parentRefs:
    - name: eg
      namespace: envoy-gateway-system
      sectionName: http
  hostnames:
    - sessions.example.com
  matches:
    - path:
        type: PathPrefix
        value: /hammrly/portal
```

## Stack integration

When installed as part of [`helm/stack`](../stack/), prefix all values with `portal:`:

```yaml
portal:
  ingress:
    enabled: true
    className: traefik
    hosts:
      - host: sessions.example.com
        paths:
          - path: /hammrly/portal
            pathType: Prefix
  config:
    queryBaseUrl: "https://sessions.example.com/hammrly/query"
    gatewayBaseUrl: "https://sessions.example.com/hammrly/gateway"
    catalogBaseUrl: "https://sessions.example.com/hammrly/catalog"
    defaultSearchTerms:
      - desktop
    oidcProviders:
      - id: cadc
        displayName: CADC SSO
        authority: "https://idp.example.com/"
        clientId: hammrly-portal
        scope: "openid profile hammrly:jobs:read hammrly:jobs:submit hammrly:catalog:read"
```

Ensure **gateway**, **query**, and **catalog** are reachable at the URLs in `config.*BaseUrl` and allow CORS from the portal origin (`HAMMRLY_CORS_ORIGINS` on those services).

## Example — minimal production values

```yaml
replicaCount: 2

ingress:
  enabled: true
  className: nginx
  hosts:
    - host: sessions.example.com
      paths:
        - path: /hammrly/portal
          pathType: Prefix

config:
  queryBaseUrl: "https://sessions.example.com/hammrly/query"
  gatewayBaseUrl: "https://sessions.example.com/hammrly/gateway"
  catalogBaseUrl: "https://sessions.example.com/hammrly/catalog"
  oidcProviders:
    - id: prod-idp
      displayName: Sign in
      authority: "https://idp.example.com/"
      clientId: hammrly-portal
      scope: "openid profile hammrly:jobs:read hammrly:jobs:submit hammrly:catalog:read"
  devBypass:
    enabled: false
```

## Related documentation

- Portal application: [`services/portal/README.md`](../../services/portal/README.md)
- Stack umbrella chart: [`helm/stack/README.md`](../stack/README.md)
- Gateway / query / catalog charts: [`helm/gateway`](../gateway/), [`helm/query`](../query/), [`helm/catalog`](../catalog/)
