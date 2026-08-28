const IN_FLIGHT = new Set([
  "pending",
  "received",
  "building_spec",
  "submitted_to_cluster",
  "running",
  "admitted",
  "queued",
]);

/** Statuses shown on the Home interactive-session list (excludes unknown/failed/etc.). */
export const INTERACTIVE_LIST_STATUSES = ["ready", ...IN_FLIGHT];

/** Lifecycle phases for the job status stepper (interactive + headless). */
export const JOB_PHASES = [
  "received",
  "building_spec",
  "submitted_to_cluster",
  "admitted",
  "running",
  "ready",
  "succeeded",
];

/**
 * @param {string} status
 * @returns {number} index into JOB_PHASES, or -1 for failed/unknown
 */
export function phaseIndexForStatus(status) {
  const s = status?.toLowerCase?.() ?? "";
  if (s === "failed" || s === "dead_letter" || s === "unknown" || s === "cancelled") {
    return -1;
  }
  if (s === "pending") return 0;
  const idx = JOB_PHASES.indexOf(s);
  return idx >= 0 ? idx : 0;
}

const TERMINAL = new Set([
  "ready",
  "succeeded",
  "failed",
  "unknown",
  "cancelled",
  "dead_letter",
]);

export function isInFlightStatus(status) {
  return IN_FLIGHT.has(status?.toLowerCase?.() ?? status);
}

export function isTerminalStatus(status) {
  return TERMINAL.has(status?.toLowerCase?.() ?? status);
}

/**
 * @param {string[]} modes
 * @param {'all' | 'desktop' | 'notebook' | 'carta'} filter
 * @returns {'desktop' | 'notebook' | 'carta' | null}
 */
export function deriveKindFromModes(modes, filter = "all") {
  const upper = (modes || []).map((m) => m.toUpperCase());
  const hasDesktop = upper.includes("DESKTOP");
  const hasNotebook = upper.includes("NOTEBOOK");
  const hasCarta = upper.includes("CARTA");
  if (filter === "desktop" && hasDesktop) return "desktop";
  if (filter === "notebook" && hasNotebook) return "notebook";
  if (filter === "carta" && hasCarta) return "carta";
  const present = [
    hasDesktop && "desktop",
    hasNotebook && "notebook",
    hasCarta && "carta",
  ].filter(Boolean);
  if (present.length === 0) return null;
  if (present.length === 1) return /** @type {'desktop' | 'notebook' | 'carta'} */ (present[0]);
  // Multiple modes: prefer desktop, then notebook, then carta (filter already handled above).
  if (hasDesktop) return "desktop";
  if (hasNotebook) return "notebook";
  return "carta";
}

/**
 * @param {string[]} modes
 * @returns {string}
 */
export function kindLabelFromModes(modes, filter = "all") {
  const kind = deriveKindFromModes(modes, filter);
  if (kind === "desktop") return "Desktop";
  if (kind === "notebook") return "Notebook";
  if (kind === "carta") return "Carta";
  return "—";
}

/**
 * @param {import('../api/types.js').SoftwareSearchItem} item
 * @param {'all' | 'desktop' | 'notebook' | 'carta'} filter
 */
export function isInteractiveCatalogItem(item, filter) {
  const kind = deriveKindFromModes(item.supported_modes, filter);
  if (filter === "all") {
    return deriveKindFromModes(item.supported_modes, "all") !== null;
  }
  return kind === filter;
}

export function formatTools(tools, max = 5) {
  if (!tools?.length) return "—";
  const shown = tools.slice(0, max);
  const text = shown.join(", ");
  return tools.length > max ? `${text}, …` : text;
}

export function truncate(text, max = 120) {
  if (!text) return "";
  if (text.length <= max) return text;
  return `${text.slice(0, max).trim()}…`;
}

export function formatRelativeTime(iso) {
  const then = new Date(iso).getTime();
  const diff = Date.now() - then;
  const sec = Math.floor(diff / 1000);
  if (sec < 60) return "just now";
  const min = Math.floor(sec / 60);
  if (min < 60) return `${min}m ago`;
  const hr = Math.floor(min / 60);
  if (hr < 24) return `${hr}h ago`;
  const day = Math.floor(hr / 24);
  return `${day}d ago`;
}

export function statusColor(status) {
  const s = status?.toLowerCase?.() ?? "";
  if (s === "ready" || s === "succeeded" || s === "completed") {
    return "bg-emerald-100 text-emerald-800";
  }
  if (
    s === "running" ||
    s === "received" ||
    s === "admitted" ||
    s === "building_spec" ||
    s === "submitted_to_cluster" ||
    s === "active" ||
    s === "expanding"
  ) {
    return "bg-blue-100 text-blue-800";
  }
  if (s === "failed" || s === "dead_letter" || s === "partial_failed") {
    return "bg-red-100 text-red-800";
  }
  if (s === "pending" || s === "accepted") return "bg-amber-100 text-amber-800";
  return "bg-slate-100 text-slate-700";
}

export function defaultSessionName(softwareName) {
  const base = (softwareName || "session")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "")
    .slice(0, 40);
  const suffix = Math.random().toString(36).slice(2, 8);
  return `${base || "session"}-${suffix}`;
}

export function memoryGiFromCatalog(memory) {
  if (memory?.recommended) return `${memory.recommended}Gi`;
  if (memory?.min) return `${memory.min}Gi`;
  return "8Gi";
}
