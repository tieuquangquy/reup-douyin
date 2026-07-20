import { pageMetadata } from "../../../lib/pageMetadata";
import { PublishControlPlanePage } from "../../../components/publish-control/PublishControlPlanePage";

export const metadata = pageMetadata.opsPublishControl;

export default function Page() {
  return <PublishControlPlanePage />;
}
