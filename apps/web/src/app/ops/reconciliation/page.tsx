import { pageMetadata } from "../../../lib/pageMetadata";
import { OpsConsoleShell } from "../../../components/app-shell/OpsConsoleShell";
import { OpsReconciliationPage } from "../../../components/ops-console/OpsReconciliationPage";

export const metadata = pageMetadata.opsReconciliation;

export default function Page() {
  return (
    <OpsConsoleShell
      description="Refresh uncertain publish attempts and keep internal/external status explicit."
      title="Reconciliation"
    >
      <OpsReconciliationPage />
    </OpsConsoleShell>
  );
}
