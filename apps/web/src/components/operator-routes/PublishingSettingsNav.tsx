"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useT } from "../../lib/i18n";


const SETTINGS_ITEMS = [
  {
    href: "/publishing/settings/content-intelligence",
    icon: "AI",
    label: "publishingSettings.contentIntelligence",
    hint: "publishingSettings.contentIntelligenceHint",
  },
  {
    href: "/publishing/settings/affiliate-catalog",
    icon: "SKU",
    label: "publishingSettings.affiliateCatalog",
    hint: "publishingSettings.affiliateCatalogHint",
  },
  {
    href: "/publishing/settings/affiliate-comments",
    icon: "CMT",
    label: "publishingSettings.affiliateComments",
    hint: "publishingSettings.affiliateCommentsHint",
  },
] as const;


export function PublishingSettingsNav() {
  const pathname = usePathname();
  const t = useT();
  return <nav aria-label={t("publishingSettings.sections")} className="publishing-settings-tabs">
    {SETTINGS_ITEMS.map((item) => <Link aria-current={pathname === item.href ? "page" : undefined} className={pathname === item.href ? "is-active" : ""} href={item.href} key={item.href}><span aria-hidden="true">{item.icon}</span><strong>{t(item.label)}</strong><small>{t(item.hint)}</small></Link>)}
  </nav>;
}
