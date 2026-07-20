import { apiFetch, parseJsonResponse } from "./client.js";
import { getConfig } from "../auth/config.js";

/**
 * @param {object} payload
 * @returns {Promise<import('./types.js').CreateSessionResponse>}
 */
export async function createSession(payload) {
  const base = getConfig().gatewayBaseUrl.replace(/\/$/, "");
  const res = await apiFetch(`${base}/v2/session`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
  return /** @type {Promise<import('./types.js').CreateSessionResponse>} */ (
    parseJsonResponse(res)
  );
}

/**
 * @param {string} kind
 * @param {object} workload
 * @returns {object}
 */
export function buildWorkload(kind, workload) {
  const w = { ...workload, kind };
  if (kind === "desktop") {
    w.kind_options = { novnc: { port: 6080 }, ...(w.kind_options || {}) };
  } else if (kind === "notebook") {
    w.kind_options = { ...(w.kind_options || {}) };
  }
  return w;
}
