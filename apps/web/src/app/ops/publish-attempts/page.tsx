import { pageMetadata } from "../../../lib/pageMetadata";
import { OpsPublishAttemptsPage } from "../../../components/ops-console/OpsPublishAttemptsPage";

export const metadata = pageMetadata.opsPublishAttempts;

export default function Page() {
  return <OpsPublishAttemptsPage />;
}
