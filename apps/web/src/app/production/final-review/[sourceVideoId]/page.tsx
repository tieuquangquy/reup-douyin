import type { Metadata } from "next";
import { createDetailPageMetadata, pageMetadata, shortResourceId } from "../../../../lib/pageMetadata";
import { OperatorFinalReviewPage } from "../../../../components/operator-routes/OperatorFinalReviewPage";

export async function generateMetadata({ params }: { params: Promise<{ sourceVideoId: string }> }): Promise<Metadata> {
  const { sourceVideoId } = await params;
  const base = pageMetadata.finalReview;
  const title = typeof base.title === "string" ? base.title : "finalReview";
  return createDetailPageMetadata(`${title} ${shortResourceId(sourceVideoId)}`, base.description ?? "");
}

export default async function Page({ params }: { params: Promise<{ sourceVideoId: string }> }) {
const { sourceVideoId } = await params;
  return <OperatorFinalReviewPage sourceVideoId={sourceVideoId} />;
}
