import { pageMetadata } from "../../../lib/pageMetadata";
import { OpsConsoleShell } from "../../../components/app-shell/OpsConsoleShell";
import { OpsPublishAttemptsPage } from "../../../components/ops-console/OpsPublishAttemptsPage";

export const metadata = pageMetadata.opsPublishAttempts;

export default function Page() {
  return (
    <OpsConsoleShell
      description="Inspect connector attempts, external IDs, status mapping, and publish errors."
      title="Publish Attempts"
    >
      <OpsPublishAttemptsPage />
    </OpsConsoleShell>
  );
}
