import { apiFetch, parseJsonResponse } from "./client.js";
import { getConfig } from "../auth/config.js";

/**
 * @param {{ limit?: number, offset?: number }} [params]
 * @returns {Promise<import('./types.js').InteractiveJobListResponse>}
 */
export async function listInteractiveJobs(params = {}) {
  const { limit = 50, offset = 0 } = params;
  const base = getConfig().queryBaseUrl.replace(/\/$/, "");
  const url = `${base}/v1/me/jobs/interactive?limit=${limit}&offset=${offset}`;
  const res = await apiFetch(url);
  return /** @type {Promise<import('./types.js').InteractiveJobListResponse>} */ (
    parseJsonResponse(res)
  );
}

/**
 * @param {string} jobId
 * @returns {Promise<import('./types.js').JobDetailResponse>}
 */
export async function getJob(jobId) {
  const base = getConfig().queryBaseUrl.replace(/\/$/, "");
  const res = await apiFetch(`${base}/v1/jobs/${jobId}`);
  return /** @type {Promise<import('./types.js').JobDetailResponse>} */ (parseJsonResponse(res));
}
