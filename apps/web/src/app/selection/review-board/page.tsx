import { ReviewBoardPage } from "../../../components/review-board/ReviewBoardPage";
import { pageMetadata } from "../../../lib/pageMetadata";

export const metadata = pageMetadata.reviewBoard;

export default function Page() {
  return <ReviewBoardPage />;
}
