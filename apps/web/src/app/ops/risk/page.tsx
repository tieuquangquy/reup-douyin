import { pageMetadata } from "../../../lib/pageMetadata";
import { OpsConsoleShell } from "../../../components/app-shell/OpsConsoleShell";
import { OpsRiskPage } from "../../../components/ops-console/OpsRiskPage";

export const metadata = pageMetadata.opsRisk;

export default function Page() {
  return (
    <OpsConsoleShell
      description="Open, acknowledged, waived, and resolved warnings across operator targets."
      title="Risk"
    >
      <OpsRiskPage />
    </OpsConsoleShell>
  );
}
