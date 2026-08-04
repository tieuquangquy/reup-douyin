import { redirect } from "next/navigation";

import { CAPTURE_INBOX_HREF } from "../../../../../lib/captureInboxRoutes";

/** Legacy Ops-era URL — Capture Inbox now lives in Operator Studio under /selection. */
export default function LegacyCaptureInboxRedirectPage() {
  redirect(CAPTURE_INBOX_HREF);
}
