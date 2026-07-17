import { pageMetadata } from "../../../lib/pageMetadata";
import { OpsConsoleShell } from "../../../components/app-shell/OpsConsoleShell";
import { OpsHealthPage } from "../../../components/ops-console/OpsHealthPage";

export const metadata = pageMetadata.opsHealth;

export default function Page() {
  return (
    <OpsConsoleShell
      description="API, DB, queue, storage, risk, and publish readiness summary."
      title="System Health"
    >
      <OpsHealthPage />
    </OpsConsoleShell>
  );
}
