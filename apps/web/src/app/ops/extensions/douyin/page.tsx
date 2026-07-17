import { redirect } from "next/navigation";
import { loginPathForSurface } from "../../../../lib/authSurface";
import { pageMetadata } from "../../../../lib/pageMetadata";

export const metadata = pageMetadata.douyinExtensionSetup;

const EXTENSION_SETUP_PATH = "/setup/douyin-extension";

/** Legacy Ops Manager entry — install/verify lives in Operator Studio Setup. */
export default function Page() {
  redirect(`${loginPathForSurface("operator")}?next=${encodeURIComponent(EXTENSION_SETUP_PATH)}`);
}
