"use client";

import { useT } from "../../lib/i18n";
import { OpsAiSettingsTabs } from "./OpsAiSettingsTabs";

export function OpsCaptionSettingsTabs() {
  const t = useT();

  return (
    <OpsAiSettingsTabs
      ariaLabel={t("opsCaptionSettings.tabsLabel")}
      tabs={[
        { href: "/ops/caption-ai", label: t("nav.captionAi") },
        { href: "/ops/caption-prompt", label: t("nav.captionPrompt") }
      ]}
    />
  );
}
