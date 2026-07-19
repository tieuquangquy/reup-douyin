import { pageMetadata } from "../../../lib/pageMetadata";
import { OpsAccountsPage } from "../../../components/ops-console/OpsAccountsPage";

export const metadata = pageMetadata.opsAccounts;

export default function Page() {
  return <OpsAccountsPage />;
}
