"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { createPublishHandoff, fetchExportPackage } from "../../lib/api";
import { mergeLifecycleByMinute } from "../../lib/handoffLifecycle";
import { useLocale, useT } from "../../lib/i18n";
import { humanizeStatus } from "../../lib/statusLabels";
import { useAsyncAction } from "../../lib/useAsyncAction";
import { useLatestRequest, type LatestRequestMode } from "../../lib/useLatestRequest";
import type { ExportPackage, ExportPackageItem, PublishHandoff } from "../../types/export-handoff";
import { OperatorStudioShell } from "../app-shell/OperatorStudioShell";
import { TopbarRefreshButton } from "../app-shell/TopbarRefreshButton";
import { AsyncButton } from "../shared/AsyncButton";
import { AsyncContentBoundary } from "../shared/AsyncContentBoundary";
import { useNotice } from "../shared/NoticeCenter";
import { OpsDetailPanel, OpsDetailSection, OpsStatePanel } from "../ops-console/OpsShared";

export function ExportPackageByIdPage({ packageId }: { packageId: string }) {
  const t = useT();
  const locale = useLocale();
  const [item, setItem] = useState<ExportPackage | null>(null);
  const [createdHandoff, setCreatedHandoff] = useState<PublishHandoff | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const action = useAsyncAction();
  const request = useLatestRequest();
  const { notify } = useNotice();

  async function load(mode: LatestRequestMode = item ? "refresh" : "initial") {
    if (mode === "initial") setItem(null);
    await request.run(async () => fetchExportPackage(packageId), setItem, mode).catch(() => undefined);
  }

  async function createHandoff() {
    await action.run("create-handoff", async () => {
      setActionError(null);
      try {
        const handoff = await createPublishHandoff({
          export_package_id: packageId,
          target_platform: "FACEBOOK_REELS",
          operator_note: t("opsExportPackages.createHandoffNote")
        });
        const success = `${t("opsExportPackages.handoffCreatedToast")}: ${handoff.id.slice(0, 8)}`;
        setCreatedHandoff(handoff);
        notify({ message: success, tone: "success" });
        await load("refresh");
      } catch (err) {
        const message = err instanceof Error ? err.message : t("opsExportPackages.createHandoffFailed");
        setActionError(message);
        notify({ message, tone: "error" });
      }
    });
  }

  async function copyPackageId(id: string) {
    if (typeof navigator === "undefined" || !navigator.clipboard) return;
    await navigator.clipboard.writeText(id).catch(() => undefined);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1200);
  }

  useEffect(() => {
    void load("initial");
  }, [packageId]);

  const boundaryStatus =
    request.initialLoading && !item ? "loading" : request.error && !item ? "error" : item ? "success" : "empty";
  const inlineError = actionError ?? (item ? request.error?.message ?? null : null);
  const stage = item ? packageStageClass(item.status) : "is-draft";
  const blockedCount = item ? item.items.filter(isItemBlocked).length : 0;

  return (
    <OperatorStudioShell
      actions={
        <TopbarRefreshButton
          busy={request.refreshing}
          disabled={request.initialLoading}
          onClick={() => void load("refresh")}
        />
      }
      description={t("opsExportPackages.description")}
      title={t("opsExportPackages.detailTitle")}
    >
      <AsyncContentBoundary
        refreshing={request.refreshing}
        status={boundaryStatus}
        skeletonVariant="detail"
        loadingLabel={t("opsExportPackages.loadingDetail")}
        errorState={
          <OpsStatePanel
            action={
              <button type="button" onClick={() => void load("initial")}>
                {t("opsExportPackages.retry")}
              </button>
            }
            detail={request.error?.message ?? t("opsExportPackages.notFound")}
            title={t("opsExportPackages.unavailableDetail")}
            variant="error"
          />
        }
      >
        {item ? (
          <div className="export-package-dossier is-open">
            <article className={`export-package-dossier__stamp ${stage}`}>
              <nav aria-label={t("opsExportPackages.related")} className="export-package-dossier__rail">
                <Link className="export-package-dossier__link" href="/publishing/export-packages">
                  <PackageDetailIcon kind="packages" />
                  <span>{t("opsExportPackages.allPackages")}</span>
                </Link>
                <Link className="export-package-dossier__link" href="/selection/reup-queue">
                  <PackageDetailIcon kind="queue" />
                  <span>{t("opsExportPackages.openReupQueue")}</span>
                </Link>
                <Link className="export-package-dossier__link" href="/publishing/publish-handoffs">
                  <PackageDetailIcon kind="handoffs" />
                  <span>{t("opsExportPackages.openHandoffs")}</span>
                </Link>
              </nav>

              <div className="export-package-dossier__mix">
                <header className="export-package-dossier__stub">
                  <div className="export-package-dossier__lead">
                    <div className="export-package-dossier__who">
                      <h2 title={item.label ?? item.id}>{item.label || `${t("opsExportPackages.package")} ${item.id.slice(0, 8)}`}</h2>
                      <span className={`export-package-dossier__stamp-chip ${stage}`}>{humanizeStatus(item.status)}</span>
                      {blockedCount > 0 ? (
                        <span className="export-package-dossier__stamp-chip is-attention">
                          {blockedCount} {t("opsExportPackages.blocked")}
                        </span>
                      ) : null}
                    </div>
                    <div className="export-package-dossier__tools">
                      <div className="export-package-dossier__cta">
                        {item.publish_handoff_ids.slice(-1).map((handoffId) => (
                          <Link
                            className="export-package-dossier__action is-primary"
                            href={`/publishing/publish-handoffs/${handoffId}`}
                            key={handoffId}
                          >
                            {t("opsExportPackages.openHandoff")} {handoffId.slice(0, 8)}
                          </Link>
                        ))}
                        <AsyncButton
                          className={
                            item.publish_handoff_ids.length > 0
                              ? "export-package-dossier__action"
                              : "export-package-dossier__action is-primary"
                          }
                          disabled={item.item_count === 0 || item.status === "CANCELLED"}
                          pending={action.isPending("create-handoff")}
                          pendingLabel={t("opsExportPackages.creatingHandoff")}
                          onClick={() => void createHandoff()}
                        >
                          {t("opsExportPackages.createHandoff")}
                        </AsyncButton>
                      </div>
                      <p className="export-package-dossier__stamp-note">
                        {/* Creating a handoff does not call platform APIs or auto-publish. */}
                        {t("opsExportPackages.facebookReelsHandoff")}
                      </p>
                    </div>
                  </div>
                  <div className="export-package-dossier__facts">
                    {item.operator_note ? <p className="export-package-dossier__note">{item.operator_note}</p> : null}
                    <div className="export-package-dossier__metrics">
                      <p className="export-package-dossier__stub-meta">
                        <span>
                          {item.item_count} {t("opsExportPackages.items")}
                        </span>
                        <button
                          type="button"
                          onClick={() => void copyPackageId(item.id)}
                          title={item.id}
                          aria-label={`${t("opsExportPackages.copyId")} ${item.id.slice(0, 8)}`}
                        >
                          <PackageDetailIcon kind={copied ? "copied" : "copy"} />
                          {item.id.slice(0, 8)}
                        </button>
                      </p>
                      <ol className="export-package-dossier__timeline" aria-label={t("opsExportPackages.lifecycle")}>
                        {mergeLifecycleByMinute(lifecycleSteps(item, t), (iso) => formatDateTime(iso, locale, t)).map((step) => (
                          <li className={`is-${step.tone}`} key={step.key}>
                            {step.label ? <i aria-hidden="true" /> : null}
                            {step.label ? <strong>{step.label}</strong> : null}
                            {step.at ? (
                              <time dateTime={step.at}>{formatDateTime(step.at, locale, t)}</time>
                            ) : (
                              <span>{t("opsExportPackages.notRecorded")}</span>
                            )}
                          </li>
                        ))}
                      </ol>
                    </div>
                  </div>
                </header>
              </div>

              <div className="export-package-dossier__body">
                {createdHandoff && !item.publish_handoff_ids.includes(createdHandoff.id) ? (
                  <p>
                    <Link href={`/publishing/publish-handoffs/${createdHandoff.id}`}>
                      {t("opsExportPackages.openCreatedHandoff")} {createdHandoff.id.slice(0, 8)}
                    </Link>
                  </p>
                ) : null}
                {inlineError ? <div className="inline-error">{inlineError}</div> : null}

                <section className="export-package-dossier__contents" aria-label={t("opsExportPackages.contents")}>
                  <h3>{t("opsExportPackages.contents")}</h3>
                  {item.items.length > 0 ? (
                    <ol>
                      {item.items.map((row, index) => (
                        <PackageContentRow index={index} item={row} key={row.id} t={t} />
                      ))}
                    </ol>
                  ) : (
                    <p className="export-package-dossier__empty">{t("opsExportPackages.contentsEmpty")}</p>
                  )}
                </section>

                <OpsDetailPanel title={t("opsExportPackages.inspect")}>
                  <OpsDetailSection collapsed title={t("opsExportPackages.diagnostics")}>
                    <pre className="export-package-dossier__code">
                      {JSON.stringify({ manifest_json: item.manifest_json, diagnostics_json: item.diagnostics_json }, null, 2)}
                    </pre>
                  </OpsDetailSection>
                </OpsDetailPanel>
              </div>
            </article>
          </div>
        ) : null}
      </AsyncContentBoundary>
    </OperatorStudioShell>
  );
}

