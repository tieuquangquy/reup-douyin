"use client";

import { useEffect, useRef, type ReactNode } from "react";
import { usePathname } from "next/navigation";
import type { NavSurface } from "../../lib/navigationConfig";
import { getBreadcrumbs, getSurfaceLabelKey } from "../../lib/navigationConfig";
import { loginPathForSurface } from "../../lib/authSurface";
import { LanguageSwitcher } from "./LanguageSwitcher";
import { StatusBadge } from "./StatusBadge";
import { useAuth } from "../../lib/auth";
import { useT } from "../../lib/i18n";

const OPS_ADMIN_ROLES = new Set(["owner", "admin"]);

function roleMayOpenOps(roles: string[] | undefined): boolean {
  return (roles ?? []).some((role) => OPS_ADMIN_ROLES.has(role));
}

function accountInitial(label: string): string {
  const trimmed = label.trim();
  if (!trimmed) return "?";
  const letter = trimmed[0];
  return letter ? letter.toUpperCase() : "?";
}

function shortAccountTriggerLabel(label: string): string {
  const trimmed = label.trim();
  if (trimmed.length <= 16) return trimmed;
  return `${trimmed.slice(0, 13)}...`;
}

function MenuCaretIcon() {
  return (
    <span aria-hidden="true" className="app-topbar-menu-caret">
      <svg fill="none" viewBox="0 0 12 12" xmlns="http://www.w3.org/2000/svg">
        <path d="M2.5 4.25 6 7.75l3.5-3.5" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.4" />
      </svg>
    </span>
  );
}

function WorkspaceSwitchIcon() {
  return (
    <span aria-hidden="true" className="app-topbar-menu-icon">
      <svg fill="none" viewBox="0 0 16 16" xmlns="http://www.w3.org/2000/svg">
        <path
          d="M3 5.5h8.2M9.2 3.2 11.8 5.5 9.2 7.8M13 10.5H4.8M6.8 8.2 4.2 10.5 6.8 12.8"
          stroke="currentColor"
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth="1.5"
        />
      </svg>
    </span>
  );
}

export function Topbar({
  surface,
  title,
  description,
  actions
}: {
  surface: NavSurface;
  title: string;
  description?: string;
  actions?: ReactNode;
}) {
  const t = useT();
  const { logout, me } = useAuth();
  const pathname = usePathname() || "/";
  const breadcrumbs = getBreadcrumbs(pathname);
  const canOpenOps = roleMayOpenOps(me?.roles);
  const showWorkspaceSwitch = surface === "ops" || canOpenOps;
  const switchLabel = surface === "operator" ? t("topbar.switchToOpsConsole") : t("topbar.switchToOperatorStudio");
  // Fail-closed: switching surfaces goes through the destination login portal.
  const switchHref = surface === "operator" ? loginPathForSurface("ops") : loginPathForSurface("operator");
  const hasPageActions = Boolean(actions);
  const accountLabel = me?.email || me?.displayName || t("topbar.account");
  const accountMenuRef = useRef<HTMLDetailsElement>(null);

  useEffect(() => {
    function onPointerDown(event: PointerEvent) {
      const menu = accountMenuRef.current;
      if (!menu || !(event.target instanceof Node) || menu.contains(event.target)) return;
      menu.removeAttribute("open");
    }
    document.addEventListener("pointerdown", onPointerDown);
    return () => document.removeEventListener("pointerdown", onPointerDown);
  }, []);

  return (
    <header className="app-topbar">
      <div className="app-topbar-context">
        <nav className="app-breadcrumbs" aria-label={t("nav.breadcrumbs")}>
          {breadcrumbs.map((crumb, index) => (
            <span key={`${crumb.label}-${index}`}>
              {crumb.href && index < breadcrumbs.length - 1 ? <a href={crumb.href}>{t(crumb.label)}</a> : <span>{t(crumb.label)}</span>}
            </span>
          ))}
        </nav>
        <h1>{title}</h1>
        <div className="app-topbar-meta">
          <span className="eyebrow">{t(getSurfaceLabelKey(surface))}</span>
          <StatusBadge label={t("common.localWorkspace")} tone="muted" />
          {description ? <p>{description}</p> : null}
        </div>
      </div>
      <div className="app-topbar-command-bar" aria-label={t("quickActions")}>
        {hasPageActions ? <div className="app-topbar-page-actions">{actions}</div> : null}
        <div className="app-topbar-command-cluster">
          <details className="app-topbar-menu app-topbar-account-menu" ref={accountMenuRef}>
            <summary aria-label={t("topbar.account")} title={accountLabel}>
              <span aria-hidden="true" className="app-topbar-account-avatar app-topbar-btn__icon-wrap">
                {accountInitial(accountLabel)}
              </span>
              <span className="app-topbar-btn__label app-topbar-account-trigger-label">{shortAccountTriggerLabel(accountLabel)}</span>
              <MenuCaretIcon />
            </summary>
            <div className="app-topbar-menu-panel app-topbar-account-panel" role="menu">
              <div className="app-topbar-account-header">
                <p className="app-topbar-account-summary" title={accountLabel}>
                  {accountLabel}
                </p>
                <p className="app-topbar-account-surface">{t(getSurfaceLabelKey(surface))}</p>
              </div>
              {showWorkspaceSwitch ? (
                <>
                  <a className="app-topbar-menu-link" href={switchHref} role="menuitem">
                    <WorkspaceSwitchIcon />
                    <span>{switchLabel}</span>
                  </a>
                  <div className="app-topbar-menu-separator" role="separator" />
                </>
              ) : null}
              <div className="app-topbar-account-language" role="none">
                <p className="app-topbar-menu-heading">{t("topbar.preferences")}</p>
                <LanguageSwitcher />
              </div>
              <div className="app-topbar-menu-separator" role="separator" />
              <button className="app-topbar-menu-button app-topbar-menu-logout" onClick={logout} role="menuitem" type="button">
                {t("topbar.logout")}
              </button>
            </div>
          </details>
        </div>
      </div>
    </header>
  );
}
