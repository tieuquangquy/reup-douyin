import { OpsAccountsPage } from "../../../components/ops-console/OpsAccountsPage";
import { pageMetadata } from "../../../lib/pageMetadata";

export const metadata = pageMetadata.opsAccounts;

export default function Page() {
  return <OpsAccountsPage />;
}
