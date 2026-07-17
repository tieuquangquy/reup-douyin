"use client";

import { StatusBadge } from "../app-shell/StatusBadge";
import { useT } from "../../lib/i18n";
import type { QuickLaunchItem } from "../../lib/operatorHomeState";

export function QuickLaunchGrid({ items }: { items: QuickLaunchItem[] }) {
  const t = useT();

  return (
    <section className="operator-panel">
      <div className="operator-panel-heading">
        <div>
          <h2>{t("operatorHome.quickLaunchHeading")}</h2>
          <p>{t("operatorHome.quickLaunchDesc")}</p>
        </div>
      </div>

      <div className="operator-quick-grid">
        {items.map((item) => (
          <a className={`operator-quick-card${item.enabled ? "" : " disabled"}`} href={item.href} key={item.key}>
            <span>
              <strong>{item.title}</strong>
              <small>{item.description}</small>
            </span>
            <StatusBadge label={item.enabled ? t("common.ready") : t("common.needsContext")} tone={item.enabled ? item.tone : "muted"} />
          </a>
        ))}
      </div>
    </section>
  );
}
