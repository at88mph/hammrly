import { useInfiniteQuery } from "@tanstack/react-query";
import { listInteractiveJobs } from "../api/query.js";
import { INTERACTIVE_LIST_STATUSES, isInFlightStatus } from "../utils.js";

const PAGE_SIZE = 50;

export function useInteractiveJobs() {
  return useInfiniteQuery({
    queryKey: ["interactiveJobs", INTERACTIVE_LIST_STATUSES],
    queryFn: ({ pageParam = 0 }) =>
      listInteractiveJobs({
        limit: PAGE_SIZE,
        offset: pageParam,
        status: INTERACTIVE_LIST_STATUSES,
      }),
    initialPageParam: 0,
    getNextPageParam: (lastPage) => {
      if (lastPage.items.length < lastPage.limit) return undefined;
      return lastPage.offset + lastPage.limit;
    },
    refetchInterval: (query) => {
      const pages = query.state.data?.pages ?? [];
      const items = pages.flatMap((p) => p.items);
      const hasInFlight = items.some((j) => isInFlightStatus(j.status));
      return hasInFlight ? 10_000 : 60_000;
    },
  });
}
