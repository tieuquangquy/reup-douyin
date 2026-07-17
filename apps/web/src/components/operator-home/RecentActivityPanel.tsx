"use client";

import { StatusBadge } from "../app-shell/StatusBadge";
import { formatToken } from "../../lib/operatorHomeState";
import { useT } from "../../lib/i18n";
import type { RecentActivityItem } from "../../lib/operatorHomeState";

export function RecentActivityPanel({ items }: { items: RecentActivityItem[] }) {
  const t = useT();

  return (
    <section className="operator-panel">
      <div className="operator-panel-heading">
        <div>
          <h2>{t("operatorHome.recentActivityHeading")}</h2>
          <p>{t("operatorHome.recentActivityDesc")}</p>
        </div>
      </div>

      {items.length === 0 ? (
        <div className="operator-empty-state">
          <h3>{t("common.noRecentActivity")}</h3>
          <p>{t("operatorHome.noRecentActivityBody")}</p>
        </div>
      ) : (
        <ol className="operator-activity-list">
          {items.map((item) => (
            <li key={item.key}>
              <a href={item.href}>
                <span>
                  <strong>{item.title}</strong>
                  <small>{item.detail}</small>
                  <small>{item.at ? new Date(item.at).toLocaleString() : t("common.unknown")}</small>
                </span>
                <StatusBadge label={formatToken(item.tone)} tone={item.tone} />
              </a>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}
