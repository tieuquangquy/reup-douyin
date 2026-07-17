import { pageMetadata } from "../../../lib/pageMetadata";
import { OpsConsoleShell } from "../../../components/app-shell/OpsConsoleShell";
import { OpsToolsPage } from "../../../components/ops-console/OpsToolsPage";

export const metadata = pageMetadata.opsTools;

export default function Page() {
  return (
    <OpsConsoleShell
      description="Local commands, runbooks, and safe operational references."
      title="Tools"
    >
      <OpsToolsPage />
    </OpsConsoleShell>
  );
}
