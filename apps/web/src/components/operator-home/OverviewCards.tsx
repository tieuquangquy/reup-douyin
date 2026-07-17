"use client";

import { StatusBadge } from "../app-shell/StatusBadge";
import { useT } from "../../lib/i18n";
import type { OperatorMetric } from "../../lib/operatorHomeState";

export function OverviewCards({ metrics }: { metrics: OperatorMetric[] }) {
  const t = useT();

  return (
    <section className="operator-overview-grid" aria-label="Operator overview metrics">
      {metrics.map((metric) => {
        const badgeLabel = metric.tone === "good" ? t("common.ok") : metric.tone === "danger" ? t("common.check") : t("common.watch");
        const content = (
          <>
            <div>
              <span>{metric.label}</span>
              <strong>{metric.value}</strong>
            </div>
            <p>{metric.detail}</p>
            <StatusBadge label={badgeLabel} tone={metric.tone} />
          </>
        );

        return metric.href ? (
          <a className="operator-metric-card" href={metric.href} key={metric.key}>
            {content}
          </a>
        ) : (
          <div className="operator-metric-card" key={metric.key}>
            {content}
          </div>
        );
      })}
    </section>
  );
}
