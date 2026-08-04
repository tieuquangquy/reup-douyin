"use client";

import { useT } from "../../lib/i18n";
import { OperatorStudioShell } from "../app-shell/OperatorStudioShell";
import { AffiliateCatalogPage } from "./AffiliateCatalogPage";
import { PublishingSettingsNav } from "./PublishingSettingsNav";


export function AffiliateCatalogSettingsPage() {
  const t = useT();
  return <OperatorStudioShell
    description={t("publishingSettings.description")}
    title={t("publishingSettings.title")}
  >
    <main className="publishing-settings-page">
      <PublishingSettingsNav />
      <AffiliateCatalogPage />
    </main>
  </OperatorStudioShell>;
}
