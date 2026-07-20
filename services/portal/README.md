# Hammrly Portal

Browser UI for managing interactive Hammrly sessions. Calls **query**, **catalog**, and **gateway** APIs.

## Development

```bash
cd services/portal
npm install
npm run dev
```

Open http://localhost:5173. Configure API endpoints and auth in [`public/config.json`](public/config.json).

Local dev uses **dev bypass** auth (HS256 JWT) when `devBypass.enabled` is true and no OIDC providers are configured. Match `hmacSecret` to `HAMMRLY_JWT_DEV_HMAC_SECRET` on gateway/query/catalog.

## Build

```bash
npm run build
```

Production base path defaults to `/hammrly/portal/` when built in Docker (`VITE_BASE_PATH`). Override with `--build-arg VITE_BASE_PATH=/your/prefix/` when building the image; **`httpPathPrefix` in the Helm chart must match** (without trailing slash). For non-Kubernetes runs, set `PORTAL_HTTP_PATH_PREFIX` (no trailing slash) to match.

## Stack integration

- **query** — session list and detail
- **catalog** — software image picker
- **gateway** — create session

Enable CORS on all three backends for the portal origin (`HAMMRLY_CORS_ORIGINS`).

## Authentication (OIDC)

Production login uses **OIDC Authorization Code + PKCE** via `config.oidcProviders` in [`public/config.json`](public/config.json) (or the Helm `config` ConfigMap).

### Callback URL (redirect URI)

Register this **exact** URL on each IdP OIDC client:

```text
{origin}{path-prefix}/auth/callback
```

| Environment | Example redirect URI |
|-------------|----------------------|
| Helm default (`httpPathPrefix: /hammrly/portal`, host `sessions.example.com`) | `https://sessions.example.com/hammrly/portal/auth/callback` |
| Vite dev (`npm run dev`, port 5173) | `http://localhost:5173/auth/callback` |

- **`origin`** — public scheme + host users type in the browser (TLS terminates at ingress).
- **`path-prefix`** — no trailing slash; matches `httpPathPrefix` / `VITE_BASE_PATH` (see [Helm path prefix](../../helm/portal/README.md#path-prefix)).

Also register **`{origin}{path-prefix}/login`** as the post-logout redirect URI if your IdP supports end-session logout.

Full registration checklist, scope requirements, and multi-IdP notes: **[`helm/portal/README.md` — OIDC client registration](../../helm/portal/README.md#oidc-client-registration)**.
