import { pageMetadata } from "../../../lib/pageMetadata";
import { OpsAssetsPage } from "../../../components/ops-console/OpsAssetsPage";

export const metadata = pageMetadata.opsAssets;

export default function Page() {
  return <OpsAssetsPage />;
}
