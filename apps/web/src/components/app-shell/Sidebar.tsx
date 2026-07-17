"use client";

import { useEffect, useState } from "react";
import { usePathname } from "next/navigation";
import type { NavSection as NavSectionConfig, NavSurface } from "../../lib/navigationConfig";
import { extractSourceVideoIdFromPath } from "../../lib/navigationConfig";
import { NavSection } from "./NavSection";
import { useT } from "../../lib/i18n";

const CURRENT_SOURCE_VIDEO_KEY = "reup-douyin-current-source-video-id";

export function Sidebar({ surface, sections }: { surface: NavSurface; sections: NavSectionConfig[] }) {
  const pathname = usePathname() || "/";
  const t = useT();
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

  return (
    <aside className="app-sidebar">
      <a className="app-brand" href={surface === "operator" ? "/" : "/ops"}>
        <span>reup-douyin</span>
        <strong>{surface === "operator" ? t("nav.operatorStudio") : t("nav.opsConsole")}</strong>
      </a>
      <nav aria-label={`${surface === "operator" ? t("nav.operatorStudio") : t("nav.opsConsole")} navigation`}>
        {sections.map((section) => (
          <NavSection activePath={pathname} currentSourceVideoId={currentSourceVideoId} key={section.title} section={section} />
        ))}
      </nav>
    </aside>
  );
}
