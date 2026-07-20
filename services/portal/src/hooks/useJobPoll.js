import { useQuery } from "@tanstack/react-query";
import { getJob } from "../api/query.js";
import { isInFlightStatus, isTerminalStatus } from "../utils.js";

/**
 * @param {string | undefined} jobId
 */
export function useJobPoll(jobId) {
  return useQuery({
    queryKey: ["job", jobId],
    queryFn: () => getJob(jobId),
    enabled: Boolean(jobId),
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      if (!status) return 2000;
      if (status === "ready" || isTerminalStatus(status)) return false;
      if (isInFlightStatus(status)) return 3000;
      return 5000;
    },
  });
}
