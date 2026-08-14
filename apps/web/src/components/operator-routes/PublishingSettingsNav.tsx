"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useT } from "../../lib/i18n";

type SettingsNavIconKind = "spark" | "catalog" | "comments";

function SettingsNavIcon({ kind }: { kind: SettingsNavIconKind }) {
  const common = { className: "publishing-settings-icon", fill: "none", viewBox: "0 0 24 24", "aria-hidden": true } as const;
  if (kind === "catalog") {
    return (
      <svg {...common}>
        <path d="M7 5.5h10v13H7z" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.8" />
        <path d="M10 9h4M10 12.5h4M10 16h2.5" stroke="currentColor" strokeLinecap="round" strokeWidth="1.8" />
      </svg>
    );
  }
  if (kind === "comments") {
    return (
      <svg {...common}>
        <path d="M5 6.5h14v9H9l-4 3.2z" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.8" />
      </svg>
    );
  }
  return (
    <svg {...common}>
      <path d="M12 3.5 13.1 8.8 18.5 10 13.1 11.2 12 16.5 10.9 11.2 5.5 10 10.9 8.8z" stroke="currentColor" strokeLinejoin="round" strokeWidth="1.8" />
      <path d="M18.2 14.8 18.8 17.2 21.2 17.8 18.8 18.4 18.2 20.8 17.6 18.4 15.2 17.8 17.6 17.2z" stroke="currentColor" strokeLinejoin="round" strokeWidth="1.8" />
    </svg>
  );
}

const SETTINGS_ITEMS: Array<{
  href: string;
  icon: SettingsNavIconKind;
  label: string;
  hint: string;
}> = [
  {
    href: "/publishing/settings/content-intelligence",
    icon: "spark",
    label: "publishingSettings.contentIntelligence",
    hint: "publishingSettings.contentIntelligenceHint",
  },
  {
    href: "/publishing/settings/affiliate-catalog",
    icon: "catalog",
    label: "publishingSettings.affiliateCatalog",
    hint: "publishingSettings.affiliateCatalogHint",
  },
  {
    href: "/publishing/settings/affiliate-comments",
    icon: "comments",
    label: "publishingSettings.affiliateComments",
    hint: "publishingSettings.affiliateCommentsHint",
  },
];

export function PublishingSettingsNav() {
  const pathname = usePathname();
  const t = useT();
  return (
    <nav aria-label={t("publishingSettings.sections")} className="publishing-settings-tabs is-v1 is-v4">
      {SETTINGS_ITEMS.map((item) => {
        const active = pathname === item.href;
        return (
          <Link
            aria-current={active ? "page" : undefined}
            className={active ? "is-active" : ""}
            href={item.href}
            key={item.href}
            title={t(item.hint)}
          >
            <SettingsNavIcon kind={item.icon} />
            <strong>{t(item.label)}</strong>
            <small>{t(item.hint)}</small>
          </Link>
        );
      })}
    </nav>
  );
}
