import { pageMetadata } from "../../../lib/pageMetadata";
import { PublishHandoffsIndexPage } from "../../../components/operator-routes/PublishHandoffsIndexPage";

export const metadata = pageMetadata.publishHandoffs;

export default function Page() {
  return <PublishHandoffsIndexPage />;
}
