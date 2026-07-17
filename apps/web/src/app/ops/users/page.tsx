import { pageMetadata } from "../../../lib/pageMetadata";
import { OpsUsersPage } from "../../../components/ops-console/OpsUsersPage";

export const metadata = pageMetadata.opsUsers;

export default function Page() {
  return <OpsUsersPage />;
}
