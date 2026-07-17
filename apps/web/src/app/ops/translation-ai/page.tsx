import { pageMetadata } from "../../../lib/pageMetadata";
import { OpsConsoleShell } from "../../../components/app-shell/OpsConsoleShell";
import { OpsTranslationAiPage } from "../../../components/ops-console/OpsTranslationAiPage";

export const metadata = pageMetadata.opsTranslationAi;

export default function Page() {
  return (
    <OpsConsoleShell
      description="LLM connection and ZH→VI dialogue system prompt for Translate jobs."
      title="Translation settings"
    >
      <OpsTranslationAiPage />
    </OpsConsoleShell>
  );
}
