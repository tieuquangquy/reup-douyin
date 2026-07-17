import type { Metadata } from "next";
import { createDetailPageMetadata, pageMetadata, shortResourceId } from "../../../../lib/pageMetadata";
import { PublishDraftByIdPage } from "../../../../components/operator-routes/PublishDraftByIdPage";

export async function generateMetadata({ params }: { params: Promise<{ draftId: string }> }): Promise<Metadata> {
  const { draftId } = await params;
  const base = pageMetadata.publishDraft;
  const title = typeof base.title === "string" ? base.title : "publishDraft";
  return createDetailPageMetadata(`${title} ${shortResourceId(draftId)}`, base.description ?? "");
}

export default async function Page({ params }: { params: Promise<{ draftId: string }> }) {
const { draftId } = await params;
  return <PublishDraftByIdPage draftId={draftId} />;
}
