"use client";

import { StatusBadge } from "../app-shell/StatusBadge";
import { useT } from "../../lib/i18n";
import type { ContinueItem } from "../../lib/operatorHomeState";

export function ContinuePanel({ items }: { items: ContinueItem[] }) {
  const t = useT();

  return (
    <section className="operator-panel">
      <div className="operator-panel-heading">
        <div>
          <h2>{t("operatorHome.continuePanelHeading")}</h2>
          <p>{t("operatorHome.continuePanelDesc")}</p>
        </div>
      </div>

      {items.length === 0 ? (
        <div className="operator-empty-state">
          <h3>{t("common.noActiveContext")}</h3>
          <p>{t("operatorHome.noActiveContextBody")}</p>
        </div>
      ) : (
        <div className="operator-action-list">
          {items.map((item) => (
            <a className="operator-action-row compact" href={item.href} key={item.key}>
              <span className="operator-action-count">{t("common.go")}</span>
              <span>
                <strong>{item.title}</strong>
                <small>{item.description}</small>
              </span>
              <StatusBadge label={t("common.continue")} tone={item.tone} />
            </a>
          ))}
        </div>
      )}
    </section>
  );
}
