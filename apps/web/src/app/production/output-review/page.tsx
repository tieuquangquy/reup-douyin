import { pageMetadata } from "../../../lib/pageMetadata";
import { OutputReviewPage } from "../../../components/operator-routes/OutputReviewPage";

export const metadata = pageMetadata.outputReview;

export default function Page() {
  return <OutputReviewPage />;
}
