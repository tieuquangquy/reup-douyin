"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { fetchPublishHandoff } from "../../lib/api";
import { buildHandoffCargo, type HandoffCargoRow } from "../../lib/handoffCargo";
import { mergeLifecycleByMinute } from "../../lib/handoffLifecycle";
import { useLocale, useT } from "../../lib/i18n";
import { humanizeStatus } from "../../lib/statusLabels";
import { useLatestRequest, type LatestRequestMode } from "../../lib/useLatestRequest";
import type { PublishHandoff } from "../../types/export-handoff";
import { OperatorStudioShell } from "../app-shell/OperatorStudioShell";
import { TopbarRefreshButton } from "../app-shell/TopbarRefreshButton";
import { AsyncContentBoundary } from "../shared/AsyncContentBoundary";
import { OpsDetailPanel, OpsDetailSection, OpsStatePanel, statusTone } from "../ops-console/OpsShared";

export function PublishHandoffByIdPage({ handoffId }: { handoffId: string }) {
  const t = useT();
  const locale = useLocale();
  const [handoff, setHandoff] = useState<PublishHandoff | null>(null);
  const [copiedKey, setCopiedKey] = useState<string | null>(null);
  const request = useLatestRequest();
  const cargo = useMemo(
    () => buildHandoffCargo(handoff?.payload_json ?? null).flatMap((group) => group.rows),
    [handoff]
  );
  const lifecycle = useMemo(
    () =>
      handoff
        ? mergeLifecycleByMinute(visibleLifecycleSteps(handoff, t), (iso) => formatDateTime(iso, locale, t))
        : [],
    [handoff, locale, t]
  );

  async function load(mode: LatestRequestMode = handoff ? "refresh" : "initial") {
    if (mode === "initial") setHandoff(null);
    await request.run(async () => fetchPublishHandoff(handoffId), setHandoff, mode).catch(() => undefined);
  }

  useEffect(() => {
    void load("initial");
  }, [handoffId]);

  async function copyValue(key: string, value: string) {
    if (typeof navigator === "undefined" || !navigator.clipboard) return;
    await navigator.clipboard.writeText(value).catch(() => undefined);
    setCopiedKey(key);
    window.setTimeout(() => setCopiedKey((current) => (current === key ? null : current)), 1200);
  }

  const boundaryStatus =
    request.initialLoading && !handoff ? "loading" : request.error && !handoff ? "error" : handoff ? "success" : "empty";
  const stage = handoff ? handoffStageClass(handoff.status) : "is-draft";
  const loggedSteps = lifecycle.filter((step) => Boolean(step.at)).length;

  return (
    <OperatorStudioShell
      actions={
        <TopbarRefreshButton
          busy={request.refreshing}
          disabled={request.initialLoading}
          onClick={() => void load("refresh")}
        />
      }
      description={t("opsPublishHandoffs.description")}
      title={t("opsPublishHandoffs.detailTitle")}
    >
      <AsyncContentBoundary
        refreshing={request.refreshing}
        status={boundaryStatus}
        skeletonVariant="detail"
        loadingLabel={t("opsPublishHandoffs.loadingDetailPage")}
        errorState={
          <OpsStatePanel
            action={
              <button type="button" onClick={() => void load("initial")}>
                {t("opsPublishHandoffs.retry")}
              </button>
            }
            detail={request.error?.message ?? t("opsPublishHandoffs.notFound")}
            title={t("opsPublishHandoffs.unavailableDetail")}
            variant="error"
          />
        }
      >
        {handoff ? (
          <div className="publish-handoff-dossier is-open">
            <article className={`publish-handoff-dossier__stamp tone-${statusTone(handoff.status)} ${stage}`}>
              <nav aria-label={t("opsPublishHandoffs.related")} className="publish-handoff-dossier__rail">
                <Link className="publish-handoff-dossier__link" href="/publishing/publish-handoffs">
                  <HandoffDetailIcon kind="handoffs" />
                  <span>{t("opsPublishHandoffs.allHandoffs")}</span>
                </Link>
                <Link
                  className="publish-handoff-dossier__link"
                  href={`/publishing/export-packages/${handoff.export_package_id}`}
                >
                  <HandoffDetailIcon kind="packages" />
                  <span>{t("opsPublishHandoffs.openPackage")}</span>
                </Link>
                <Link className="publish-handoff-dossier__link" href="/selection/reup-queue">
                  <HandoffDetailIcon kind="queue" />
                  <span>{t("opsPublishHandoffs.openReupQueue")}</span>
                </Link>
              </nav>

              <div className="publish-handoff-dossier__mix">
                <div
                  aria-hidden="true"
                  className="publish-handoff-dossier__ring"
                  style={{ background: lifecycleRingFill(lifecycle, stage) }}
                >
                  <span className="publish-handoff-dossier__ring-core">
                    <b>{loggedSteps}</b>
                    <small>{t("opsPublishHandoffs.lifecycle")}</small>
                  </span>
                </div>

                <header className="publish-handoff-dossier__stub">
                  <div>
                    <em>{t("opsPublishHandoffs.to")}</em>
                    <h2 title={handoff.target_platform}>{handoff.target_platform.replace(/_/g, " ")}</h2>
                    <span className="publish-handoff-dossier__stamp-chip">{humanizeStatus(handoff.status)}</span>
                  </div>
                  <p className="publish-handoff-dossier__stub-meta">
                    <em>{t("opsPublishHandoffs.from")}</em>
                    <Link href={`/publishing/export-packages/${handoff.export_package_id}`} title={handoff.export_package_id}>
                      {handoff.export_package_id.slice(0, 8)}
                    </Link>
                    <button
                      type="button"
                      onClick={() => void copyValue("handoff", handoff.id)}
                      title={handoff.id}
                      aria-label={`${t("opsPublishHandoffs.handoff")} ${handoff.id.slice(0, 8)}`}
                    >
                      <HandoffDetailIcon kind="copy" />
                      {handoff.id.slice(0, 8)}
                    </button>
                    <time dateTime={handoff.ready_at ?? handoff.created_at}>
                      {formatDateTime(handoff.ready_at ?? handoff.created_at, locale, t)}
                    </time>
                    <em>{t("opsPublishHandoffs.publishAutomationValue")}</em>
                  </p>
                  <p className="publish-handoff-dossier__stamp-note">
                    {/* Handoffs do not call platform APIs or auto-publish. */}
                    {t("opsPublishHandoffs.noPlatformApi")}
                  </p>
                </header>

                <ol className="publish-handoff-dossier__timeline" aria-label={t("opsPublishHandoffs.lifecycle")}>
                  {lifecycle.map((step) => (
                    <li className={`is-${step.tone}`} key={step.key}>
                      <i aria-hidden="true" />
                      <strong>{step.label}</strong>
                      {step.at ? (
                        <time dateTime={step.at}>{formatDateTime(step.at, locale, t)}</time>
                      ) : (
                        <span>{t("opsPublishHandoffs.notRecorded")}</span>
                      )}
                    </li>
                  ))}
                </ol>
              </div>

              <div className="publish-handoff-dossier__body">
                {handoff.operator_note ? <p className="publish-handoff-dossier__note">{handoff.operator_note}</p> : null}

                <section className="publish-handoff-dossier__cargo" aria-label={t("opsPublishHandoffs.cargo")}>
                  {cargo.length > 0 ? (
                    <ul>
                      {cargo.map((row) => (
                        <CargoCopyRow
                          copied={copiedKey === row.key}
                          copiedLabel={t("opsPublishHandoffs.copied")}
                          copyLabel={t("opsPublishHandoffs.copy")}
                          key={row.key}
                          onCopy={() => void copyValue(row.key, row.value)}
                          row={row}
                        />
                      ))}
                    </ul>
                  ) : (
                    <p className="publish-handoff-dossier__cargo-empty">{t("opsPublishHandoffs.cargoEmpty")}</p>
                  )}
                </section>
              </div>

            <OpsDetailPanel title={t("opsPublishHandoffs.inspect")}>
              <OpsDetailSection collapsed title={t("opsPublishHandoffs.payload")}>
                <p className="muted">{t("opsPublishHandoffs.payloadDesc")}</p>
                <pre className="publish-handoff-dossier__code">{JSON.stringify(handoff.payload_json ?? {}, null, 2)}</pre>
              </OpsDetailSection>
              <OpsDetailSection collapsed title={t("opsPublishHandoffs.diagnostics")}>
                <pre className="publish-handoff-dossier__code">
                  {JSON.stringify(handoff.diagnostics_json ?? {}, null, 2)}
                </pre>
              </OpsDetailSection>
            </OpsDetailPanel>
            </article>
          </div>
        ) : null}
      </AsyncContentBoundary>
    </OperatorStudioShell>
  );
}

