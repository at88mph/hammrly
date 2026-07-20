import { apiFetch, parseJsonResponse } from "./client.js";
import { getConfig } from "../auth/config.js";

/**
 * @param {{ terms?: string[], limit?: number, offset?: number }} [params]
 * @returns {Promise<{ items: import('./types.js').SoftwareSearchItem[], limit: number, offset: number }>}
 */
export async function searchSoftware(params = {}) {
  const { terms = [], limit = 50, offset = 0 } = params;
  if (!terms.length) {
    throw new Error("At least one search term is required");
  }
  const base = getConfig().catalogBaseUrl.replace(/\/$/, "");
  const url = `${base}/v1/software/query?limit=${limit}&offset=${offset}`;
  const body = new URLSearchParams();
  for (const t of terms) {
    if (t.trim()) body.append("term", t.trim());
  }
  const res = await apiFetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: body.toString(),
  });
  return parseJsonResponse(res);
}
