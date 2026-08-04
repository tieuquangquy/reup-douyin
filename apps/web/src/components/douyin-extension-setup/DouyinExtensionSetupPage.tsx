"use client";

import { useEffect, useState, type ReactNode } from "react";
import { checkDouyinExtensionStatus, fetchDouyinExtensionStatus, getDouyinExtensionDownloadUrl } from "../../lib/api";
import { EXTENSION_BUILD_COMMAND, EXTENSION_DIST_PATH, resolveDouyinExtensionDownloadState } from "../../lib/douyinExtensionInstall";
import { useT } from "../../lib/i18n";
import { useLatestRequest } from "../../lib/useLatestRequest";
import type { DouyinExtensionStatusResponse } from "../../types/douyin-extension-setup";
import { OperatorStudioShell } from "../app-shell/OperatorStudioShell";
import { TopbarRefreshButton } from "../app-shell/TopbarRefreshButton";
import { AsyncContentBoundary } from "../shared/AsyncContentBoundary";
import { useNotice } from "../shared/NoticeCenter";
import { OpsState, formatDateTime, type OpsTone } from "../ops-console/OpsShared";

export function DouyinExtensionSetupPage() {
  const t = useT();
  const [status, setStatus] = useState<DouyinExtensionStatusResponse | null>(null);
  const request = useLatestRequest();
  const { notify } = useNotice();

  useEffect(() => {
    void loadStatus();
  }, [t]);

  async function loadStatus() {
    try {
      await request.run(() => fetchDouyinExtensionStatus(), setStatus, status ? "refresh" : "initial");
    } catch (err) {
      if (status) notify({ id: "extension-status", message: err instanceof Error ? err.message : t("extensionSetup.loadError"), tone: "error" });
    }
  }

  async function checkConnection() {
    try {
      const result = await request.run(() => checkDouyinExtensionStatus(), setStatus, "refresh");
      if (result) notify({ id: "extension-status", message: "Extension connection checked.", tone: "success" });
    } catch (err) {
      notify({ id: "extension-status", message: err instanceof Error ? err.message : t("extensionSetup.checkError"), tone: "error" });
    }
  }

  const refreshAction = (
    <TopbarRefreshButton busy={request.refreshing} disabled={request.initialLoading} onClick={() => void (status ? checkConnection() : loadStatus())} />
  );

  if (!status && !request.error) {
    return (
      <OperatorStudioShell actions={refreshAction} description={t("extensionSetup.description")} title={t("extensionSetup.title")}>
        <AsyncContentBoundary skeletonVariant="detail" loadingLabel={t("extensionSetup.loadingDetail")} status="loading"><span /></AsyncContentBoundary>
      </OperatorStudioShell>
    );
  }

  if (request.error && !status) {
    return (
      <OperatorStudioShell actions={refreshAction} description={t("extensionSetup.description")} title={t("extensionSetup.title")}>
        <AsyncContentBoundary errorState={<OpsState title={t("extensionSetup.unavailableTitle")} detail={request.error.message} retry={() => void loadStatus()} />} skeletonVariant="detail" status="error"><span /></AsyncContentBoundary>
      </OperatorStudioShell>
    );
  }

  return (
    <OperatorStudioShell actions={refreshAction} description={t("extensionSetup.description")} title={t("extensionSetup.title")}>
      <AsyncContentBoundary refreshing={request.refreshing} skeletonVariant="detail" status="success">
        <ExtensionSetupBody error={null} status={status} t={t} />
      </AsyncContentBoundary>
    </OperatorStudioShell>
  );
}

