import { apiFetch, parseJsonResponse } from "./client.js";
import { getConfig } from "../auth/config.js";

function queryBase() {
  return getConfig().queryBaseUrl.replace(/\/$/, "");
}

/**
 * @param {{ limit?: number, offset?: number }} [params]
 * @returns {Promise<import('./types.js').InteractiveJobListResponse>}
 */
export async function listInteractiveJobs(params = {}) {
  const { limit = 50, offset = 0 } = params;
  const url = `${queryBase()}/v1/me/jobs/interactive?limit=${limit}&offset=${offset}`;
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
  const res = await apiFetch(`${queryBase()}/v1/jobs/${jobId}`);
  return /** @type {Promise<import('./types.js').JobDetailResponse>} */ (parseJsonResponse(res));
}

/**
 * @param {string} campaignId
 * @returns {Promise<import('./types.js').CampaignDetailResponse>}
 */
export async function getCampaign(campaignId) {
  const res = await apiFetch(`${queryBase()}/v1/me/campaigns/${campaignId}`);
  return /** @type {Promise<import('./types.js').CampaignDetailResponse>} */ (
    parseJsonResponse(res)
  );
}

/**
 * @param {string} campaignId
 * @param {{ status?: string, limit?: number, offset?: number }} [params]
 * @returns {Promise<import('./types.js').CampaignJobListResponse>}
 */
export async function listCampaignJobs(campaignId, params = {}) {
  const { status, limit = 50, offset = 0 } = params;
  const qs = new URLSearchParams({
    limit: String(limit),
    offset: String(offset),
  });
  if (status) qs.set("status", status);
  const res = await apiFetch(
    `${queryBase()}/v1/me/campaigns/${campaignId}/jobs?${qs.toString()}`,
  );
  return /** @type {Promise<import('./types.js').CampaignJobListResponse>} */ (
    parseJsonResponse(res)
  );
}

/**
 * @param {{ unreadOnly?: boolean, limit?: number, offset?: number }} [params]
 * @returns {Promise<import('./types.js').NotificationListResponse>}
 */
export async function listNotifications(params = {}) {
  const { unreadOnly = false, limit = 50, offset = 0 } = params;
  const qs = new URLSearchParams({
    limit: String(limit),
    offset: String(offset),
    unread_only: unreadOnly ? "true" : "false",
  });
  const res = await apiFetch(`${queryBase()}/v1/me/notifications?${qs.toString()}`);
  return /** @type {Promise<import('./types.js').NotificationListResponse>} */ (
    parseJsonResponse(res)
  );
}

/**
 * @returns {Promise<import('./types.js').UnreadCountResponse>}
 */
export async function getUnreadNotificationCount() {
  const res = await apiFetch(`${queryBase()}/v1/me/notifications/unread_count`);
  return /** @type {Promise<import('./types.js').UnreadCountResponse>} */ (
    parseJsonResponse(res)
  );
}

/**
 * @param {number} notificationId
 * @returns {Promise<import('./types.js').NotificationItem>}
 */
export async function markNotificationRead(notificationId) {
  const res = await apiFetch(
    `${queryBase()}/v1/me/notifications/${notificationId}/read`,
    { method: "POST" },
  );
  return /** @type {Promise<import('./types.js').NotificationItem>} */ (parseJsonResponse(res));
}

/**
 * @returns {Promise<import('./types.js').UnreadCountResponse>}
 */
export async function markAllNotificationsRead() {
  const res = await apiFetch(`${queryBase()}/v1/me/notifications/read_all`, {
    method: "POST",
  });
  return /** @type {Promise<import('./types.js').UnreadCountResponse>} */ (
    parseJsonResponse(res)
  );
}

/**
 * Authenticated SSE via fetch (EventSource cannot send Bearer headers).
 * @param {(event: { type: string, data: Record<string, unknown> }) => void} onEvent
 * @param {AbortSignal} [signal]
 */
export async function streamNotifications(onEvent, signal) {
  const res = await apiFetch(`${queryBase()}/v1/me/notifications/stream`, {
    headers: { Accept: "text/event-stream" },
    signal,
  });
  if (!res.ok || !res.body) {
    throw new Error(`Notification stream failed (${res.status})`);
  }
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let sep;
    while ((sep = buffer.indexOf("\n\n")) >= 0) {
      const chunk = buffer.slice(0, sep);
      buffer = buffer.slice(sep + 2);
      let eventType = "message";
      let dataLine = "";
      for (const line of chunk.split("\n")) {
        if (line.startsWith("event:")) eventType = line.slice(6).trim();
        else if (line.startsWith("data:")) dataLine += line.slice(5).trim();
      }
      if (!dataLine) continue;
      try {
        onEvent({ type: eventType, data: JSON.parse(dataLine) });
      } catch {
        // ignore malformed
      }
    }
  }
}
