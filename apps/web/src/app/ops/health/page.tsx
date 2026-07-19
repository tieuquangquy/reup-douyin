import { pageMetadata } from "../../../lib/pageMetadata";
import { OpsHealthPage } from "../../../components/ops-console/OpsHealthPage";

export const metadata = pageMetadata.opsHealth;

export default function Page() {
  return <OpsHealthPage />;
}