function ExtensionSetupBody({
  status,
  error,
  t,
}: {
  status: DouyinExtensionStatusResponse | null;
  error: string | null;
  t: (key: string) => string;
}) {
  const downloadUrl = getDouyinExtensionDownloadUrl();
  const downloadState = resolveDouyinExtensionDownloadState(status, downloadUrl);
  const tone = statusTone(status);
  const chromeUrl = status?.chrome_extensions_url ?? "chrome://extensions";
  const edgeUrl = status?.edge_extensions_url ?? "edge://extensions";

  return (
    <>
      {error ? <div className="inline-error">{error}</div> : null}

      <main className="ops-page ext-setup-page">
        <div className="ext-setup-freshness">
          <p>
            {t("extensionSetup.checkedAt")}{" "}
            <time dateTime={status?.backend_checked_at}>{formatDateTime(status?.backend_checked_at)}</time>
          </p>
          <SetupChip label={statusLabel(status, t)} tone={tone} />
          <span className="ext-setup-freshness__headline">{status?.operator_message ?? t("extensionSetup.noStatus")}</span>
        </div>

        <section className="ext-setup-kpis" aria-label={t("extensionSetup.summary")}>
          <SetupKpi
            label={t("extensionSetup.connected")}
            value={status?.connected ? t("extensionSetup.yes") : t("extensionSetup.no")}
            detail={statusLabel(status, t)}
            tone={status?.connected ? "good" : "warn"}
          />
          <SetupKpi
            label={t("extensionSetup.compatibility")}
            value={compatLabel(status, t)}
            detail={
              status
                ? `${status.extension_version ?? t("extensionSetup.notReported")} / ${status.backend_expected_extension_version}`
                : t("extensionSetup.notReported")
            }
            tone={compatTone(status)}
          />
          <SetupKpi
            label={t("extensionSetup.download")}
            value={status?.download_available ? t("extensionSetup.yes") : t("extensionSetup.no")}
            detail={downloadState.description}
            tone={status?.download_available ? "good" : "muted"}
          />
          <SetupKpi
            label={t("extensionSetup.nextAction")}
            value={status?.recommended_next_action_label ?? t("extensionSetup.notReported")}
            detail={t("extensionSetup.nextActionDetail")}
            tone={tone}
          />
        </section>

        <div className="ext-setup-toolbar">
          <div className="ext-setup-actions" aria-label={t("extensionSetup.triage")}>
            {downloadState.kind === "available" ? (
              <a className="ext-setup-download is-ready" download href={downloadState.href}>
                {t("extensionSetup.downloadZip")}
              </a>
            ) : (
              <span aria-disabled="true" className="ext-setup-download is-muted" role="status">
                {downloadState.kind === "loading" ? t("extensionSetup.downloadChecking") : t("extensionSetup.downloadUnavailable")}
              </span>
            )}
            <ShortcutAction label={t("extensionSetup.chromeExtensions")} url={chromeUrl} copyLabel={t("extensionSetup.copyUrl")} openLabel={t("extensionSetup.open")} />
            <ShortcutAction label={t("extensionSetup.edgeExtensions")} url={edgeUrl} copyLabel={t("extensionSetup.copyUrl")} openLabel={t("extensionSetup.open")} />
          </div>
        </div>

        <SetupPanel title={t("extensionSetup.installSteps")}>
          <ol className="ext-setup-steps">
            <li>
              {t("extensionSetup.stepBuild")} <code>{EXTENSION_BUILD_COMMAND}</code>
            </li>
            <li>{t("extensionSetup.stepOpenExtensions")}</li>
            <li>{t("extensionSetup.stepDeveloperMode")}</li>
            <li>{t("extensionSetup.stepLoadUnpacked")}</li>
            <li>
              {t("extensionSetup.stepSelectDist")} <code>{EXTENSION_DIST_PATH}</code>
            </li>
            <li>
              {t("extensionSetup.stepApiUrl")} <code>http://127.0.0.1:8000</code>
            </li>
          </ol>
          <p className="ext-setup-footnote">{t("extensionSetup.manualInstall")}</p>
        </SetupPanel>

        <SetupPanel title={t("extensionSetup.diagnostics")}>
          {status ? (
            <dl className="ext-setup-diagnostics">
              <DiagnosticRow label={t("extensionSetup.diagStatus")} value={status.status} />
              <DiagnosticRow label={t("extensionSetup.diagNext")} value={status.recommended_next_action_label} />
              <DiagnosticRow label={t("extensionSetup.diagLastSeen")} value={formatLastSeen(status.last_seen_at, t)} />
              <DiagnosticRow label={t("extensionSetup.diagBrowser")} value={status.browser_family ?? t("extensionSetup.unknown")} />
              <DiagnosticRow label={t("extensionSetup.diagExtVersion")} value={status.extension_version ?? t("extensionSetup.notReported")} />
              <DiagnosticRow label={t("extensionSetup.diagExpectedVersion")} value={status.backend_expected_extension_version} />
              <DiagnosticRow label={t("extensionSetup.diagCompat")} value={status.version_status} />
              <DiagnosticRow label={t("extensionSetup.diagInstallId")} value={status.install_id ?? t("extensionSetup.notReported")} />
              <DiagnosticRow label={t("extensionSetup.diagExtensionId")} value={status.extension_id ?? t("extensionSetup.notReported")} />
              <DiagnosticRow label={t("extensionSetup.diagDownload")} value={status.download_available ? t("extensionSetup.yes") : t("extensionSetup.no")} />
              <DiagnosticRow label={t("extensionSetup.diagManual")} value={status.manual_install_required ? t("extensionSetup.yes") : t("extensionSetup.no")} />
            </dl>
          ) : (
            <p className="ext-setup-empty">{t("extensionSetup.noStatus")}</p>
          )}
        </SetupPanel>
      </main>
    </>
  );
}