function PackageContentRow({ index, item, t }: { index: number; item: ExportPackageItem; t: (key: string) => string }) {
  const warnings = extraItemWarnings(item, t);
  const blocked = isItemBlocked(item);
  const mediaPrep = mediaPrepStatus(item);
  return (
    <li className={blocked ? "is-blocked" : undefined}>
      <b className="export-package-dossier__idx" aria-hidden="true">
        {String(index + 1).padStart(2, "0")}
      </b>
      <div className="export-package-dossier__rowhead">
        <div className="export-package-dossier__identity">
          <strong title={item.source_video_id}>{item.source_video_id.slice(0, 8)}</strong>
          {item.item_status !== "INCLUDED" ? <span>{humanizeStatus(item.item_status)}</span> : null}
          {mediaPrep && mediaPrep !== "READY_FOR_EXPORT" ? <span>{humanizeStatus(mediaPrep)}</span> : null}
          {warnings.map((warning) => (
            <em key={warning}>{warning}</em>
          ))}
        </div>
        <div className="export-package-dossier__flags">
          <span className={`export-package-dossier__flag ${item.render_output_id ? "is-ok" : "is-warn"}`}>
            {item.render_output_id ? t("opsExportPackages.renderSealed") : t("opsExportPackages.renderMissing")}
          </span>
          {item.publish_draft_id ? (
            <Link className="export-package-dossier__flag is-ok" href={`/publishing/drafts/${item.publish_draft_id}`}>
              {t("opsExportPackages.draftReady")}
            </Link>
          ) : (
            <span className="export-package-dossier__flag is-warn">{t("opsExportPackages.draftMissing")}</span>
          )}
        </div>
        <nav>
          <Link href={`/production/final-review/${item.source_video_id}`}>{t("opsExportPackages.openFinalReview")}</Link>
          <Link href={`/production/transcript-editor/${item.source_video_id}`}>{t("opsExportPackages.openTranscript")}</Link>
          {item.publish_draft_id ? <Link href={`/publishing/drafts/${item.publish_draft_id}`}>{t("opsExportPackages.openDraft")}</Link> : null}
        </nav>
      </div>
    </li>
  );
}

