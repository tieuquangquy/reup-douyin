import { pageMetadata } from "../../../lib/pageMetadata";
import { ReupQueuePage } from "../../../components/reup-queue/ReupQueuePage";

export const metadata = pageMetadata.reupQueue;

export default function Page() {
  return <ReupQueuePage />;
}
