"use client";

export { captionModelListReady, captionCanShowModel } from "./OpsLlmAiSetupsPage";
import { OpsLlmAiSetupsPage } from "./OpsLlmAiSetupsPage";

export function OpsCaptionAiPage() {
  return <OpsLlmAiSetupsPage variant="caption" />;
}
