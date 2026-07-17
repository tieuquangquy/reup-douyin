import { pageMetadata } from "../../../lib/pageMetadata";
import { OperatorPlaceholderPage } from "../../../components/operator-routes/OperatorPlaceholderPage";

export const metadata = pageMetadata.intakeProfiles;

export default function Page() {
  return (
    <OperatorPlaceholderPage
      actions={[
        { label: "Crawl sessions", href: "/intake/crawl-sessions", description: "Check ingest session placeholders." },
        { label: "Review candidates", href: "/selection/review-board", description: "Continue with currently seeded candidate data." }
      ]}
      description="Source profile management is planned; backend profile APIs already exist for later UI wiring."
      title="Source Profiles"
    />
  );
}
