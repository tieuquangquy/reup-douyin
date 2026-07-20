"use client";

import type { OperatorMetric } from "../../lib/operatorHomeState";

export function OverviewCards({ metrics }: { metrics: OperatorMetric[] }) {
  return (
    <section className="operator-home-kpis" aria-label="Operator overview metrics">
      {metrics.map((metric) => {
        const content = (
          <>
            <em>{metric.label}</em>
            <strong>{metric.value}</strong>
            <span title={metric.detail}>{metric.detail}</span>
          </>
        );

        return metric.href ? (
          <a className={`operator-home-kpi tone-${metric.tone}`} href={metric.href} key={metric.key} title={metric.detail}>
            {content}
          </a>
        ) : (
          <article className={`operator-home-kpi tone-${metric.tone}`} key={metric.key} title={metric.detail}>
            {content}
          </article>
        );
      })}
    </section>
  );
}