function SetupPanel({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="ext-setup-panel">
      <div className="ext-setup-panel__head">
        <h2>{title}</h2>
      </div>
      <div className="ext-setup-panel__body">{children}</div>
    </section>
  );
}

function SetupKpi({
  label,
  value,
  detail,
  tone = "muted",
}: {
  label: string;
  value: string;
  detail: string;
  tone?: OpsTone;
}) {
  return (
    <article className={`ext-setup-kpi tone-${tone}`} title={detail}>
      <em>{label}</em>
      <strong>{value}</strong>
      <span>{detail}</span>
    </article>
  );
}

function SetupChip({ label, tone }: { label: string; tone: OpsTone }) {
  return <span className={`ext-setup-chip tone-${tone}`}>{label}</span>;
}

function ShortcutOpenIcon() {
  return (
    <svg className="ext-setup-shortcut__icon" viewBox="0 0 24 24" aria-hidden="true" fill="none">
      <path
        d="M10 5H7.5A2.5 2.5 0 0 0 5 7.5v9A2.5 2.5 0 0 0 7.5 19h9a2.5 2.5 0 0 0 2.5-2.5V14"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path
        d="M13 5h6v6M19 5l-8 8"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function ShortcutCopyIcon() {
  return (
    <svg className="ext-setup-shortcut__icon" viewBox="0 0 24 24" aria-hidden="true" fill="none">
      <rect x="8" y="8" width="11" height="11" rx="1.5" stroke="currentColor" strokeWidth="1.8" />
      <path
        d="M6.5 15H6A1.5 1.5 0 0 1 4.5 13.5v-8A1.5 1.5 0 0 1 6 4h8A1.5 1.5 0 0 1 15.5 5.5V6"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
      />
    </svg>
  );
}

function ShortcutAction({
  label,
  url,
  copyLabel,
  openLabel,
}: {
  label: string;
  url: string;
  copyLabel: string;
  openLabel: string;
}) {
  async function copy() {
    if (typeof navigator !== "undefined" && navigator.clipboard) await navigator.clipboard.writeText(url);
  }

  return (
    <span className="ext-setup-shortcut">
      <em>{label}</em>
      <code title={url}>{url}</code>
      <a className="ext-setup-shortcut__btn" href={url} aria-label={openLabel} title={openLabel}>
        <ShortcutOpenIcon />
      </a>
      <button className="ext-setup-shortcut__btn" type="button" onClick={() => void copy()} aria-label={copyLabel} title={copyLabel}>
        <ShortcutCopyIcon />
      </button>
    </span>
  );
}

function DiagnosticRow({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt>{label}</dt>
      <dd>{value}</dd>
    </div>
  );
}

function statusTone(status: DouyinExtensionStatusResponse | null): OpsTone {
  if (!status) return "muted";
  if (status.status === "connected") return "good";
  if (status.status === "version_mismatch" || status.status === "backend_unreachable_from_extension") return "danger";
  return "warn";
}

function statusLabel(status: DouyinExtensionStatusResponse | null, t: (key: string) => string): string {
  if (!status) return t("extensionSetup.statusUnknown");
  const map: Record<DouyinExtensionStatusResponse["status"], string> = {
    connected: t("extensionSetup.statusConnected"),
    not_installed_or_not_connected: t("extensionSetup.statusNotConnected"),
    installed_not_connected: t("extensionSetup.statusInstalledNotConnected"),
    version_mismatch: t("extensionSetup.statusVersionMismatch"),
    backend_unreachable_from_extension: t("extensionSetup.statusBackendUnreachable"),
    stale_connection: t("extensionSetup.statusStale"),
  };
  return map[status.status];
}

function compatLabel(status: DouyinExtensionStatusResponse | null, t: (key: string) => string): string {
  if (!status) return t("extensionSetup.notReported");
  if (status.version_status === "compatible") return t("extensionSetup.compatOk");
  if (status.version_status === "version_mismatch") return t("extensionSetup.compatMismatch");
  return t("extensionSetup.compatUnknown");
}

function compatTone(status: DouyinExtensionStatusResponse | null): OpsTone {
  if (!status) return "muted";
  if (status.version_status === "compatible") return "good";
  if (status.version_status === "version_mismatch") return "danger";
  return "muted";
}

function formatLastSeen(value: string | null, t: (key: string) => string): string {
  if (!value) return t("extensionSetup.never");
  return formatDateTime(value);
}