function extraItemWarnings(item: ExportPackageItem, t: (key: string) => string): string[] {
  const raw = item.diagnostics_json?.warnings;
  const codes = Array.isArray(raw) ? raw.filter((entry): entry is string => typeof entry === "string") : [];
  return codes.flatMap((code) => {
    if (code === "MISSING_RENDER_OUTPUT" && !item.render_output_id) return [];
    if (code === "MISSING_PUBLISH_DRAFT" && !item.publish_draft_id) return [];
    if (code === "MISSING_RENDER_OUTPUT") return [t("opsExportPackages.missingRenderWarning")];
    if (code === "MISSING_PUBLISH_DRAFT") return [t("opsExportPackages.missingDraftWarning")];
    return [code.replaceAll("_", " ")];
  });
}

function isItemBlocked(item: ExportPackageItem): boolean {
  const raw = item.diagnostics_json?.warnings;
  return !item.render_output_id || !item.publish_draft_id || (Array.isArray(raw) && raw.length > 0);
}

function mediaPrepStatus(item: ExportPackageItem): string | null {
  const value = item.diagnostics_json?.media_prep_status;
  return typeof value === "string" ? value : null;
}

function lifecycleSteps(item: ExportPackage, t: (key: string) => string) {
  return [
    {
      key: "recorded",
      label: "",
      at: item.ready_at ?? item.created_at,
      tone: "done" as const
    },
    {
      key: "failed",
      label: t("opsExportPackages.failedAt"),
      at: item.failed_at,
      tone: item.failed_at ? ("attention" as const) : ("pending" as const)
    },
    {
      key: "cancelled",
      label: t("opsExportPackages.cancelledAt"),
      at: item.cancelled_at,
      tone: item.cancelled_at ? ("muted" as const) : ("pending" as const)
    }
  ].filter((step) => step.key === "recorded" || Boolean(step.at));
}

function packageStageClass(status: string): string {
  if (status === "FAILED_NEEDS_ATTENTION") return "is-attention";
  if (status === "HANDOFF_CREATED") return "is-handed";
  if (status === "READY_FOR_HANDOFF") return "is-ready";
  if (status === "CANCELLED") return "is-cancelled";
  return "is-draft";
}

function PackageDetailIcon({ kind }: { kind: "packages" | "queue" | "handoffs" | "copy" | "copied" }) {
  const className =
    kind === "copy" || kind === "copied" ? "export-package-dossier__copy-icon" : "export-package-dossier__link-icon";
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
  if (kind === "handoffs") {
    return (
      <svg aria-hidden="true" className={className} fill="none" viewBox="0 0 20 20">
        <path d="M4.4 10h11.2M15.6 10l-3.4-3.4M15.6 10l-3.4 3.4" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.55" />
      </svg>
    );
  }
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

function formatDateTime(value: string | null, locale: "en" | "vi", t: (key: string) => string): string {
  if (!value) return t("opsExportPackages.notRecorded");
  return new Intl.DateTimeFormat(locale === "vi" ? "vi-VN" : "en-US", {
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit"
  }).format(new Date(value));
}
