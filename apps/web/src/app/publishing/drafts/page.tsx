import { pageMetadata } from "../../../lib/pageMetadata";
import { PublishDraftsIndexPage } from "../../../components/operator-routes/PublishDraftsIndexPage";

export const metadata = pageMetadata.publishDrafts;

export default function Page() {
  return <PublishDraftsIndexPage />;
}
