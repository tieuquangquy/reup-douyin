import { pageMetadata } from "../../../lib/pageMetadata";
import { OpsConsoleShell } from "../../../components/app-shell/OpsConsoleShell";
import { OpsCaptionAiPage } from "../../../components/ops-console/OpsCaptionAiPage";

export const metadata = pageMetadata.opsCaptionAi;

export default function Page() {
  return (
    <OpsConsoleShell
      description="LLM for hard-sub OCR caption ZH to VI. Separate from dialogue Translation settings."
      title="Caption AI settings"
    >
      <OpsCaptionAiPage />
    </OpsConsoleShell>
  );
}
