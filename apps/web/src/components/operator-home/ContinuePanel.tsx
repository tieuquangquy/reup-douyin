"use client";

import { useT } from "../../lib/i18n";
import type { ContinueItem } from "../../lib/operatorHomeState";
import { OperatorHomeChip, OperatorHomeOpenLink, OperatorHomePanel } from "./OperatorHomeShared";

export function ContinuePanel({ items }: { items: ContinueItem[] }) {
  const t = useT();

  return (
    <OperatorHomePanel title={t("operatorHome.continuePanelHeading")} description={t("operatorHome.continuePanelDesc")}>
      {items.length === 0 ? (
        <div className="operator-home-empty">
          <strong>{t("common.noActiveContext")}</strong>
          <span>{t("operatorHome.noActiveContextBody")}</span>
        </div>
      ) : (
        <ul className="operator-home-continue">
          {items.map((item) => (
            <li className="operator-home-row operator-home-continue__item" key={item.key}>
              <OperatorHomeChip label={t("common.go")} tone={item.tone} />
              <div className="operator-home-row__body">
                <strong>{item.title}</strong>
                <span title={item.description}>{item.description}</span>
              </div>
              <OperatorHomeOpenLink href={item.href} label={t("common.continue")} />
            </li>
          ))}
        </ul>
      )}
    </OperatorHomePanel>
  );
}
