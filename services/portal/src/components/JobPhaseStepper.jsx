import { JOB_PHASES, phaseIndexForStatus } from "../utils.js";

/**
 * @param {{ status: string }} props
 */
export function JobPhaseStepper({ status }) {
  const failed =
    status === "failed" ||
    status === "dead_letter" ||
    status === "unknown" ||
    status === "cancelled";
  const current = phaseIndexForStatus(status);
  const phases = JOB_PHASES.filter((p) => {
    // Hide ready for non-interactive terminal success path display when already succeeded
    if (status === "succeeded" && p === "ready") return false;
    return true;
  });

  return (
    <ol className="mt-4 flex flex-wrap gap-2">
      {phases.map((phase, idx) => {
        const phaseIdx = JOB_PHASES.indexOf(phase);
        const done = !failed && current >= 0 && phaseIdx <= current;
        const active = !failed && phaseIdx === current;
        return (
          <li
            key={phase}
            className={`rounded-full px-2.5 py-1 text-xs font-medium ${
              active
                ? "bg-portal-accent text-white"
                : done
                  ? "bg-emerald-100 text-emerald-800"
                  : "bg-slate-100 text-slate-500"
            }`}
          >
            {idx + 1}. {phase}
          </li>
        );
      })}
      {failed && (
        <li className="rounded-full bg-red-100 px-2.5 py-1 text-xs font-medium text-red-800">
          {status}
        </li>
      )}
    </ol>
  );
}
