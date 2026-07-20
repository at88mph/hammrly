import {
  deriveKindFromModes,
  formatTools,
  kindLabelFromModes,
  truncate,
} from "../utils.js";

/**
 * @param {{ item: import('../api/types.js').SoftwareSearchItem, kindFilter: 'all' | 'desktop' | 'notebook', onSelect: () => void }} props
 */
export function SoftwareCard({ item, kindFilter, onSelect }) {
  const kindLabel = kindLabelFromModes(item.supported_modes, kindFilter);
  const gpuLabel = item.gpu_required ? "Required" : "Not required";

  return (
    <button
      type="button"
      onClick={onSelect}
      className="flex h-full w-full flex-col rounded-lg border border-slate-200 bg-white p-5 text-left shadow-sm transition hover:border-portal-accent hover:ring-2 hover:ring-portal-accent/20 focus:outline-none focus:ring-2 focus:ring-portal-accent"
    >
      <h3 className="text-lg font-semibold text-slate-900">{item.name}</h3>
      <p className="mt-2 text-sm text-slate-600">
        <span className="font-medium text-slate-700">Kind:</span> {kindLabel}
      </p>
      <p className="text-sm text-slate-600">
        <span className="font-medium text-slate-700">GPU:</span> {gpuLabel}
      </p>
      <p className="mt-1 text-sm text-slate-600">
        <span className="font-medium text-slate-700">Tools:</span> {formatTools(item.tools_included)}
      </p>
      {item.description && (
        <p className="mt-3 line-clamp-2 flex-1 text-sm text-slate-500">
          {truncate(item.description, 120)}
        </p>
      )}
      <span className="mt-4 inline-flex text-sm font-medium text-portal-accent">
        Select →
      </span>
    </button>
  );
}

export { deriveKindFromModes };
