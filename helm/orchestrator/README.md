# Hammrly orchestrator Helm chart

Deploys the orchestrator worker and optionally a **oauth2-proxy** sub-chart for interactive session ingress authentication.

## Session ingress auth

When `ingress.auth.enabled=true`, the orchestrator stamps **controller-specific annotations** on every per-session Ingress it creates. An optional **oauth2-proxy** sub-chart (`oauth2-proxy.enabled=true`) provides OIDC login and ForwardAuth endpoints.

### Profiles (`ingress.auth.profile`)

| Profile | Ingress annotations | Extra resources |
|---------|---------------------|-----------------|
| `traefik` (default) | `traefik.ingress.kubernetes.io/router.middlewares` | Traefik `Middleware` CRDs (sub-chart) |
| `nginx` | `nginx.ingress.kubernetes.io/auth-url`, `auth-signin`, … | None |
| `custom` | `ingress.auth.annotations` verbatim | None |

Traefik requires `providers.kubernetescrd.allowCrossNamespace=true` when session Ingresses are created in `k8sWorkloadNamespace` different from the release namespace. Prefer deploying oauth2-proxy and Middleware CRDs in the **workload namespace** in that case.

### Example (Traefik + oauth2-proxy)

```yaml
ingress:
  host: sessions.example.com
  className: traefik
  auth:
    enabled: true
    profile: traefik
    jwt:
      issuer: "https://idp.example.com/"
      audience: "hammrly"

oauth2-proxy:
  enabled: true
  ingressHost: sessions.example.com   # must match ingress.host
  ingressClassName: traefik
  authProfile: traefik
  clientId: hammrly-sessions
  existingSecret: oauth2-proxy        # keys: client-secret, cookie-secret
  jwt:
    issuer: "https://idp.example.com/"
    audience: "hammrly"
```

Align `ingress.auth.jwt` / `oauth2-proxy.jwt` with gateway/query JWT issuer settings.

### Browser flow

1. User submits a session via the gateway API (Hammrly JWT).
2. User polls Query until `status=ready`, then opens `access_url`.
3. Ingress controller checks auth via oauth2-proxy; unauthenticated users complete OIDC login.
4. Jupyter runs with `--ServerApp.token=''` when `ingress.auth.disableJupyterToken=true` (default).

### Sub-chart dependency

```bash
cd helm/orchestrator
helm dependency update
```

See [`helm/oauth2-proxy`](../oauth2-proxy/) for sub-chart values.
