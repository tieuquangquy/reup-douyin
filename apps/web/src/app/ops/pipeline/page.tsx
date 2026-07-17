import { pageMetadata } from "../../../lib/pageMetadata";
import { PipelineDashboardPage } from "../../../components/operator-routes/PipelineDashboardPage";

export const metadata = pageMetadata.pipelineDashboard;

export default function Page() {
  return <PipelineDashboardPage />;
}
