import { pageMetadata } from "../../../lib/pageMetadata";
import { OpsConsoleShell } from "../../../components/app-shell/OpsConsoleShell";
import { OpsRoutingRulesPage } from "../../../components/ops-console/OpsRoutingRulesPage";

export const metadata = pageMetadata.opsRoutingRules;

export default function Page() {
  return (
    <OpsConsoleShell
      description="Routing rule summary, queue coverage, and deterministic assignment context."
      title="Routing Rules"
    >
      <OpsRoutingRulesPage />
    </OpsConsoleShell>
  );
}
