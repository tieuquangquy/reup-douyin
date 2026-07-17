import { pageMetadata } from "../../../lib/pageMetadata";
import { OpsConsoleShell } from "../../../components/app-shell/OpsConsoleShell";
import { OpsJobsPage } from "../../../components/ops-console/OpsJobsPage";

export const metadata = pageMetadata.opsJobs;

export default function Page() {
  return (
    <OpsConsoleShell
      description="Inspect running, failed, retryable, and stale durable jobs."
      title="Jobs"
    >
      <OpsJobsPage />
    </OpsConsoleShell>
  );
}
