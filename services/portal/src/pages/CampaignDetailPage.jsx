import { Link, useParams } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { getCampaign, listCampaignJobs } from "../api/query.js";
import { formatRelativeTime, statusColor } from "../utils.js";

export function CampaignDetailPage() {
  const { campaignId } = useParams({ from: "/campaigns/$campaignId" });

  const campaignQuery = useQuery({
    queryKey: ["campaign", campaignId],
    queryFn: () => getCampaign(campaignId),
    enabled: Boolean(campaignId),
    refetchInterval: (q) => {
      const s = q.state.data?.status;
      if (!s) return 3000;
      if (["completed", "partial_failed", "failed"].includes(s)) return 30000;
      return 5000;
    },
  });

  const failedJobsQuery = useQuery({
    queryKey: ["campaign-jobs", campaignId, "failed"],
    queryFn: () => listCampaignJobs(campaignId, { status: "failed", limit: 50 }),
    enabled: Boolean(campaignId),
    refetchInterval: 10000,
  });

  if (campaignQuery.isLoading) {
    return <p className="text-slate-600">Loading campaign…</p>;
  }

  if (campaignQuery.isError || !campaignQuery.data) {
    return (
      <div className="rounded border border-red-200 bg-red-50 p-4 text-red-700">
        {campaignQuery.error instanceof Error
          ? campaignQuery.error.message
          : "Campaign not found"}
        <div className="mt-2">
          <Link to="/" className="text-sm text-portal-accent hover:underline">
            Back to Home
          </Link>
        </div>
      </div>
    );
  }

  const c = campaignQuery.data;
  const failedItems = failedJobsQuery.data?.items?.length
    ? failedJobsQuery.data.items
    : c.failed_sample || [];

  return (
    <div className="mx-auto max-w-4xl">
      <Link to="/" className="text-sm text-portal-accent hover:underline">
        ← Home
      </Link>
      <h1 className="mt-4 text-2xl font-semibold text-slate-900">{c.name}</h1>
      <p className="mt-1 font-mono text-sm text-slate-600">{c.campaign_id}</p>
      {c.description && <p className="mt-2 text-sm text-slate-600">{c.description}</p>}

      <div className="mt-6 grid gap-4 sm:grid-cols-4">
        <Stat label="Status" value={c.status} badge />
        <Stat label="Progress" value={c.progress_pct != null ? `${c.progress_pct}%` : "—"} />
        <Stat label="Items" value={String(c.item_count ?? "—")} />
        <Stat
          label="Failed"
          value={`${c.fail_count} (${c.fail_pct}%)`}
          emphasize={c.fail_count > 0}
        />
      </div>

      <section className="mt-8">
        <h2 className="text-lg font-medium text-slate-900">By status</h2>
        <ul className="mt-3 flex flex-wrap gap-2">
          {Object.entries(c.by_status || {}).map(([status, count]) => (
            <li
              key={status}
              className={`rounded-full px-3 py-1 text-sm font-medium ${statusColor(status)}`}
            >
              {status}: {count}
            </li>
          ))}
          {!Object.keys(c.by_status || {}).length && (
            <li className="text-sm text-slate-500">No status counts yet.</li>
          )}
        </ul>
      </section>

      <section className="mt-8">
        <h2 className="text-lg font-medium text-slate-900">Failed jobs</h2>
        {failedItems.length ? (
          <div className="mt-3 overflow-x-auto rounded-lg border border-slate-200 bg-white">
            <table className="min-w-full text-left text-sm">
              <thead className="border-b border-slate-200 bg-slate-50 text-slate-600">
                <tr>
                  <th className="px-4 py-2 font-medium">Job</th>
                  <th className="px-4 py-2 font-medium">Item</th>
                  <th className="px-4 py-2 font-medium">Detail</th>
                  <th className="px-4 py-2 font-medium">Updated</th>
                </tr>
              </thead>
              <tbody>
                {failedItems.map((item) => (
                  <tr key={item.job_id} className="border-b border-slate-100 last:border-0">
                    <td className="px-4 py-2">
                      <Link
                        to="/jobs/$jobId"
                        params={{ jobId: item.job_id }}
                        className="font-mono text-portal-accent hover:underline"
                      >
                        {item.job_id.slice(0, 8)}…
                      </Link>
                    </td>
                    <td className="px-4 py-2 font-mono text-slate-700">
                      {item.item_key || "—"}
                    </td>
                    <td className="max-w-xs truncate px-4 py-2 text-red-700">
                      {item.status_detail || item.status}
                    </td>
                    <td className="px-4 py-2 text-slate-500">
                      {item.updated_at ? formatRelativeTime(item.updated_at) : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="mt-2 text-sm text-slate-500">No failed jobs.</p>
        )}
      </section>
    </div>
  );
}

function Stat({ label, value, badge, emphasize }) {
  return (
    <div className="rounded-lg border border-slate-200 bg-white p-4">
      <div className="text-xs uppercase tracking-wide text-slate-500">{label}</div>
      <div
        className={`mt-1 text-lg font-semibold ${
          emphasize ? "text-red-700" : "text-slate-900"
        }`}
      >
        {badge ? (
          <span className={`rounded-full px-2 py-0.5 text-sm ${statusColor(value)}`}>
            {value}
          </span>
        ) : (
          value
        )}
      </div>
    </div>
  );
}
