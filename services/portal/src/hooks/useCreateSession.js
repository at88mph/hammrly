import { useMutation, useQueryClient } from "@tanstack/react-query";
import { buildWorkload, createSession } from "../api/gateway.js";

export function useCreateSession() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ kind, workload, tenantId, projectId }) => {
      const body = {
        workload: buildWorkload(kind, workload),
      };
      if (tenantId) body.tenant_id = tenantId;
      if (projectId) body.project_id = projectId;
      return createSession(body);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["interactiveJobs"] });
    },
  });
}
