import { pageMetadata } from "../../lib/pageMetadata";
import { IntakePage } from "../../components/intake/IntakePage";

export const metadata = pageMetadata.intake;

export default function Page() {
  return <IntakePage />;
}
