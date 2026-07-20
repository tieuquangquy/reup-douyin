"use client";

import { useT } from "../../lib/i18n";
import type { QuickLaunchItem } from "../../lib/operatorHomeState";
import { OperatorHomePanel } from "./OperatorHomeShared";

export function QuickLaunchGrid({ items }: { items: QuickLaunchItem[] }) {
  const t = useT();

  return (
    <OperatorHomePanel title={t("operatorHome.quickLaunchHeading")} description={t("operatorHome.quickLaunchDesc")}>
      <nav className="operator-home-launch" aria-label={t("operatorHome.quickLaunchHeading")}>
        {items.map((item) => (
          <a
            className={`operator-home-launch__item${item.enabled ? "" : " is-disabled"} tone-${item.enabled ? item.tone : "muted"}`}
            href={item.href}
            key={item.key}
            title={item.description}
            aria-disabled={item.enabled ? undefined : true}
            onClick={item.enabled ? undefined : (event) => event.preventDefault()}
          >
            <strong>{item.title}</strong>
            <span>{item.enabled ? t("common.ready") : t("common.needsContext")}</span>
          </a>
        ))}
      </nav>
    </OperatorHomePanel>
  );
}
