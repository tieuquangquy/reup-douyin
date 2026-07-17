import type { Metadata } from "next";
import { ExportPackageByIdPage } from "../../../../components/operator-routes/ExportPackageByIdPage";
import { createDetailPageMetadata, pageMetadata, shortResourceId } from "../../../../lib/pageMetadata";

export async function generateMetadata({ params }: { params: Promise<{ packageId: string }> }): Promise<Metadata> {
  const { packageId } = await params;
  const base = pageMetadata.exportPackage;
  const title = typeof base.title === "string" ? base.title : "exportPackage";
  return createDetailPageMetadata(`${title} ${shortResourceId(packageId)}`, base.description ?? "");
}

export default async function Page({ params }: { params: Promise<{ packageId: string }> }) {
  const { packageId } = await params;
  return <ExportPackageByIdPage packageId={packageId} />;
}
