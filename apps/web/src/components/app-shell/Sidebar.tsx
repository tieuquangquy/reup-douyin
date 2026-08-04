"use client";

import { useEffect, useRef, useState } from "react";
import { usePathname } from "next/navigation";
import type { NavSection as NavSectionConfig, NavSurface } from "../../lib/navigationConfig";
import { extractSourceVideoIdFromPath } from "../../lib/navigationConfig";
import { NavSection } from "./NavSection";
import { useT } from "../../lib/i18n";

const CURRENT_SOURCE_VIDEO_KEY = "reup-douyin-current-source-video-id";

export function Sidebar({ surface, sections }: { surface: NavSurface; sections: NavSectionConfig[] }) {
  const pathname = usePathname() || "/";
  const t = useT();
  const sidebarRef = useRef<HTMLElement>(null);
  const [currentSourceVideoId, setCurrentSourceVideoId] = useState<string | null>(null);

  useEffect(() => {
    const sourceVideoId = extractSourceVideoIdFromPath(pathname);
    if (sourceVideoId) {
      localStorage.setItem(CURRENT_SOURCE_VIDEO_KEY, sourceVideoId);
      setCurrentSourceVideoId(sourceVideoId);
      return;
    }
    setCurrentSourceVideoId(localStorage.getItem(CURRENT_SOURCE_VIDEO_KEY));
  }, [pathname]);

  useEffect(() => {
    const frameId = window.requestAnimationFrame(() => {
      const activeItem = sidebarRef.current?.querySelector<HTMLElement>('[aria-current="page"]');
      activeItem?.scrollIntoView({ behavior: "auto", block: "center", inline: "nearest" });
    });

    return () => window.cancelAnimationFrame(frameId);
  }, [pathname]);

  return (
    <aside className={`app-sidebar is-${surface}`} ref={sidebarRef}>
      <a className="app-brand" href={surface === "operator" ? "/" : "/ops"}>
        <span className="app-brand__mark">
          <img alt="" height={28} src="/brand/logo-loop-r.svg" width={28} />
        </span>
        <span className="app-brand__text">
          <span>reup-douyin</span>
          <strong>{surface === "operator" ? t("nav.operatorStudio") : t("nav.opsConsole")}</strong>
        </span>
      </a>
      <nav aria-label={`${surface === "operator" ? t("nav.operatorStudio") : t("nav.opsConsole")} navigation`}>
        {sections.map((section) => (
          <NavSection activePath={pathname} currentSourceVideoId={currentSourceVideoId} key={section.title} section={section} />
        ))}
      </nav>
      <footer className="app-sidebar__footer">
        <span aria-hidden="true" className="app-sidebar__status-dot" />
        <span>
          <strong>{t("common.localWorkspace")}</strong>
          <small>{surface === "operator" ? t("nav.operatorStudio") : t("nav.opsConsole")}</small>
        </span>
      </footer>
    </aside>
  );
}
