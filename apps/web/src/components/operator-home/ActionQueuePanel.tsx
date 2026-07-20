"use client";

import { useT } from "../../lib/i18n";
import type { OperatorActionItem } from "../../lib/operatorHomeState";
import { OperatorHomeChip, OperatorHomeOpenLink, OperatorHomePanel } from "./OperatorHomeShared";

export function ActionQueuePanel({ items }: { items: OperatorActionItem[] }) {
  const t = useT();
  const next = items.find((item) => item.count > 0);

  return (
    <OperatorHomePanel
      title={t("operatorHome.actionQueueHeading")}
      description={t("operatorHome.actionQueueDesc")}
      action={
        next ? (
          <a className="operator-home-panel__link" href={next.href}>
            {t("operatorHome.nextAction")} {next.cta}
          </a>
        ) : null
      }
    >
      <ul className="operator-home-actions">
        {items.map((item) => (
          <li className="operator-home-row operator-home-actions__item" key={item.key}>
            <b className="operator-home-num">{item.count}</b>
            <div className="operator-home-row__body">
              <strong>{item.title}</strong>
              <span title={item.description}>{item.description}</span>
              {item.count > 0 ? <em className="operator-home-row__cta">{item.cta}</em> : null}
            </div>
            <OperatorHomeChip
              label={item.count > 0 ? t("common.needsWork") : t("common.clear")}
              tone={item.count > 0 ? item.tone : "muted"}
            />
            <OperatorHomeOpenLink href={item.href} label={item.cta} />
          </li>
        ))}
      </ul>
    </OperatorHomePanel>
  );
}
