import { pageMetadata } from "../../../lib/pageMetadata";
import { OpsRoutingRulesPage } from "../../../components/ops-console/OpsRoutingRulesPage";

export const metadata = pageMetadata.opsRoutingRules;

export default function Page() {
  return <OpsRoutingRulesPage />;
}
