"use client";

import type { ReactNode } from "react";
import { opsNavSections } from "../../lib/navigationConfig";
import { AppShell } from "./AppShell";

export function OpsConsoleShell({
  title,
  description,
  actions,
  children
}: {
  title: string;
  description?: string;
  actions?: ReactNode;
  children: ReactNode;
}) {
  return (
    <AppShell actions={actions} description={description} sections={opsNavSections} surface="ops" title={title}>
      {children}
    </AppShell>
  );
}
