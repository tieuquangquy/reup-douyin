"use client";

import { OperatorStudioShell } from "../app-shell/OperatorStudioShell";
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
  return (
    <OperatorStudioShell description={description} title={title}>
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
    </OperatorStudioShell>
  );
}
