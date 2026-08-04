"use client";

import type { NavIconName, NavSection as NavSectionConfig } from "../../lib/navigationConfig";
import { isNavItemActive, resolveNavItemHref, resolveNavItemStatusLabel } from "../../lib/navigationConfig";
import { StatusBadge } from "./StatusBadge";
import { useT } from "../../lib/i18n";

function NavItemIcon({ name }: { name: NavIconName }) {
  if (name === "home") return <svg viewBox="0 0 24 24"><path d="m4 11 8-7 8 7v8.5a.5.5 0 0 1-.5.5h-15a.5.5 0 0 1-.5-.5V11Z" /><path d="M9 20v-6h6v6" /></svg>;
  if (name === "pipeline") return <svg viewBox="0 0 24 24"><circle cx="5" cy="6" r="2" /><circle cx="19" cy="6" r="2" /><circle cx="12" cy="18" r="2" /><path d="M7 6h10M6.5 7.5 11 16m6.5-8.5L13 16" /></svg>;
  if (name === "inbox") return <svg viewBox="0 0 24 24"><path d="M4 5h16v14H4z" /><path d="M4 14h4l2 2h4l2-2h4" /></svg>;
  if (name === "review") return <svg viewBox="0 0 24 24"><path d="M7 4h10v3H7zM5 6h14v14H5z" /><path d="m8.5 13 2.2 2.2 4.8-5" /></svg>;
  if (name === "queue") return <svg viewBox="0 0 24 24"><path d="m12 4 8 4-8 4-8-4 8-4Z" /><path d="m4 12 8 4 8-4M4 16l8 4 8-4" /></svg>;
  if (name === "output") return <svg viewBox="0 0 24 24"><rect height="14" rx="2" width="16" x="4" y="5" /><path d="m10 9 5 3-5 3V9Z" /><path d="m15.5 18 1.5 1.5 3-3" /></svg>;
  if (name === "transcript") return <svg viewBox="0 0 24 24"><path d="M6 4h12v16H6z" /><path d="M9 8h6M9 12h6M9 16h4" /></svg>;
  if (name === "final") return <svg viewBox="0 0 24 24"><path d="M12 3.5 19 6v5.2c0 4.2-2.6 7.4-7 9.3-4.4-1.9-7-5.1-7-9.3V6l7-2.5Z" /><path d="m9 12 2 2 4-4" /></svg>;
  if (name === "draft") return <svg viewBox="0 0 24 24"><path d="M6 3.5h8l4 4V20H6z" /><path d="M14 3.5V8h4M9 12h6M9 16h4" /></svg>;
  if (name === "package") return <svg viewBox="0 0 24 24"><path d="m4 7 8-4 8 4v10l-8 4-8-4V7Z" /><path d="m4 7 8 4 8-4M12 11v10M8 5l8 4" /></svg>;
  if (name === "handoff") return <svg viewBox="0 0 24 24"><path d="m4 6 16 6-16 6 3-6-3-6Z" /><path d="M7 12h8" /></svg>;
  if (name === "extension") return <svg viewBox="0 0 24 24"><path d="M8 4v4H4v8h4v4h8v-4h4V8h-4V4H8Z" /><path d="M9 12h6M12 9v6" /></svg>;
  if (name === "dashboard") return <svg viewBox="0 0 24 24"><rect height="7" rx="1.5" width="7" x="4" y="4" /><rect height="7" rx="1.5" width="7" x="13" y="4" /><rect height="7" rx="1.5" width="7" x="4" y="13" /><rect height="7" rx="1.5" width="7" x="13" y="13" /></svg>;
  if (name === "health") return <svg viewBox="0 0 24 24"><path d="M3 12h4l2-5 4 10 2-5h6" /><path d="M5 5.5A9 9 0 0 1 20.5 9M19 17a9 9 0 0 1-14.5-2" /></svg>;
  if (name === "jobs") return <svg viewBox="0 0 24 24"><rect height="14" rx="2" width="16" x="4" y="6" /><path d="M9 6V4h6v2M8 11h8M8 15h5" /></svg>;
  if (name === "users") return <svg viewBox="0 0 24 24"><circle cx="9" cy="8" r="3" /><path d="M3.5 19c.7-3.5 2.5-5.2 5.5-5.2s4.8 1.7 5.5 5.2" /><circle cx="17" cy="9" r="2.3" /><path d="M15.5 14.2c2.9-.5 4.6 1.1 5 4.2" /></svg>;
  if (name === "accounts") return <svg viewBox="0 0 24 24"><rect height="15" rx="2" width="18" x="3" y="4.5" /><circle cx="9" cy="10" r="2.2" /><path d="M5.8 16c.5-2.1 1.6-3.1 3.2-3.1s2.7 1 3.2 3.1M15 9h4M15 13h4M15 17h3" /></svg>;
  if (name === "translation") return <svg viewBox="0 0 24 24"><path d="M4 5h8M8 3v2m-2 4c1.6 2.4 3.8 4.1 6.5 5M11 5c-.7 4-3 7.1-7 9" /><path d="m14 19 3.2-8 3.3 8M15.2 16h4" /></svg>;
  if (name === "caption") return <svg viewBox="0 0 24 24"><rect height="14" rx="2" width="18" x="3" y="5" /><path d="M7 11h4M7 15h3M13 11h4M12 15h5" /></svg>;
  if (name === "settings") return <svg viewBox="0 0 24 24"><path d="M4 7h10M18 7h2M4 17h2M10 17h10" /><circle cx="16" cy="7" r="2" /><circle cx="8" cy="17" r="2" /></svg>;
  return <svg viewBox="0 0 24 24"><path d="M8 5v8a4 4 0 0 0 8 0V5" /><path d="M5 12v1a7 7 0 0 0 14 0v-1M12 20v2" /></svg>;
}

function NavItemIndicator() {
  return <span aria-hidden="true" className="app-nav-item__indicator"><svg viewBox="0 0 12 12"><path d="m4 2.5 3.5 3.5L4 9.5" /></svg></span>;
}

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
              <span aria-hidden="true" className={`app-nav-item__icon is-${item.icon}`}><NavItemIcon name={item.icon} /></span>
              <span className="app-nav-item__copy">
                <strong>{t(item.label)}</strong>
                <small>{t(item.description)}</small>
              </span>
              <span className="app-nav-item__meta">{statusLabel ? <StatusBadge label={statusLabel} tone="muted" /> : <NavItemIndicator />}</span>
            </a>
          );
        })}
      </div>
    </section>
  );
}
