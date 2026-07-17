"use client";

import { useEffect, useState } from "react";
import { checkDouyinExtensionStatus, fetchDouyinExtensionStatus, getDouyinExtensionDownloadUrl } from "../../lib/api";
import { EXTENSION_BUILD_COMMAND, EXTENSION_DIST_PATH, resolveDouyinExtensionDownloadState } from "../../lib/douyinExtensionInstall";
import type { DouyinExtensionStatusResponse } from "../../types/douyin-extension-setup";
import { OperatorStudioShell } from "../app-shell/OperatorStudioShell";
import { PageShell } from "../app-shell/PageShell";

export function DouyinExtensionSetupPage() {
  const [status, setStatus] = useState<DouyinExtensionStatusResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [checking, setChecking] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void loadStatus();
  }, []);

  async function loadStatus() {
    setLoading(true);
    setError(null);
    try {
      setStatus(await fetchDouyinExtensionStatus());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load extension status.");
    } finally {
      setLoading(false);
    }
  }

  async function checkConnection() {
    setChecking(true);
    setError(null);
    try {
      setStatus(await checkDouyinExtensionStatus());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to check extension connection.");
    } finally {
      setChecking(false);
    }
  }

  const downloadUrl = getDouyinExtensionDownloadUrl();
  const downloadState = resolveDouyinExtensionDownloadState(status, downloadUrl);

  return (
    <OperatorStudioShell
      description="Install, verify, and troubleshoot the local Douyin current-tab capture extension."
      title="Douyin Extension Setup"
    >
      <PageShell
        actions={<button onClick={() => void checkConnection()} type="button" disabled={checking}>{checking ? "Checking..." : "Check extension connection"}</button>}
        description="Use this page to download the extension build, open browser extension settings, and verify backend connectivity. Browser installation is still manual."
        title="Extension Setup"
      >
        <div className="intake-layout">
          <div className="intake-form">
            <section className="operator-panel">
              <div className="operator-panel-heading">
                <div>
                  <h2>Install / download</h2>
                  <p>Download a ZIP only when the backend reports a packageable build, or use the manual Load unpacked workflow.</p>
                </div>
              </div>
              <div className="actions-row">
                {downloadState.kind === "available" ? (
                  <a className="button-like" download href={downloadState.href}>Download ZIP</a>
                ) : (
                  <span aria-disabled="true" className="button-like muted" role="status">{downloadState.label}</span>
                )}
              </div>
              <p className="muted">{downloadState.description}</p>
              <p className="muted">If download is unavailable, run <code>{EXTENSION_BUILD_COMMAND}</code> from the repository root and load <code>{EXTENSION_DIST_PATH}</code>.</p>
              <p className="muted">Manual install remains required because Chrome and Edge do not allow this local web app to install unpacked extensions automatically.</p>
            </section>

            <section className="operator-panel">
              <div className="operator-panel-heading">
                <div>
                  <h2>Manual install steps</h2>
                  <p>Load the unpacked extension in the browser session you use for Douyin.</p>
                </div>
              </div>
              <ol className="intake-flow">
                <li>Run <code>{EXTENSION_BUILD_COMMAND}</code> if a ZIP download is not available.</li>
                <li>Open the Chrome or Edge extensions page.</li>
                <li>Enable Developer mode.</li>
                <li>Choose Load unpacked.</li>
                <li>Select <code>{EXTENSION_DIST_PATH}</code>, or extract the downloaded ZIP and select the extracted folder.</li>
                <li>Open the extension popup and confirm the API URL is <code>http://127.0.0.1:8000</code> unless your backend runs elsewhere.</li>
              </ol>
            </section>

            <section className="operator-panel">
              <div className="operator-panel-heading">
                <div>
                  <h2>Browser extension shortcuts</h2>
                  <p>Use these shortcuts to open the browser extension management page. If a browser blocks the link, copy and paste the URL into the address bar.</p>
                </div>
              </div>
              <div className="filter-grid">
                <ShortcutCard label="Chrome Extensions" url="chrome://extensions" />
                <ShortcutCard label="Edge Extensions" url="edge://extensions" />
              </div>
            </section>
          </div>

          <aside className="intake-side">
            <section className={`operator-panel intake-status ${statusTone(status)}`}>
              <div className="operator-panel-heading">
                <div>
                  <h2>Connection status</h2>
                  <p>{loading ? "Loading setup status..." : status?.operator_message ?? "No status loaded."}</p>
                </div>
              </div>
              {error ? <p className="danger-text">{error}</p> : null}
              {status ? <StatusDetails status={status} /> : null}
            </section>
          </aside>
        </div>
      </PageShell>
    </OperatorStudioShell>
  );
}

function ShortcutCard({ label, url }: { label: string; url: string }) {
  async function copy() {
    if (typeof navigator !== "undefined" && navigator.clipboard) await navigator.clipboard.writeText(url);
  }

  return (
    <div className="operator-panel">
      <h3>{label}</h3>
      <p><code>{url}</code></p>
      <div className="actions-row">
        <a className="button-like" href={url}>Open</a>
        <button type="button" onClick={() => void copy()}>Copy URL</button>
      </div>
    </div>
  );
}

function StatusDetails({ status }: { status: DouyinExtensionStatusResponse }) {
  return (
    <dl className="summary-list">
      <div><dt>Status</dt><dd>{status.status}</dd></div>
      <div><dt>Recommended next action</dt><dd>{status.recommended_next_action_label}</dd></div>
      <div><dt>Last seen</dt><dd>{formatDateTime(status.last_seen_at)}</dd></div>
      <div><dt>Browser</dt><dd>{status.browser_family ?? "Unknown"}</dd></div>
      <div><dt>Extension version</dt><dd>{status.extension_version ?? "Not reported"}</dd></div>
      <div><dt>Backend expected version</dt><dd>{status.backend_expected_extension_version}</dd></div>
      <div><dt>Compatibility</dt><dd>{status.version_status}</dd></div>
      <div><dt>Install id</dt><dd>{status.install_id ?? "Not reported"}</dd></div>
      <div><dt>Extension id</dt><dd>{status.extension_id ?? "Not reported"}</dd></div>
      <div><dt>Download available</dt><dd>{status.download_available ? "Yes" : "No"}</dd></div>
      <div><dt>Manual install required</dt><dd>{status.manual_install_required ? "Yes" : "No"}</dd></div>
    </dl>
  );
}

function statusTone(status: DouyinExtensionStatusResponse | null): "good" | "warn" | "danger" | "muted" {
  if (!status) return "muted";
  if (status.status === "connected") return "good";
  if (status.status === "version_mismatch" || status.status === "backend_unreachable_from_extension") return "danger";
  return "warn";
}

function formatDateTime(value: string | null): string {
  if (!value) return "Never";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
}
