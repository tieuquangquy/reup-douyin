"use client";

import type { ReactNode } from "react";
import { operatorNavSections } from "../../lib/navigationConfig";
import { AppShell } from "./AppShell";

export function OperatorStudioShell({
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
    <AppShell actions={actions} description={description} sections={operatorNavSections} surface="operator" title={title}>
      {children}
    </AppShell>
  );
}
