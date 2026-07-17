import { pageMetadata } from "../lib/pageMetadata";
import { OperatorHomePage } from "../components/operator-home/OperatorHomePage";

export const metadata = pageMetadata.home;

export default function HomePage() {
  return <OperatorHomePage />;
}
