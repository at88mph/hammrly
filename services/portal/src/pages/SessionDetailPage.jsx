import { Link, useParams } from "@tanstack/react-router";
import { useJobPoll } from "../hooks/useJobPoll.js";
import { statusColor } from "../utils.js";

export function SessionDetailPage() {
  const { jobId } = useParams({ from: "/sessions/$jobId" });
  const { data: job, isLoading, isError, error } = useJobPoll(jobId);

  if (isLoading) {
    return <p className="text-slate-600">Loading session…</p>;
  }

  if (isError || !job) {
    return (
      <div className="rounded border border-red-200 bg-red-50 p-4 text-red-700">
        {error instanceof Error ? error.message : "Session not found"}
        <div className="mt-2">
          <Link to="/" className="text-sm text-portal-accent hover:underline">
            Back to Home
          </Link>
        </div>
      </div>
    );
  }

  const canOpen = job.status === "ready" && job.access_url;
  const isFailed = job.status === "failed" || job.status === "dead_letter";

  return (
    <div className="mx-auto max-w-3xl">
      <Link to="/" className="text-sm text-portal-accent hover:underline">
        ← Home
      </Link>
      <h1 className="mt-4 text-2xl font-semibold text-slate-900">Session</h1>
      <p className="mt-1 font-mono text-sm text-slate-600">{job.job_id}</p>

      <div
        className={`mt-6 rounded-lg border p-4 ${isFailed ? "border-red-200 bg-red-50" : "border-slate-200 bg-white"}`}
      >
        <div className="flex flex-wrap items-center justify-between gap-4">
          <span
            className={`inline-block rounded-full px-3 py-1 text-sm font-medium ${statusColor(job.status)}`}
          >
            {job.status}
          </span>
          {canOpen && (
            <a
              href={job.access_url}
              target="_blank"
              rel="noopener noreferrer"
              className="rounded-md bg-portal-accent px-4 py-2 text-sm font-medium text-white hover:bg-blue-700"
            >
              Open session
            </a>
          )}
        </div>
        {job.status_detail && isFailed && (
          <p className="mt-3 text-sm text-red-700">{job.status_detail}</p>
        )}
        {!canOpen && !isFailed && (
          <p className="mt-3 text-sm text-slate-600">
            Session is provisioning. This page refreshes automatically.
          </p>
        )}
      </div>

      <dl className="mt-6 grid grid-cols-1 gap-3 rounded-lg border border-slate-200 bg-white p-4 text-sm sm:grid-cols-2">
        <div>
          <dt className="text-slate-500">Submission ID</dt>
          <dd className="font-mono text-slate-900">{job.submission_id}</dd>
        </div>
        <div>
          <dt className="text-slate-500">Tenant</dt>
          <dd>{job.tenant_id}</dd>
        </div>
        <div>
          <dt className="text-slate-500">Queue</dt>
          <dd>{job.queue_name}</dd>
        </div>
        <div>
          <dt className="text-slate-500">Cluster</dt>
          <dd>{job.cluster_id}</dd>
        </div>
        <div>
          <dt className="text-slate-500">Created</dt>
          <dd>{new Date(job.created_at).toLocaleString()}</dd>
        </div>
        <div>
          <dt className="text-slate-500">Updated</dt>
          <dd>{new Date(job.updated_at).toLocaleString()}</dd>
        </div>
      </dl>

      <section className="mt-8">
        <h2 className="text-lg font-medium text-slate-900">Event timeline</h2>
        {job.events?.length ? (
          <ol className="mt-4 space-y-3">
            {job.events.map((ev) => (
              <li
                key={ev.id}
                className="rounded border border-slate-200 bg-white px-4 py-3 text-sm"
              >
                <div className="flex justify-between gap-4">
                  <span className="font-medium text-slate-800">{ev.event_type}</span>
                  <time className="text-slate-500">
                    {new Date(ev.occurred_at).toLocaleString()}
                  </time>
                </div>
              </li>
            ))}
          </ol>
        ) : (
          <p className="mt-2 text-sm text-slate-500">No events yet.</p>
        )}
      </section>
    </div>
  );
}
