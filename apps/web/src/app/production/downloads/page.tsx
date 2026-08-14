import { pageMetadata } from "../../../lib/pageMetadata";
import { ReupQueuePage } from "../../../components/reup-queue/ReupQueuePage";

export const metadata = pageMetadata.downloads;

export default function Page() {
  return <ReupQueuePage initialFilter="download" />;
}
