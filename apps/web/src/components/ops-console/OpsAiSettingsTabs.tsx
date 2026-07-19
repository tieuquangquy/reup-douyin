"use client";

import { usePathname } from "next/navigation";

export type OpsAiSettingsTab = {
  href: string;
  label: string;
};

export function OpsAiSettingsTabs({
  ariaLabel,
  tabs
}: {
  ariaLabel: string;
  tabs: readonly OpsAiSettingsTab[];
}) {
  const pathname = usePathname() || "";

  return (
    <nav className="ops-settings-tabs" aria-label={ariaLabel}>
      {tabs.map((tab) => {
        const active = pathname === tab.href || pathname.startsWith(`${tab.href}/`);
        return (
          <a
            key={tab.href}
            href={tab.href}
            className={active ? "ops-settings-tab is-active" : "ops-settings-tab"}
            aria-current={active ? "page" : undefined}
          >
            {tab.label}
          </a>
        );
      })}
    </nav>
  );
}
