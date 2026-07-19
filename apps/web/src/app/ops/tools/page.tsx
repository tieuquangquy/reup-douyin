import { pageMetadata } from "../../../lib/pageMetadata";
import { OpsToolsPage } from "../../../components/ops-console/OpsToolsPage";

export const metadata = pageMetadata.opsTools;

export default function Page() {
  return <OpsToolsPage />;
}