function CargoCopyRow({
  copied,
  copiedLabel,
  copyLabel,
  onCopy,
  row
}: {
  copied: boolean;
  copiedLabel: string;
  copyLabel: string;
  onCopy: () => void;
  row: HandoffCargoRow;
}) {
  return (
    <li className="publish-handoff-dossier__row">
      <span>{row.label}</span>
      <p>
        <code title={row.value}>{row.value}</code>
        <button type="button" onClick={onCopy} aria-label={copied ? copiedLabel : copyLabel}>
          <HandoffDetailIcon kind={copied ? "copied" : "copy"} />
        </button>
      </p>
    </li>
  );
}

function lifecycleSteps(handoff: PublishHandoff, t: (key: string) => string) {
  return [
    { key: "created", label: t("opsPublishHandoffs.createdAt"), at: handoff.created_at, tone: "done" as const },
    {
      key: "ready",
      label: t("opsPublishHandoffs.readyAt"),
      at: handoff.ready_at,
      tone: handoff.ready_at ? ("done" as const) : ("pending" as const)
    },
    {
      key: "accepted",
      label: t("opsPublishHandoffs.acceptedAt"),
      at: handoff.accepted_at,
      tone: handoff.accepted_at ? ("done" as const) : ("pending" as const)
    },
    {
      key: "failed",
      label: t("opsPublishHandoffs.failedAt"),
      at: handoff.failed_at,
      tone: handoff.failed_at ? ("attention" as const) : ("pending" as const)
    },
    {
      key: "cancelled",
      label: t("opsPublishHandoffs.cancelledAt"),
      at: handoff.cancelled_at,
      tone: handoff.cancelled_at ? ("muted" as const) : ("pending" as const)
    }
  ];
}

