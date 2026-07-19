import type { Metadata } from "next";
import { createDetailPageMetadata, pageMetadata, shortResourceId } from "../../../../lib/pageMetadata";
import { OperatorTranscriptEditorPage } from "../../../../components/operator-routes/OperatorTranscriptEditorPage";

export async function generateMetadata({ params }: { params: Promise<{ sourceVideoId: string }> }): Promise<Metadata> {
  const { sourceVideoId } = await params;
  const base = pageMetadata.transcriptEditor;
  const title = typeof base.title === "string" ? base.title : "transcriptEditor";
  return createDetailPageMetadata(`${title} ${shortResourceId(sourceVideoId)}`, base.description ?? "");
}

export default async function Page({ params }: { params: Promise<{ sourceVideoId: string }> }) {
  const { sourceVideoId } = await params;
  return <OperatorTranscriptEditorPage sourceVideoId={sourceVideoId} />;
}
