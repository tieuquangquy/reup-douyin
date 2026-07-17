import { pageMetadata } from "../../../lib/pageMetadata";
import { OpsConsoleShell } from "../../../components/app-shell/OpsConsoleShell";
import { OpsTranslationPromptPage } from "../../../components/ops-console/OpsTranslationPromptPage";

export const metadata = pageMetadata.opsTranslationPrompt;

export default function Page() {
  return (
    <OpsConsoleShell
      description="LLM connection and ZH→VI dialogue system prompt for Translate jobs."
      title="Translation settings"
    >
      <OpsTranslationPromptPage />
    </OpsConsoleShell>
  );
}
