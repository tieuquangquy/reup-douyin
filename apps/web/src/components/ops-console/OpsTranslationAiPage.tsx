"use client";

export { modelListReady, canShowModel } from "./OpsLlmAiSetupsPage";
import { OpsLlmAiSetupsPage } from "./OpsLlmAiSetupsPage";

export function OpsTranslationAiPage() {
  return <OpsLlmAiSetupsPage variant="translation" />;
}
