"use client";

import { useT } from "../../lib/i18n";
import type { OperatorFreshness, OperatorExtensionSignal, OperatorMetric } from "../../lib/operatorHomeState";
import { toneForPipelineStatus } from "../../lib/operatorHomeState";
import { OperatorHomeChip } from "./OperatorHomeShared";

function formatFreshnessTime(value: string | null): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  const time = date.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit", hour12: false });
  return `${time} · ${date.getDate()}/${date.getMonth() + 1}`;
}

function pipelineStatusLabel(status: OperatorFreshness["overallStatus"], t: (key: string) => string): string {
  if (status === "healthy") return t("opsPipeline.statusHealthy");
  if (status === "needs_attention") return t("opsPipeline.statusNeedsAttention");
  if (status === "blocked") return t("opsPipeline.statusBlocked");
  if (status === "quiet") return t("opsPipeline.statusQuiet");
  if (status === "in_progress") return t("opsPipeline.statusInProgress");
  return t("operatorHome.pipelineUnknown");
}

export function FreshnessStrip({
  freshness,
  extension,
  publishSuccess
}: {
  freshness: OperatorFreshness;
  extension: OperatorExtensionSignal;
  publishSuccess: OperatorMetric;
}) {
  const t = useT();
  const statusTone = toneForPipelineStatus(freshness.overallStatus);

  return (
    <section className="operator-home-freshness" aria-label={t("operatorHome.freshness")}>
      <OperatorHomeChip label={pipelineStatusLabel(freshness.overallStatus, t)} tone={statusTone} />
      <span className="operator-home-freshness__headline" title={freshness.headline ?? undefined}>
        {freshness.headline ?? t("operatorHome.pipelineQuietHeadline")}
      </span>
      <div className="operator-home-freshness__inline">
        <span className="operator-home-freshness__meta">
          {t("operatorHome.loadedAt")}{" "}
          <time dateTime={freshness.generatedAt ?? undefined}>{formatFreshnessTime(freshness.generatedAt)}</time>
        </span>
        <span className="operator-home-freshness__sep" aria-hidden="true">
          ·
        </span>
        {publishSuccess.href ? (
          <a
            className={`operator-home-freshness__link tone-${publishSuccess.tone}`}
            href={publishSuccess.href}
            title={publishSuccess.detail}
          >
            {t("operatorHome.publishSuccessShort")} <strong>{publishSuccess.value}</strong>
          </a>
        ) : (
          <span className={`operator-home-freshness__link tone-${publishSuccess.tone}`} title={publishSuccess.detail}>
            {t("operatorHome.publishSuccessShort")} <strong>{publishSuccess.value}</strong>
          </span>
        )}
        <a
          className={`operator-home-freshness__action tone-${extension.tone}`}
          href={extension.href}
          title={extension.detail}
        >
          {extension.label}
        </a>
        <a className="operator-home-freshness__action is-primary" href={freshness.pipelineHref}>
          {t("operatorHome.openPipeline")}
        </a>
      </div>
    </section>
  );
}