function visibleLifecycleSteps(handoff: PublishHandoff, t: (key: string) => string) {
  return lifecycleSteps(handoff, t).filter((step) => {
    if (step.at) return true;
    if (handoff.failed_at || handoff.cancelled_at) return false;
    if (step.key === "ready" && !handoff.ready_at) return true;
    if (step.key === "accepted" && Boolean(handoff.ready_at) && !handoff.accepted_at) return true;
    return false;
  });
}

function HandoffDetailIcon({ kind }: { kind: "handoffs" | "packages" | "queue" | "copy" | "copied" }) {
  const className =
    kind === "copy" || kind === "copied" ? "publish-handoff-dossier__copy-icon" : "publish-handoff-dossier__link-icon";
  if (kind === "copied") {
    return (
      <svg aria-hidden="true" className={className} fill="none" viewBox="0 0 20 20">
        <path d="m5.2 10.4 3.1 3.1 6.5-7.2" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.7" />
      </svg>
    );
  }
  if (kind === "copy") {
    return (
      <svg aria-hidden="true" className={className} fill="none" viewBox="0 0 20 20">
        <rect height="11" rx="1.4" stroke="currentColor" strokeWidth="1.55" width="9" x="6.6" y="6.2" />
        <path d="M13.4 6.2V5.1A1.4 1.4 0 0 0 12 3.7H5.4A1.4 1.4 0 0 0 4 5.1v8.8A1.4 1.4 0 0 0 5.4 15.3H6.6" stroke="currentColor" strokeWidth="1.55" />
      </svg>
    );
  }
  if (kind === "queue") {
    return (
      <svg aria-hidden="true" className={className} fill="none" viewBox="0 0 20 20">
        <path d="M4.5 6.2h11M4.5 10h11M4.5 13.8h7.2" stroke="currentColor" strokeLinecap="round" strokeWidth="1.55" />
      </svg>
    );
  }
  if (kind === "packages") {
    return (
      <svg aria-hidden="true" className={className} fill="none" viewBox="0 0 20 20">
        <path
          d="M5.2 5.2h9.6a1.4 1.4 0 0 1 1.4 1.4v7.8a1.4 1.4 0 0 1-1.4 1.4H5.2a1.4 1.4 0 0 1-1.4-1.4V6.6a1.4 1.4 0 0 1 1.4-1.4Z"
          stroke="currentColor"
          strokeWidth="1.55"
        />
        <path d="M7.1 8.4h5.8M7.1 11h3.8" stroke="currentColor" strokeLinecap="round" strokeWidth="1.55" />
      </svg>
    );
  }
  return (
    <svg aria-hidden="true" className={className} fill="none" viewBox="0 0 20 20">
      <path d="M4.4 10h11.2M4.4 10l3.4-3.4M4.4 10l3.4 3.4" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.55" />
    </svg>
  );
}

function handoffStageClass(status: string) {
  if (status === "READY_FOR_OPERATOR") return "is-ready";
  if (status === "ACCEPTED") return "is-accepted";
  if (status === "FAILED_NEEDS_ATTENTION") return "is-attention";
  if (status === "CANCELLED") return "is-cancelled";
  return "is-draft";
}

function lifecycleRingFill(steps: Array<{ at: string | null }>, stage: string) {
  const done = steps.filter((step) => Boolean(step.at)).length;
  const total = Math.max(steps.length, 1);
  const deg = Math.round((done / total) * 360);
  const fill =
    stage === "is-attention" ? "#c4841a" : stage === "is-accepted" ? "#4f6fbf" : stage === "is-ready" ? "#2f8f6f" : "#8aa39a";
  const track = "#d5e0db";
  if (deg >= 360) return fill;
  if (deg <= 0) return track;
  return `conic-gradient(${fill} 0deg ${deg}deg, ${track} ${deg}deg 360deg)`;
}

function formatDateTime(value: string | null, locale: "en" | "vi", t: (key: string) => string): string {
  if (!value) return t("opsPublishHandoffs.notRecorded");
  return new Intl.DateTimeFormat(locale === "vi" ? "vi-VN" : "en-US", {
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit"
  }).format(new Date(value));
}

