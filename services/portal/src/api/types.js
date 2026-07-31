/**
 * @typedef {Object} InteractiveJobItem
 * @property {string} job_id
 * @property {string} submission_id
 * @property {string} tenant_id
 * @property {string} status
 * @property {string|null} [status_detail]
 * @property {string} queue_name
 * @property {number} gpu_count
 * @property {string|null} [kind]
 * @property {string|null} [access_url]
 * @property {string} updated_at
 */

/**
 * @typedef {Object} InteractiveJobListResponse
 * @property {InteractiveJobItem[]} items
 * @property {number} limit
 * @property {number} offset
 */

/**
 * @typedef {Object} SubmissionEvent
 * @property {number} id
 * @property {string} event_type
 * @property {Record<string, unknown>} [payload_json]
 * @property {string} occurred_at
 */

/**
 * @typedef {Object} JobDetailResponse
 * @property {string} job_id
 * @property {string} submission_id
 * @property {string} tenant_id
 * @property {string|null} [project_id]
 * @property {string} user_id
 * @property {string|null} [campaign_id]
 * @property {string|null} [item_key]
 * @property {string} status
 * @property {string|null} [status_detail]
 * @property {string} queue_name
 * @property {number} gpu_count
 * @property {string} cluster_id
 * @property {string|null} [access_url]
 * @property {string} created_at
 * @property {string} updated_at
 * @property {SubmissionEvent[]} events
 */

/**
 * @typedef {Object} FailedSampleItem
 * @property {string} job_id
 * @property {string|null} [item_key]
 * @property {string} status
 * @property {string|null} [status_detail]
 */

/**
 * @typedef {Object} CampaignDetailResponse
 * @property {string} campaign_id
 * @property {string} name
 * @property {string|null} [description]
 * @property {string} status
 * @property {number|null} [item_count]
 * @property {Record<string, number>} by_status
 * @property {number} fail_count
 * @property {number} fail_pct
 * @property {number|null} [progress_pct]
 * @property {string|null} [output_uri]
 * @property {string} created_at
 * @property {string} updated_at
 * @property {FailedSampleItem[]} failed_sample
 */

/**
 * @typedef {Object} CampaignJobItem
 * @property {string} job_id
 * @property {string} submission_id
 * @property {string|null} [item_key]
 * @property {string} status
 * @property {string|null} [status_detail]
 * @property {string} updated_at
 */

/**
 * @typedef {Object} CampaignJobListResponse
 * @property {CampaignJobItem[]} items
 * @property {number} limit
 * @property {number} offset
 */

/**
 * @typedef {Object} NotificationItem
 * @property {number} id
 * @property {string} kind
 * @property {string} subject
 * @property {Record<string, unknown>} body_json
 * @property {string|null} [resource_type]
 * @property {string|null} [resource_id]
 * @property {string} created_at
 * @property {string|null} [read_at]
 */

/**
 * @typedef {Object} NotificationListResponse
 * @property {NotificationItem[]} items
 * @property {number} limit
 * @property {number} offset
 */

/**
 * @typedef {Object} UnreadCountResponse
 * @property {number} unread_count
 */

/**
 * @typedef {Object} SoftwareSearchItem
 * @property {string} id
 * @property {string} name
 * @property {string|null} [description]
 * @property {string|null} [status]
 * @property {string[]} tools_included
 * @property {string[]} supported_modes
 * @property {boolean} gpu_required
 * @property {{ min?: number, recommended?: number }} [memory]
 */

/**
 * @typedef {Object} CreateSessionResponse
 * @property {string} job_id
 * @property {string} submission_id
 * @property {string} status
 * @property {string} status_url
 */

export {};
