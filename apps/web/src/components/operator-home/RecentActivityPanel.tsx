"use client";

import { formatToken } from "../../lib/operatorHomeState";
import { useT } from "../../lib/i18n";
import type { RecentActivityItem } from "../../lib/operatorHomeState";
import {
  formatCompactActivityTime,
  OperatorHomeChip,
  OperatorHomeOpenLink,
  OperatorHomePanel,
} from "./OperatorHomeShared";

export function RecentActivityPanel({ items }: { items: RecentActivityItem[] }) {
  const t = useT();

  return (
    <OperatorHomePanel title={t("operatorHome.recentActivityHeading")} description={t("operatorHome.recentActivityDesc")}>
      {items.length === 0 ? (
        <div className="operator-home-empty">
          <strong>{t("common.noRecentActivity")}</strong>
          <span>{t("operatorHome.noRecentActivityBody")}</span>
        </div>
      ) : (
        <ol className="operator-home-activity">
          {items.map((item) => {
            const compactTime = item.at ? formatCompactActivityTime(item.at) : t("common.unknown");
            return (
              <li className="operator-home-row operator-home-activity__item" key={item.key}>
                <OperatorHomeChip label={formatToken(item.tone)} tone={item.tone} />
                <div className="operator-home-row__body">
                  <strong>{item.title}</strong>
                  <span title={item.detail}>{item.detail}</span>
                </div>
                <div className="operator-home-activity__trail">
                  {item.at ? (
                    <time dateTime={item.at} title={new Date(item.at).toLocaleString()}>
                      {compactTime}
                    </time>
                  ) : (
                    <time>{compactTime}</time>
                  )}
                  <OperatorHomeOpenLink href={item.href} label={t("opsPipeline.open")} />
                </div>
              </li>
            );
          })}
        </ol>
      )}
    </OperatorHomePanel>
  );
}
