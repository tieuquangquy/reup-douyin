"use client";

import { useT } from "../../lib/i18n";
import type { OperatorNextWorkItem } from "../../lib/operatorHomeState";
import { OperatorHomeChip, OperatorHomeOpenLink, OperatorHomePanel } from "./OperatorHomeShared";

function severityLabel(severity: OperatorNextWorkItem["severity"], t: (key: string) => string): string {
  if (severity === "critical") return t("opsPipeline.severityCritical");
  if (severity === "warning") return t("opsPipeline.severityWarning");
  return t("opsPipeline.severityInfo");
}

export function NextWorkPanel({ items }: { items: OperatorNextWorkItem[] }) {
  const t = useT();

  if (items.length === 0) return null;

  return (
    <OperatorHomePanel title={t("operatorHome.nextWork")} description={t("operatorHome.nextWorkDesc")}>
      <ul className="operator-home-next">
        {items.map((item) => (
          <li className="operator-home-row operator-home-next__item" key={item.key}>
            <OperatorHomeChip label={severityLabel(item.severity, t)} tone={item.tone} />
            <div className="operator-home-row__body">
              <strong>{item.title}</strong>
              <span title={item.detail}>{item.detail}</span>
              <em className="operator-home-row__cta">{item.cta}</em>
            </div>
            <b className="operator-home-num">{item.count}</b>
            <OperatorHomeOpenLink href={item.href} label={item.cta} />
          </li>
        ))}
      </ul>
    </OperatorHomePanel>
  );
}
