"use client";

import { usePathname } from "next/navigation";
import { useT } from "../../lib/i18n";

const TABS = [
  { href: "/ops/translation-ai", labelKey: "nav.translationAi" },
  { href: "/ops/translation-prompt", labelKey: "nav.translationPrompt" }
] as const;

export function OpsTranslationSettingsTabs() {
  const t = useT();
  const pathname = usePathname() || "";

  return (
    <nav className="ops-settings-tabs" aria-label={t("opsTranslationSettings.tabsLabel")}>
      {TABS.map((tab) => {
        const active = pathname === tab.href || pathname.startsWith(`${tab.href}/`);
        return (
          <a
            key={tab.href}
            href={tab.href}
            className={active ? "ops-settings-tab is-active" : "ops-settings-tab"}
            aria-current={active ? "page" : undefined}
          >
            {t(tab.labelKey)}
          </a>
        );
      })}
    </nav>
  );
}
