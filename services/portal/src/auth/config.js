/**
 * @typedef {Object} OidcProviderConfig
 * @property {string} id
 * @property {string} displayName
 * @property {string} authority
 * @property {string} clientId
 * @property {string} scope
 * @property {Record<string, string>} [extraQueryParams]
 */

/**
 * @typedef {Object} DevBypassConfig
 * @property {boolean} enabled
 * @property {string} hmacSecret
 * @property {string} [userId]
 * @property {string} [tenantId]
 */

/**
 * @typedef {Object} PortalConfig
 * @property {string} queryBaseUrl
 * @property {string} gatewayBaseUrl
 * @property {string} catalogBaseUrl
 * @property {Record<string, string>} [imageMap]
 * @property {string[]} [defaultSearchTerms]
 * @property {OidcProviderConfig[]} oidcProviders
 * @property {DevBypassConfig} [devBypass]
 */

/** @type {PortalConfig | null} */
let cachedConfig = null;

/**
 * @returns {Promise<PortalConfig>}
 */
export async function loadConfig() {
  if (cachedConfig) return cachedConfig;
  const base = import.meta.env.BASE_URL || "/";
  const path = `${base.endsWith("/") ? base : `${base}/`}config.json`;
  const res = await fetch(path);
  if (!res.ok) {
    throw new Error(`Failed to load config.json (${res.status})`);
  }
  const data = await res.json();
  if (!data.queryBaseUrl || !data.gatewayBaseUrl || !data.catalogBaseUrl) {
    throw new Error("config.json missing required API base URLs");
  }
  cachedConfig = {
    imageMap: {},
    oidcProviders: [],
    ...data,
  };
  return cachedConfig;
}

export function getConfig() {
  if (!cachedConfig) {
    throw new Error("Config not loaded");
  }
  return cachedConfig;
}

export function clearConfigCache() {
  cachedConfig = null;
}

/**
 * @param {string} catalogId
 * @returns {string | null}
 */
export function resolveImage(catalogId) {
  const cfg = getConfig();
  return cfg.imageMap?.[catalogId] ?? null;
}

export function getAppBasePath() {
  const base = import.meta.env.BASE_URL || "/";
  return base.endsWith("/") ? base.slice(0, -1) : base;
}

export function getRedirectUri() {
  return `${window.location.origin}${getAppBasePath()}/auth/callback`;
}
