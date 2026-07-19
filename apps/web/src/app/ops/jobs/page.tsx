import { pageMetadata } from "../../../lib/pageMetadata";
import { OpsJobsPage } from "../../../components/ops-console/OpsJobsPage";

export const metadata = pageMetadata.opsJobs;

export default function Page() {
  return <OpsJobsPage />;
}
