import { UserManager, WebStorageStateStore } from "oidc-client-ts";
import { SignJWT } from "jose";
import { getConfig, getRedirectUri, loadConfig } from "./config.js";

/** @type {Map<string, UserManager>} */
const managers = new Map();

const DEV_USER_KEY = "portal_dev_user";

/**
 * @param {import('./config.js').OidcProviderConfig} provider
 * @returns {UserManager}
 */
export function createUserManager(provider) {
  const redirectUri = getRedirectUri();
  return new UserManager({
    authority: provider.authority,
    client_id: provider.clientId,
    redirect_uri: redirectUri,
    response_type: "code",
    scope: provider.scope,
    automaticSilentRenew: true,
    userStore: new WebStorageStateStore({ store: window.sessionStorage }),
    extraQueryParams: provider.extraQueryParams || {},
  });
}

/**
 * @param {string} providerId
 * @returns {UserManager}
 */
export function getUserManager(providerId) {
  const mgr = managers.get(providerId);
  if (!mgr) {
    throw new Error(`Unknown OIDC provider: ${providerId}`);
  }
  return mgr;
}

/**
 * @param {import('./config.js').PortalConfig} config
 */
export function initOidcManagers(config) {
  managers.clear();
  for (const p of config.oidcProviders || []) {
    managers.set(p.id, createUserManager(p));
  }
}

export function getLastProviderId() {
  return sessionStorage.getItem("oidcProviderId");
}

export function setLastProviderId(id) {
  sessionStorage.setItem("oidcProviderId", id);
}

/**
 * @returns {Promise<import('oidc-client-ts').User | null>}
 */
export async function getCurrentUser() {
  const cfg = getConfig();
  if (cfg.devBypass?.enabled) {
    return getDevUser(cfg);
  }
  const providerId = getLastProviderId();
  if (!providerId) return null;
  try {
    return await getUserManager(providerId).getUser();
  } catch {
    return null;
  }
}

/**
 * @returns {Promise<string | null>}
 */
export async function getAccessToken() {
  const user = await getCurrentUser();
  if (!user) return null;
  if (user.expired) {
    const cfg = getConfig();
    if (cfg.devBypass?.enabled) {
      const refreshed = await mintDevToken(cfg);
      sessionStorage.setItem(DEV_USER_KEY, JSON.stringify(refreshed));
      return refreshed.access_token;
    }
    const providerId = getLastProviderId();
    if (!providerId) return null;
    try {
      const renewed = await getUserManager(providerId).signinSilent();
      return renewed?.access_token ?? null;
    } catch {
      return null;
    }
  }
  return user.access_token;
}

/**
 * @param {import('./config.js').PortalConfig} config
 */
async function mintDevToken(config) {
  const bypass = config.devBypass;
  const secret = new TextEncoder().encode(bypass.hmacSecret);
  const now = Math.floor(Date.now() / 1000);
  const token = await new SignJWT({
    scope:
      "hammrly:jobs:read hammrly:jobs:submit hammrly:catalog:read openid profile",
    hammrly_tenant_id: bypass.tenantId || "dev-tenant",
  })
    .setProtectedHeader({ alg: "HS256" })
    .setSubject(bypass.userId || "portal-dev-user")
    .setIssuedAt(now)
    .setExpirationTime(now + 3600)
    .sign(secret);

  return {
    access_token: token,
    token_type: "Bearer",
    profile: { sub: bypass.userId || "portal-dev-user" },
    expires_at: now + 3600,
    expired: false,
  };
}

/**
 * @param {import('./config.js').PortalConfig} config
 */
async function getDevUser(config) {
  const raw = sessionStorage.getItem(DEV_USER_KEY);
  if (raw) {
    try {
      const parsed = JSON.parse(raw);
      if (parsed.expires_at > Math.floor(Date.now() / 1000)) {
        return parsed;
      }
    } catch {
      /* refresh below */
    }
  }
  const user = await mintDevToken(config);
  sessionStorage.setItem(DEV_USER_KEY, JSON.stringify(user));
  return user;
}

/**
 * @param {string} providerId
 */
export async function signIn(providerId) {
  await loadConfig();
  setLastProviderId(providerId);
  await getUserManager(providerId).signinRedirect({
    state: { returnTo: sessionStorage.getItem("returnTo") || "/" },
  });
}

export async function signInDev() {
  const cfg = await loadConfig();
  if (!cfg.devBypass?.enabled) {
    throw new Error("Dev bypass is not enabled");
  }
  initOidcManagers(cfg);
  await getDevUser(cfg);
}

export async function handleCallback() {
  const providerId = getLastProviderId();
  if (!providerId) {
    throw new Error("No OIDC provider selected");
  }
  return getUserManager(providerId).signinRedirectCallback();
}

export async function signOut() {
  const cfg = getConfig();
  if (cfg.devBypass?.enabled) {
    sessionStorage.removeItem(DEV_USER_KEY);
    return;
  }
  const providerId = getLastProviderId();
  if (providerId) {
    try {
      await getUserManager(providerId).signoutRedirect();
    } catch {
      await getUserManager(providerId).removeUser();
    }
  }
}

export function parseJwtClaims(token) {
  try {
    const payload = token.split(".")[1];
    return JSON.parse(atob(payload.replace(/-/g, "+").replace(/_/g, "/")));
  } catch {
    return {};
  }
}
