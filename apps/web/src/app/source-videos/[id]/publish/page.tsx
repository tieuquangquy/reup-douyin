import type { Metadata } from "next";
import { createDetailPageMetadata, pageMetadata, shortResourceId } from "../../../../lib/pageMetadata";
import { OperatorPublishDraftPage } from "../../../../components/operator-routes/OperatorPublishDraftPage";

export async function generateMetadata({ params }: { params: Promise<{ id: string }> }): Promise<Metadata> {
  const { id } = await params;
  const base = pageMetadata.publishDraft;
  const title = typeof base.title === "string" ? base.title : "publishDraft";
  return createDetailPageMetadata(`${title} ${shortResourceId(id)}`, base.description ?? "");
}

export default async function Page({ params }: { params: Promise<{ id: string }> }) {
const { id } = await params;
  return <OperatorPublishDraftPage sourceVideoId={id} />;
}
