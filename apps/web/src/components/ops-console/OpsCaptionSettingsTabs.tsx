"use client";

import { usePathname } from "next/navigation";
import { useT } from "../../lib/i18n";

const TABS = [
  { href: "/ops/caption-ai", labelKey: "nav.captionAi" },
  { href: "/ops/caption-prompt", labelKey: "nav.captionPrompt" }
] as const;

export function OpsCaptionSettingsTabs() {
  const t = useT();
  const pathname = usePathname() || "";

  return (
    <nav className="ops-settings-tabs" aria-label={t("opsCaptionSettings.tabsLabel")}>
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
