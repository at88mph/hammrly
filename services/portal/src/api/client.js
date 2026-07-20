/**
 * @typedef {Object} ApiError
 * @property {string} error
 * @property {string} message
 * @property {Record<string, unknown>} [details]
 */

/** @type {(() => Promise<string | null>) | null} */
let tokenGetter = null;

export function setTokenGetter(fn) {
  tokenGetter = fn;
}

/**
 * @param {string} url
 * @param {RequestInit} [options]
 * @returns {Promise<Response>}
 */
export async function apiFetch(url, options = {}) {
  const headers = new Headers(options.headers || {});
  if (tokenGetter) {
    const token = await tokenGetter();
    if (token) {
      headers.set("Authorization", `Bearer ${token}`);
    }
  }
  if (!headers.has("Content-Type") && options.body && typeof options.body === "string") {
    headers.set("Content-Type", "application/json");
  }
  const res = await fetch(url, { ...options, headers });
  return res;
}

/**
 * @param {Response} res
 * @returns {Promise<unknown>}
 */
export async function parseJsonResponse(res) {
  const text = await res.text();
  let body;
  try {
    body = text ? JSON.parse(text) : {};
  } catch {
    throw new Error(`Invalid JSON response (${res.status})`);
  }
  if (!res.ok) {
    /** @type {ApiError} */
    const err = body.detail || body;
    const msg = err.message || res.statusText;
    const error = new Error(msg);
    error.status = res.status;
    error.code = err.error;
    error.details = err.details;
    throw error;
  }
  return body;
}
