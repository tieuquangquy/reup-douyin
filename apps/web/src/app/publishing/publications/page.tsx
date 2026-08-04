import { PublicationLibraryPage } from "../../../components/operator-routes/PublicationLibraryPage";
import { pageMetadata } from "../../../lib/pageMetadata";

export const metadata = pageMetadata.publications;

type PublicationPageProps = {
  searchParams?: Promise<{ account_id?: string | string[] }>;
};

export default async function Page({ searchParams }: PublicationPageProps) {
  const params = await searchParams;
  const accountId = params?.account_id;
  const initialAccountId = Array.isArray(accountId) ? accountId[0] ?? "" : accountId ?? "";

  return <PublicationLibraryPage initialAccountId={initialAccountId} />;
}
