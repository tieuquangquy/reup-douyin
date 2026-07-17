import type { Metadata } from "next";
import { createDetailPageMetadata, pageMetadata, shortResourceId } from "../../../../lib/pageMetadata";
import { PublishHandoffByIdPage } from "../../../../components/operator-routes/PublishHandoffByIdPage";

export async function generateMetadata({ params }: { params: Promise<{ handoffId: string }> }): Promise<Metadata> {
  const { handoffId } = await params;
  const base = pageMetadata.publishHandoff;
  const title = typeof base.title === "string" ? base.title : "publishHandoff";
  return createDetailPageMetadata(`${title} ${shortResourceId(handoffId)}`, base.description ?? "");
}

export default async function Page({ params }: { params: Promise<{ handoffId: string }> }) {
const { handoffId } = await params;
  return <PublishHandoffByIdPage handoffId={handoffId} />;
}
