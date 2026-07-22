"use client";

import type { ReactNode } from "react";
import type { NavSection as NavSectionConfig, NavSurface } from "../../lib/navigationConfig";
import { BackToTopButton } from "./BackToTopButton";
import { NoticeViewport } from "../shared/NoticeCenter";
import { Sidebar } from "./Sidebar";
import { Topbar } from "./Topbar";

export function AppShell({
  surface,
  sections,
  title,
  description,
  actions,
  children
}: {
  surface: NavSurface;
  sections: NavSectionConfig[];
  title: string;
  description?: string;
  actions?: ReactNode;
  children: ReactNode;
}) {
  return (
    <div className={`app-shell app-shell--${surface}`}>
      <Sidebar sections={sections} surface={surface} />
      <main className="app-main">
        <Topbar actions={actions} description={description} surface={surface} title={title} />
        <div className="app-content">{children}</div>
      </main>
      <BackToTopButton />
      <NoticeViewport />
    </div>
  );
}
