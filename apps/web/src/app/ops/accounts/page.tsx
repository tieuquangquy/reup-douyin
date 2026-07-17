import { pageMetadata } from "../../../lib/pageMetadata";
import { OpsConsoleShell } from "../../../components/app-shell/OpsConsoleShell";
import { OpsAccountsPage } from "../../../components/ops-console/OpsAccountsPage";

export const metadata = pageMetadata.opsAccounts;

export default function Page() {
  return (
    <OpsConsoleShell
      description="Configured platform accounts, health, holds, and backlog context."
      title="Accounts"
    >
      <OpsAccountsPage />
    </OpsConsoleShell>
  );
}
