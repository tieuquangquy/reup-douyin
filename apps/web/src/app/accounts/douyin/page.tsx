import { redirect } from "next/navigation";
import { pageMetadata } from "../../../lib/pageMetadata";

export const metadata = pageMetadata.douyinExtensionSetup;

/** Legacy Douyin Accounts entry — Phase 1 setup lives at Extension Setup. */
export default function Page() {
  redirect("/setup/douyin-extension");
}
