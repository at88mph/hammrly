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
