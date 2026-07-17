import { pageMetadata } from "../../../lib/pageMetadata";
import { OpsConsoleShell } from "../../../components/app-shell/OpsConsoleShell";
import { PublishHealthDashboardPage } from "../../../components/publish-health/PublishHealthDashboardPage";

export const metadata = pageMetadata.opsPublishHealth;

export default function Page() {
  return (
    <OpsConsoleShell
      description="Monitor published, failed, and reconcile-needed attempts across configured accounts."
      title="Publish Health"
    >
      <PublishHealthDashboardPage />
    </OpsConsoleShell>
  );
}
