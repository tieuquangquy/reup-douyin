"use client";

import type { NavSection as NavSectionConfig } from "../../lib/navigationConfig";
import { isNavItemActive, resolveNavItemHref, resolveNavItemStatusLabel } from "../../lib/navigationConfig";
import { StatusBadge } from "./StatusBadge";
import { useT } from "../../lib/i18n";

export function NavSection({
  section,
  activePath,
  currentSourceVideoId
}: {
  section: NavSectionConfig;
  activePath: string;
  currentSourceVideoId: string | null;
}) {
  const t = useT();

  return (
    <section className="app-nav-section">
      <h3>{t(section.title)}</h3>
      <div className="app-nav-items">
        {section.items.map((item) => {
          const isActive = isNavItemActive(item, activePath);
          const href = resolveNavItemHref(item, currentSourceVideoId);
          const statusLabelKey = resolveNavItemStatusLabel(item, currentSourceVideoId);
          const statusLabel = statusLabelKey ? t(statusLabelKey) : null;

          return (
            <a
              aria-current={isActive ? "page" : undefined}
              className={`app-nav-item${isActive ? " active" : ""}`}
              href={href}
              key={`${section.title}-${item.label}`}
              rel={item.external ? "noreferrer" : undefined}
              target={item.external ? "_blank" : undefined}
            >
              <span>
                <strong>{t(item.label)}</strong>
                <small>{t(item.description)}</small>
              </span>
              {statusLabel ? <StatusBadge label={statusLabel} tone="muted" /> : null}
            </a>
          );
        })}
      </div>
    </section>
  );
}
