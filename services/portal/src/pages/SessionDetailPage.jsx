import { Link, useParams } from "@tanstack/react-router";
import { EventTimeline } from "../components/EventTimeline.jsx";
import { JobPhaseStepper } from "../components/JobPhaseStepper.jsx";
import { useJobPoll } from "../hooks/useJobPoll.js";
import { statusColor } from "../utils.js";

export function SessionDetailPage() {
  const { jobId } = useParams({ from: "/sessions/$jobId" });
  return <JobDetailView jobId={jobId} backTo="/" backLabel="← Home" title="Session" />;
}

/**
 * Shared job detail for interactive sessions and headless campaign jobs.
 * @param {{ jobId: string, backTo?: string, backLabel?: string, title?: string }} props
 */
export function JobDetailView({
  jobId,
  backTo = "/",
  backLabel = "← Home",
  title = "Job",
}) {
  const { data: job, isLoading, isError, error } = useJobPoll(jobId);

  if (isLoading) {
    return <p className="text-slate-600">Loading {title.toLowerCase()}…</p>;
  }

  if (isError || !job) {
    return (
      <div className="rounded border border-red-200 bg-red-50 p-4 text-red-700">
        {error instanceof Error ? error.message : `${title} not found`}
        <div className="mt-2">
          <Link to={backTo} className="text-sm text-portal-accent hover:underline">
            {backLabel}
          </Link>
        </div>
      </div>
    );
  }

  const canOpen = job.status === "ready" && job.access_url;
  const isFailed = job.status === "failed" || job.status === "dead_letter";

  return (
    <div className="mx-auto max-w-3xl">
      <Link to={backTo} className="text-sm text-portal-accent hover:underline">
        {backLabel}
      </Link>
      <h1 className="mt-4 text-2xl font-semibold text-slate-900">{title}</h1>
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
        <JobPhaseStepper status={job.status} />
        {job.status_detail && (
          <p className={`mt-3 text-sm ${isFailed ? "text-red-700" : "text-slate-600"}`}>
            {job.status_detail}
          </p>
        )}
        {!canOpen && !isFailed && job.status !== "succeeded" && (
          <p className="mt-3 text-sm text-slate-600">
            This page refreshes automatically while the job is in progress.
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
        {job.campaign_id && (
          <div>
            <dt className="text-slate-500">Campaign</dt>
            <dd>
              <Link
                to="/campaigns/$campaignId"
                params={{ campaignId: job.campaign_id }}
                className="font-mono text-portal-accent hover:underline"
              >
                {job.campaign_id}
              </Link>
            </dd>
          </div>
        )}
        {job.item_key && (
          <div>
            <dt className="text-slate-500">Item key</dt>
            <dd className="font-mono">{job.item_key}</dd>
          </div>
        )}
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
        <EventTimeline events={job.events} />
      </section>
    </div>
  );
}
