"use client";

import { useT } from "../../lib/i18n";
import { OperatorStudioShell } from "../app-shell/OperatorStudioShell";
import { ContentAiConfiguration } from "./ContentAiConfiguration";
import { PublishingSettingsNav } from "./PublishingSettingsNav";


export function ContentIntelligenceSettingsPage() {
  const t = useT();

  return <OperatorStudioShell
    description={t("publishingSettings.description")}
    title={t("publishingSettings.title")}
  >
    <main className="publishing-settings-page">
      <PublishingSettingsNav />
      <ContentAiConfiguration />
    </main>
  </OperatorStudioShell>;
}
