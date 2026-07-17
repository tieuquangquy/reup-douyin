"use client";

import { useT } from "../../lib/i18n";
import { OperatorStudioShell } from "../app-shell/OperatorStudioShell";
import { PageShell } from "../app-shell/PageShell";
import { StatusBadge } from "../app-shell/StatusBadge";

type PlaceholderAction = {
  label: string;
  href: string;
  description: string;
};

export function OperatorPlaceholderPage({
  title,
  description,
  statusLabel = "Planned",
  actions
}: {
  title: string;
  description: string;
  statusLabel?: string;
  actions: PlaceholderAction[];
}) {
  const t = useT();
  return (
    <OperatorStudioShell description={description} title={title}>
      <PageShell
        description={t("operatorRoutes.placeholderDesc")}
        title={title}
      >
        <div className="studio-card-list">
          {actions.map((action) => (
            <a className="studio-card" href={action.href} key={action.href}>
              <span>
                <strong>{action.label}</strong>
                <small>{action.description}</small>
              </span>
              <StatusBadge label={statusLabel} tone="muted" />
            </a>
          ))}
        </div>
      </PageShell>
    </OperatorStudioShell>
  );
}
