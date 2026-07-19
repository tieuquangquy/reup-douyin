import { pageMetadata } from "../../../lib/pageMetadata";
import { OpsReconciliationPage } from "../../../components/ops-console/OpsReconciliationPage";

export const metadata = pageMetadata.opsReconciliation;

export default function Page() {
  return <OpsReconciliationPage />;
}
