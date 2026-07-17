import { pageMetadata } from "../../../lib/pageMetadata";
import { OpsConsoleShell } from "../../../components/app-shell/OpsConsoleShell";
import { PublishControlPlanePage } from "../../../components/publish-control/PublishControlPlanePage";

export const metadata = pageMetadata.opsPublishControl;

export default function Page() {
  return (
    <OpsConsoleShell
      description="Assign and rebalance ready publish drafts across Facebook Page accounts."
      title="Publish Control"
    >
      <PublishControlPlanePage />
    </OpsConsoleShell>
  );
}
