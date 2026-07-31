import { useState } from "react";
import { Link, useNavigate } from "@tanstack/react-router";
import { resolveImage } from "../auth/config.js";
import { useAuth } from "../auth/AuthProvider.jsx";
import { SoftwareCard, deriveKindFromModes } from "../components/SoftwareCard.jsx";
import { useCreateSession } from "../hooks/useCreateSession.js";
import { useDebouncedValue, useSoftwareSearch } from "../hooks/useSoftwareSearch.js";
import {
  defaultSessionName,
  memoryGiFromCatalog,
} from "../utils.js";

const KIND_FILTERS = [
  { id: "all", label: "All" },
  { id: "desktop", label: "Desktop" },
  { id: "notebook", label: "Notebook" },
  { id: "carta", label: "Carta" },
];

export function NewSessionPage() {
  const navigate = useNavigate();
  const { profile } = useAuth();
  const createSession = useCreateSession();

  const [step, setStep] = useState(/** @type {1 | 2} */ (1));
  const [kindFilter, setKindFilter] = useState(
    /** @type {'all' | 'desktop' | 'notebook' | 'carta'} */ ("all"),
  );
  const [searchText, setSearchText] = useState("");
  const debouncedSearch = useDebouncedValue(searchText);

  const { filteredItems, isLoading, isError, error, refetch } = useSoftwareSearch(
    debouncedSearch,
    kindFilter,
  );

  /** @type {[import('../api/types.js').SoftwareSearchItem | null, Function]} */
  const [selected, setSelected] = useState(null);
  const [sessionName, setSessionName] = useState("");
  const [projectId, setProjectId] = useState("");
  const [cpu, setCpu] = useState("4");
  const [memory, setMemory] = useState("8Gi");
  const [requestGpu, setRequestGpu] = useState(false);
  const [gpuCount, setGpuCount] = useState("1");
  const [tenantId, setTenantId] = useState("");
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [submitError, setSubmitError] = useState(/** @type {string | null} */ (null));

  const resolvedImage = selected ? resolveImage(selected.id) : null;
  const workloadKind = selected
    ? deriveKindFromModes(selected.supported_modes, kindFilter)
    : null;

  const handleSelect = (item) => {
    setSelected(item);
    setSessionName(defaultSessionName(item.name));
    setMemory(memoryGiFromCatalog(item.memory));
    setRequestGpu(item.gpu_required);
    setGpuCount("1");
    setStep(2);
    setSubmitError(null);
  };

  const handleBackToPicker = () => {
    setStep(1);
    setSubmitError(null);
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSubmitError(null);
    if (!selected || !workloadKind || !resolvedImage) return;
    if (!sessionName.trim()) {
      setSubmitError("Session name is required.");
      return;
    }

    /** @type {Record<string, string>} */
    const resources = { cpu, memory };
    if (requestGpu) {
      resources["nvidia.com/gpu"] = gpuCount;
    }

    try {
      const result = await createSession.mutateAsync({
        kind: workloadKind,
        workload: {
          name: sessionName.trim(),
          image: resolvedImage,
          resources,
        },
        projectId: projectId.trim() || undefined,
        tenantId: !profile?.tenantId && tenantId.trim() ? tenantId.trim() : undefined,
      });
      navigate({ to: "/sessions/$jobId", params: { jobId: result.job_id } });
    } catch (err) {
      setSubmitError(err instanceof Error ? err.message : "Failed to create session");
    }
  };

  if (step === 1) {
    return (
      <div>
        <h1 className="text-2xl font-semibold text-slate-900">New Session</h1>
        <p className="mt-1 text-sm text-slate-600">Choose a software image to run.</p>

        <div className="mt-6 flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex flex-wrap gap-2">
            {KIND_FILTERS.map((f) => (
              <button
                key={f.id}
                type="button"
                onClick={() =>
                  setKindFilter(/** @type {'all'|'desktop'|'notebook'|'carta'} */ (f.id))
                }
                className={
                  kindFilter === f.id
                    ? "rounded-full bg-portal-accent px-4 py-1.5 text-sm font-medium text-white"
                    : "rounded-full border border-slate-300 px-4 py-1.5 text-sm text-slate-700 hover:bg-slate-50"
                }
              >
                {f.label}
              </button>
            ))}
          </div>
          <input
            type="search"
            placeholder="Search software…"
            value={searchText}
            onChange={(e) => setSearchText(e.target.value)}
            className="w-full max-w-sm rounded-md border border-slate-300 px-3 py-2 text-sm sm:w-72"
          />
        </div>

        {isLoading && <p className="mt-8 text-slate-600">Loading images…</p>}

        {isError && (
          <div className="mt-6 rounded border border-red-200 bg-red-50 p-4">
            <p className="text-sm text-red-700">
              {error instanceof Error ? error.message : "Search failed"}
            </p>
            <button
              type="button"
              onClick={() => refetch()}
              className="mt-2 text-sm text-portal-accent hover:underline"
            >
              Retry
            </button>
          </div>
        )}

        {!isLoading && !isError && filteredItems.length === 0 && (
          <p className="mt-8 text-slate-600">No images match your search.</p>
        )}

        <div className="mt-6 grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
          {filteredItems.map((item) => (
            <SoftwareCard
              key={item.id}
              item={item}
              kindFilter={kindFilter}
              onSelect={() => handleSelect(item)}
            />
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-2xl">
      <h1 className="text-2xl font-semibold text-slate-900">New Session</h1>
      <p className="mt-1 text-sm text-slate-600">Configure and launch your session.</p>

      <div
        className={`mt-6 rounded-lg border p-4 ${!resolvedImage ? "border-amber-300 bg-amber-50" : "border-slate-200 bg-white"}`}
      >
        <div className="flex items-start justify-between gap-4">
          <div>
            <p className="font-medium text-slate-900">{selected?.name}</p>
            <p className="mt-1 truncate text-sm text-slate-600">
              {resolvedImage || "No OCI image mapping for this catalog entry"}
            </p>
            {workloadKind && (
              <p className="mt-1 text-sm text-slate-500 capitalize">Kind: {workloadKind}</p>
            )}
          </div>
          <button
            type="button"
            onClick={handleBackToPicker}
            className="shrink-0 text-sm text-portal-accent hover:underline"
          >
            Change image
          </button>
        </div>
      </div>

      {submitError && (
        <div className="mt-4 rounded border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
          {submitError}
        </div>
      )}

      <form onSubmit={handleSubmit} className="mt-6 space-y-6">
        <fieldset className="rounded-lg border border-slate-200 bg-white p-4">
          <legend className="px-1 text-sm font-medium text-slate-700">Identity</legend>
          <label className="mt-3 block text-sm">
            Session name *
            <input
              required
              value={sessionName}
              onChange={(e) => setSessionName(e.target.value)}
              className="mt-1 w-full rounded border border-slate-300 px-3 py-2"
            />
          </label>
          <label className="mt-3 block text-sm">
            Project ID
            <input
              value={projectId}
              onChange={(e) => setProjectId(e.target.value)}
              placeholder="optional"
              className="mt-1 w-full rounded border border-slate-300 px-3 py-2"
            />
          </label>
        </fieldset>

        <fieldset className="rounded-lg border border-slate-200 bg-white p-4">
          <legend className="px-1 text-sm font-medium text-slate-700">Resources</legend>
          <div className="mt-3 grid grid-cols-2 gap-4">
            <label className="text-sm">
              CPU *
              <input
                required
                value={cpu}
                onChange={(e) => setCpu(e.target.value)}
                className="mt-1 w-full rounded border border-slate-300 px-3 py-2"
              />
            </label>
            <label className="text-sm">
              Memory *
              <input
                required
                value={memory}
                onChange={(e) => setMemory(e.target.value)}
                className="mt-1 w-full rounded border border-slate-300 px-3 py-2"
              />
            </label>
          </div>
          <label className="mt-4 flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={requestGpu}
              onChange={(e) => setRequestGpu(e.target.checked)}
            />
            Request GPU
          </label>
          {requestGpu && (
            <label className="mt-2 block text-sm">
              GPU count
              <input
                type="number"
                min="1"
                value={gpuCount}
                onChange={(e) => setGpuCount(e.target.value)}
                className="mt-1 w-32 rounded border border-slate-300 px-3 py-2"
              />
            </label>
          )}
        </fieldset>

        {!profile?.tenantId && (
          <fieldset className="rounded-lg border border-slate-200 bg-white p-4">
            <button
              type="button"
              onClick={() => setShowAdvanced(!showAdvanced)}
              className="text-sm font-medium text-slate-700"
            >
              {showAdvanced ? "▼" : "▶"} Advanced
            </button>
            {showAdvanced && (
              <label className="mt-3 block text-sm">
                Tenant ID
                <input
                  value={tenantId}
                  onChange={(e) => setTenantId(e.target.value)}
                  className="mt-1 w-full rounded border border-slate-300 px-3 py-2"
                />
              </label>
            )}
          </fieldset>
        )}

        <div className="flex justify-end gap-3">
          <Link
            to="/"
            className="rounded border border-slate-300 px-4 py-2 text-sm hover:bg-slate-50"
          >
            Cancel
          </Link>
          <button
            type="submit"
            disabled={createSession.isPending || !resolvedImage || !workloadKind}
            className="rounded bg-portal-accent px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
          >
            {createSession.isPending ? "Creating…" : "Create session"}
          </button>
        </div>
      </form>
    </div>
  );
}
