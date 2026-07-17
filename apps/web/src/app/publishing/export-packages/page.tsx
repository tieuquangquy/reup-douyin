import { pageMetadata } from "../../../lib/pageMetadata";
import { ExportPackagesIndexPage } from "../../../components/operator-routes/ExportPackagesIndexPage";

export const metadata = pageMetadata.exportPackages;

export default function Page() {
  return <ExportPackagesIndexPage />;
}
