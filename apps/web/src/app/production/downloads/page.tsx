import { pageMetadata } from "../../../lib/pageMetadata";
import { OperatorPlaceholderPage } from "../../../components/operator-routes/OperatorPlaceholderPage";

export const metadata = pageMetadata.downloads;

export default function Page() {
  return (
    <OperatorPlaceholderPage
      actions={[
        { label: "Review board", href: "/selection/review-board", description: "Select candidates before downloading media." },
        { label: "Pipeline", href: "/ops/pipeline", description: "Monitor stage backlog and next work without leaving Operator Studio." }
      ]}
      description="Download and asset-state UI is planned; media services and manifests already exist behind the API."
      title="Downloads"
    />
  );
}
