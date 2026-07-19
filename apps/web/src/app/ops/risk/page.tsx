import { pageMetadata } from "../../../lib/pageMetadata";
import { OpsRiskPage } from "../../../components/ops-console/OpsRiskPage";

export const metadata = pageMetadata.opsRisk;

export default function Page() {
  return <OpsRiskPage />;
}
