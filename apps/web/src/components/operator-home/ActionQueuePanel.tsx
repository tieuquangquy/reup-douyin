"use client";

import { StatusBadge } from "../app-shell/StatusBadge";
import { useT } from "../../lib/i18n";
import type { OperatorActionItem } from "../../lib/operatorHomeState";

export function ActionQueuePanel({ items }: { items: OperatorActionItem[] }) {
  const t = useT();
  const next = items.find((item) => item.count > 0);

  return (
    <section className="operator-panel">
      <div className="operator-panel-heading">
        <div>
          <h2>{t("operatorHome.actionQueueHeading")}</h2>
          <p>{t("operatorHome.actionQueueDesc")}</p>
        </div>
        {next ? <a className="operator-inline-link" href={next.href}>{t("operatorHome.nextAction")} {next.cta}</a> : null}
      </div>

      <div className="operator-action-list">
        {items.map((item) => (
          <a className="operator-action-row" href={item.href} key={item.key}>
            <span className="operator-action-count">{item.count}</span>
            <span>
              <strong>{item.title}</strong>
              <small>{item.description}</small>
              <small className="operator-next-action">{item.cta}</small>
            </span>
            <StatusBadge label={item.count > 0 ? t("common.needsWork") : t("common.clear")} tone={item.tone} />
          </a>
        ))}
      </div>
    </section>
  );
}
