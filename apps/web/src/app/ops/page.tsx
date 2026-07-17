import { pageMetadata } from "../../lib/pageMetadata";
import { OpsConsoleShell } from "../../components/app-shell/OpsConsoleShell";
import { OpsHomePage } from "../../components/ops-console/OpsHomePage";

export const metadata = pageMetadata.opsHome;

export default function OpsPage() {
  return (
    <OpsConsoleShell
      description="Operate the local system without using Swagger as the backend UI."
      title="Ops Console"
    >
      <OpsHomePage />
    </OpsConsoleShell>
  );
}
