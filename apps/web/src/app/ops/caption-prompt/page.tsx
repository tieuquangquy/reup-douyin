import { pageMetadata } from "../../../lib/pageMetadata";
import { OpsConsoleShell } from "../../../components/app-shell/OpsConsoleShell";
import { OpsCaptionPromptPage } from "../../../components/ops-console/OpsCaptionPromptPage";

export const metadata = pageMetadata.opsCaptionPrompt;

export default function Page() {
  return (
    <OpsConsoleShell
      description="System prompt for hard-sub caption translation. Separate from dialogue Translation prompt."
      title="Caption AI settings"
    >
      <OpsCaptionPromptPage />
    </OpsConsoleShell>
  );
}
