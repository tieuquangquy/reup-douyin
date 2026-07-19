"use client";

import { useT } from "../../lib/i18n";
import { OpsAiSettingsTabs } from "./OpsAiSettingsTabs";

export function OpsTranslationSettingsTabs() {
  const t = useT();

  return (
    <OpsAiSettingsTabs
      ariaLabel={t("opsTranslationSettings.tabsLabel")}
      tabs={[
        { href: "/ops/translation-ai", label: t("nav.translationAi") },
        { href: "/ops/translation-prompt", label: t("nav.translationPrompt") }
      ]}
    />
  );
}
