import { pageMetadata } from "../../../lib/pageMetadata";
import { PublishHealthDashboardPage } from "../../../components/publish-health/PublishHealthDashboardPage";

export const metadata = pageMetadata.opsPublishHealth;

export default function Page() {
  return <PublishHealthDashboardPage />;
}
