import { useParams } from "@tanstack/react-router";
import { JobDetailView } from "./SessionDetailPage.jsx";

export function JobDetailPage() {
  const { jobId } = useParams({ from: "/jobs/$jobId" });
  return (
    <JobDetailView
      jobId={jobId}
      backTo="/"
      backLabel="← Home"
      title="Job"
    />
  );
}
