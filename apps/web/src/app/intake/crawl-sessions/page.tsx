import { pageMetadata } from "../../../lib/pageMetadata";
import { OperatorPlaceholderPage } from "../../../components/operator-routes/OperatorPlaceholderPage";

export const metadata = pageMetadata.intakeCrawlSessions;

export default function Page() {
  return (
    <OperatorPlaceholderPage
      actions={[
        { label: "Source profiles", href: "/intake/profiles", description: "Return to source profile intake context." },
        { label: "Review board", href: "/selection/review-board", description: "Move to candidate selection." }
      ]}
      description="Crawl session UI is planned; this route reserves the operator location for ingest visibility."
      title="Crawl Sessions"
    />
  );
}
