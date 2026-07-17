import { pageMetadata } from "../../../lib/pageMetadata";
import { OpsConsoleShell } from "../../../components/app-shell/OpsConsoleShell";
import { OpsTtsAiPage } from "../../../components/ops-console/OpsTtsAiPage";

export const metadata = pageMetadata.opsTtsAi;

export default function Page() {
  return (
    <OpsConsoleShell
      description="Switch Vietnamese TTS providers (edge, VieNeu, cloud, HTTP) without changing Generate TTS."
      title="TTS settings"
    >
      <OpsTtsAiPage />
    </OpsConsoleShell>
  );
}
