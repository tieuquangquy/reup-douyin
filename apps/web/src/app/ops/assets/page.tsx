import { pageMetadata } from "../../../lib/pageMetadata";
import { OpsConsoleShell } from "../../../components/app-shell/OpsConsoleShell";
import { OpsAssetsPage } from "../../../components/ops-console/OpsAssetsPage";

export const metadata = pageMetadata.opsAssets;

export default function Page() {
  return (
    <OpsConsoleShell
      description="Review current and historical asset state from operational metrics."
      title="Assets"
    >
      <OpsAssetsPage />
    </OpsConsoleShell>
  );
}
