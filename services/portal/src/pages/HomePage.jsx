import { Link } from "@tanstack/react-router";
import { useInteractiveJobs } from "../hooks/useInteractiveJobs.js";
import { formatRelativeTime, statusColor } from "../utils.js";

export function HomePage() {
  const { data, isLoading, isError, error, fetchNextPage, hasNextPage, isFetchingNextPage } =
    useInteractiveJobs();

  const items = data?.pages.flatMap((p) => p.items) ?? [];

  if (isLoading) {
    return <p className="text-slate-600">Loading sessions…</p>;
  }

  if (isError) {
    return (
      <div className="rounded border border-red-200 bg-red-50 p-4 text-red-700">
        {error instanceof Error ? error.message : "Failed to load sessions"}
      </div>
    );
  }

  return (
    <div>
      <h1 className="text-2xl font-semibold text-slate-900">Home</h1>
      <p className="mt-1 text-sm text-slate-600">Your interactive sessions.</p>

      {items.length === 0 ? (
        <div className="mt-8 rounded-lg border border-dashed border-slate-300 bg-white p-10 text-center">
          <p className="text-slate-600">No sessions yet.</p>
          <Link
            to="/sessions/new"
            className="mt-4 inline-block rounded-md bg-portal-accent px-4 py-2 text-sm font-medium text-white hover:bg-blue-700"
          >
            New Session
          </Link>
        </div>
      ) : (
        <div className="mt-6 overflow-x-auto rounded-lg border border-slate-200 bg-white">
          <table className="w-full table-fixed text-left text-sm">
            <thead className="border-b border-slate-200 bg-slate-50 text-slate-600">
              <tr>
                <th className="px-4 py-3 font-medium">Name / ID</th>
                <th className="w-32 px-4 py-3 font-medium">Kind</th>
                <th className="w-28 px-4 py-3 font-medium">Status</th>
                <th className="w-16 px-4 py-3 font-medium">GPU</th>
                <th className="w-28 px-4 py-3 font-medium">Updated</th>
                <th className="w-36 px-4 py-3 font-medium">Actions</th>
              </tr>
            </thead>
            <tbody>
              {items.map((job) => (
                <tr key={job.job_id} className="border-b border-slate-100 hover:bg-slate-50">
                  <td className="min-w-0 px-4 py-3">
                    <Link
                      to="/sessions/$jobId"
                      params={{ jobId: job.job_id }}
                      title={job.job_id}
                      className="block truncate font-mono font-medium text-portal-accent hover:underline"
                    >
                      {job.job_id}
                    </Link>
                  </td>
                  <td className="whitespace-nowrap px-4 py-3 capitalize">{job.kind || "—"}</td>
                  <td className="whitespace-nowrap px-4 py-3">
                    <span
                      className={`inline-block rounded-full px-2.5 py-0.5 text-xs font-medium ${statusColor(job.status)}`}
                    >
                      {job.status}
                    </span>
                  </td>
                  <td className="whitespace-nowrap px-4 py-3">{job.gpu_count}</td>
                  <td className="whitespace-nowrap px-4 py-3 text-slate-600">
                    {formatRelativeTime(job.updated_at)}
                  </td>
                  <td className="whitespace-nowrap px-4 py-3">
                    <div className="flex gap-2">
                      {job.status === "ready" && job.access_url ? (
                        <a
                          href={job.access_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-portal-accent hover:underline"
                          onClick={(e) => e.stopPropagation()}
                        >
                          Open
                        </a>
                      ) : (
                        <span className="text-slate-400">Open</span>
                      )}
                      <Link
                        to="/sessions/$jobId"
                        params={{ jobId: job.job_id }}
                        className="text-slate-600 hover:underline"
                      >
                        Details
                      </Link>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {hasNextPage && (
            <div className="border-t border-slate-200 p-4 text-center">
              <button
                type="button"
                onClick={() => fetchNextPage()}
                disabled={isFetchingNextPage}
                className="rounded border border-slate-300 px-4 py-2 text-sm hover:bg-slate-50 disabled:opacity-50"
              >
                {isFetchingNextPage ? "Loading…" : "Load more"}
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
