import { pageMetadata } from "../../lib/pageMetadata";
import { OpsHomePage } from "../../components/ops-console/OpsHomePage";

export const metadata = pageMetadata.opsHome;

export default function OpsPage() {
  return <OpsHomePage />;
}
