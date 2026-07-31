/**
 * @param {{ events?: import('../api/types.js').SubmissionEvent[] }} props
 */
export function EventTimeline({ events }) {
  if (!events?.length) {
    return <p className="mt-2 text-sm text-slate-500">No events yet.</p>;
  }

  return (
    <ol className="mt-4 space-y-3">
      {events.map((ev) => (
        <li
          key={ev.id}
          className="rounded border border-slate-200 bg-white px-4 py-3 text-sm"
        >
          <div className="flex justify-between gap-4">
            <span className="font-medium text-slate-800">{ev.event_type}</span>
            <time className="shrink-0 text-slate-500">
              {new Date(ev.occurred_at).toLocaleString()}
            </time>
          </div>
          {ev.payload_json && Object.keys(ev.payload_json).length > 0 && (
            <pre className="mt-2 overflow-x-auto rounded bg-slate-50 p-2 text-xs text-slate-700">
              {JSON.stringify(ev.payload_json, null, 2)}
            </pre>
          )}
        </li>
      ))}
    </ol>
  );
}
