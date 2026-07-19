"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import {
  captureDouyinExtensionPage,
  checkDouyinExtensionStatus,
  detectDouyinExtensionPage,
  fetchDouyinExtensionHistory,
  fetchDouyinExtensionStatus
} from "../../lib/api";
import { loginPathForSurface } from "../../lib/authSurface";
import type { DouyinExtensionStatusResponse } from "../../types/douyin-extension-setup";
import type {
  DouyinExtensionCaptureResponse,
  DouyinExtensionDetectPageResponse,
  DouyinExtensionManagerHistoryItem,
  DouyinExtensionManagerHistoryResponse,
  DouyinExtensionPageSnapshot,
  DouyinExtensionPageType
} from "../../types/douyin-extension-manager";
import { OpsConsoleShell } from "../app-shell/OpsConsoleShell";

const EXTENSION_SETUP_PATH = "/setup/douyin-extension";
const EXTENSION_SETUP_HREF = `${loginPathForSurface("operator")}?next=${encodeURIComponent(EXTENSION_SETUP_PATH)}`;

type ManagerFormState = {
  url: string;
  title: string;
  pageType: DouyinExtensionPageType;
  profileUrl: string;
  profileExternalId: string;
  handle: string;
  displayName: string;
  videoLinkCount: string;
  videoUrls: string;
};

const INITIAL_FORM: ManagerFormState = {
  url: "",
  title: "",
  pageType: "unknown_page",
  profileUrl: "",
  profileExternalId: "",
  handle: "",
  displayName: "",
  videoLinkCount: "0",
  videoUrls: ""
};

const PAGE_TYPE_OPTIONS: DouyinExtensionPageType[] = [
  "unknown_page",
  "login_page",
  "challenge_page",
  "home_feed_page",
  "profile_page",
  "profile_feed_page",
  "video_detail_page",
  "unsupported_page"
];

export function DouyinExtensionManagerPage() {
  const [status, setStatus] = useState<DouyinExtensionStatusResponse | null>(null);
  const [history, setHistory] = useState<DouyinExtensionManagerHistoryResponse | null>(null);
  const [form, setForm] = useState<ManagerFormState>(INITIAL_FORM);
  const [loading, setLoading] = useState(true);
  const [working, setWorking] = useState<"status" | "detect" | "capture" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [detectResult, setDetectResult] = useState<DouyinExtensionDetectPageResponse | null>(null);
  const [captureResult, setCaptureResult] = useState<DouyinExtensionCaptureResponse | null>(null);

  useEffect(() => {
    void loadManagerState();
  }, []);

  const troubleshooting = useMemo(() => buildTroubleshooting(status, detectResult, history?.items[0] ?? null), [status, detectResult, history]);

  async function loadManagerState() {
    setLoading(true);
    setError(null);
    try {
      const [statusPayload, historyPayload] = await Promise.all([fetchDouyinExtensionStatus(), fetchDouyinExtensionHistory(10)]);
      setStatus(statusPayload);
      setHistory(historyPayload);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load Douyin extension manager state.");
    } finally {
      setLoading(false);
    }
  }

  async function checkConnection() {
    setWorking("status");
    setError(null);
    try {
      const [statusPayload, historyPayload] = await Promise.all([checkDouyinExtensionStatus(), fetchDouyinExtensionHistory(10)]);
      setStatus(statusPayload);
      setHistory(historyPayload);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to check Douyin extension connection.");
    } finally {
      setWorking(null);
    }
  }

  async function detect(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setWorking("detect");
    setError(null);
    try {
      const response = await detectDouyinExtensionPage({ page: buildSnapshot(form), diagnostics: { extension_manager_source: "web_manager" } });
      setDetectResult(response);
      setHistory(await fetchDouyinExtensionHistory(10));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to detect current page.");
      setHistory(await fetchDouyinExtensionHistory(10).catch(() => history));
    } finally {
      setWorking(null);
    }
  }

  async function capture() {
    setWorking("capture");
    setError(null);
    try {
      const response = await captureDouyinExtensionPage({
        schema_version: "douyin_extension_capture.v1",
        captured_at: new Date().toISOString(),
        persist: true,
        page: buildSnapshot(form),
        profile: buildProfile(form),
        videos: buildVideos(form),
        diagnostics: { extension_manager_source: "web_manager" }
      });
      setCaptureResult(response);
      setHistory(await fetchDouyinExtensionHistory(10));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to capture current page.");
      setHistory(await fetchDouyinExtensionHistory(10).catch(() => history));
    } finally {
      setWorking(null);
    }
  }

  return (
    <OpsConsoleShell
      actions={<button disabled={working === "status"} onClick={() => void checkConnection()} type="button">{working === "status" ? "Checking..." : "Check connection"}</button>}
      description="Detect, capture, and troubleshoot the Douyin browser extension. Install lives in Operator Studio Setup."
      title="Douyin Extension Manager"
    >
        {error ? <section className="operator-panel intake-status danger"><strong>Manager error:</strong> {error}</section> : null}
        <div className="intake-layout">
          <div className="intake-form">
            <SetupPointerSection />
            <ConnectionSection loading={loading} status={status} />
            <CaptureSection captureResult={captureResult} history={history} />
            <CurrentPageToolsSection
              detectResult={detectResult}
              form={form}
              onCapture={() => void capture()}
              onDetect={(event) => void detect(event)}
              setForm={setForm}
              working={working}
            />
          </div>
          <aside className="intake-side">
            <TroubleshootingSection items={troubleshooting} />
            <HistorySection history={history} />
          </aside>
        </div>
    </OpsConsoleShell>
  );
}

function SetupPointerSection() {
  return (
    <section className="operator-panel">
      <div className="operator-panel-heading">
        <div>
          <h2>Need to install the extension?</h2>
          <p>First-time install and verify live in Operator Studio Extension Setup.</p>
        </div>
      </div>
      <div className="actions-row">
        <a className="button-like" href={EXTENSION_SETUP_HREF}>
          Open Extension Setup
        </a>
      </div>
      <p className="muted">This Ops page focuses on connection health, capture diagnostics, and advanced backend testing.</p>
    </section>
  );
}

function ConnectionSection({ loading, status }: { loading: boolean; status: DouyinExtensionStatusResponse | null }) {
  return (
    <section className={`operator-panel intake-status ${statusTone(status)}`}>
      <div className="operator-panel-heading">
        <div>
          <h2>Connection status</h2>
          <p>{loading ? "Loading extension status..." : status?.operator_message ?? "No status loaded."}</p>
        </div>
      </div>
      {status ? (
        <dl className="summary-list">
          <div><dt>Status</dt><dd>{status.status}</dd></div>
          <div><dt>Last seen</dt><dd>{formatDateTime(status.last_seen_at)}</dd></div>
          <div><dt>Browser</dt><dd>{status.browser_family ?? "Unknown"}</dd></div>
          <div><dt>Extension version</dt><dd>{status.extension_version ?? "Not reported"}</dd></div>
          <div><dt>Backend version</dt><dd>{status.backend_expected_extension_version}</dd></div>
          <div><dt>Compatibility</dt><dd>{status.version_status}</dd></div>
          <div><dt>Next action</dt><dd>{status.recommended_next_action_label}</dd></div>
        </dl>
      ) : null}
    </section>
  );
}

function CurrentPageToolsSection({
  detectResult,
  form,
  onCapture,
  onDetect,
  setForm,
  working
}: {
  detectResult: DouyinExtensionDetectPageResponse | null;
  form: ManagerFormState;
  onCapture: () => void;
  onDetect: (event: FormEvent<HTMLFormElement>) => void;
  setForm: (next: ManagerFormState) => void;
  working: "status" | "detect" | "capture" | null;
}) {
  return (
    <details className="operator-panel advanced-panel">
      <summary>
        <span>
          <strong>Advanced troubleshooting · manual backend testing</strong>
          <small>Use typed safe snapshot fields only when validating backend detect/capture behavior.</small>
        </span>
        <span className="pill warn">Manual backend test only</span>
      </summary>
      <p className="muted">This form does not read the active browser tab. For real current-page detection or capture, use the browser extension popup on a Douyin tab.</p>
      <form className="intake-form" onSubmit={onDetect}>
        <label className="field">
          Page URL
          <input value={form.url} onChange={(event) => setForm({ ...form, url: event.target.value })} placeholder="https://www.douyin.com/user/..." />
        </label>
        <div className="filter-grid">
          <label className="field">
            Page type
            <select value={form.pageType} onChange={(event) => setForm({ ...form, pageType: event.target.value as DouyinExtensionPageType })}>
              {PAGE_TYPE_OPTIONS.map((item) => <option key={item} value={item}>{item}</option>)}
            </select>
          </label>
          <label className="field">
            Video link count
            <input min="0" type="number" value={form.videoLinkCount} onChange={(event) => setForm({ ...form, videoLinkCount: event.target.value })} />
          </label>
        </div>
        <label className="field">
          Page title
          <input value={form.title} onChange={(event) => setForm({ ...form, title: event.target.value })} />
        </label>
        <label className="field">
          Profile URL
          <input value={form.profileUrl} onChange={(event) => setForm({ ...form, profileUrl: event.target.value })} placeholder="https://www.douyin.com/user/..." />
        </label>
        <div className="filter-grid">
          <label className="field">
            Profile external id
            <input value={form.profileExternalId} onChange={(event) => setForm({ ...form, profileExternalId: event.target.value })} />
          </label>
          <label className="field">
            Handle
            <input value={form.handle} onChange={(event) => setForm({ ...form, handle: event.target.value })} />
          </label>
        </div>
        <label className="field">
          Display name
          <input value={form.displayName} onChange={(event) => setForm({ ...form, displayName: event.target.value })} />
        </label>
        <label className="field">
          Video URLs for capture, one per line
          <textarea rows={4} value={form.videoUrls} onChange={(event) => setForm({ ...form, videoUrls: event.target.value })} />
        </label>
        <div className="actions-row">
          <button disabled={working === "detect"} type="submit">{working === "detect" ? "Testing detect..." : "Test detect from form"}</button>
          <button disabled={working === "capture"} onClick={onCapture} type="button">{working === "capture" ? "Submitting test..." : "Submit manual capture test"}</button>
        </div>
      </form>
      {detectResult ? (
        <dl className="summary-list">
          <div><dt>Detected page type</dt><dd>{detectResult.detected_page_type}</dd></div>
          <div><dt>Capture supported</dt><dd>{detectResult.supported_capture ? "Yes" : "No"}</dd></div>
          <div><dt>Recommended action</dt><dd>{detectResult.recommended_action_label}</dd></div>
          <div><dt>Message</dt><dd>{detectResult.operator_message}</dd></div>
        </dl>
      ) : null}
    </details>
  );
}

function CaptureSection({ captureResult, history }: { captureResult: DouyinExtensionCaptureResponse | null; history: DouyinExtensionManagerHistoryResponse | null }) {
  const latestCapture = history?.items.find((item) => item.event_type === "capture") ?? null;
  return (
    <section className="operator-panel">
      <div className="operator-panel-heading">
        <div>
          <h2>Capture status</h2>
          <p>Latest result from real extension captures or manual backend tests that use the same capture endpoint.</p>
        </div>
      </div>
      {captureResult ? (
        <>
          <dl className="summary-list">
            <div><dt>Success</dt><dd>{captureResult.success ? "Yes" : "No"}</dd></div>
            <div><dt>Capture session</dt><dd>{captureResult.capture_session_id ?? "Not staged"}</dd></div>
            <div><dt>Stage</dt><dd>{captureResult.stage}</dd></div>
            <div><dt>Submitted</dt><dd>{captureResult.submitted_count}</dd></div>
            <div><dt>Staged items</dt><dd>{captureResult.staged_count}</dd></div>
            <div><dt>Normalized</dt><dd>{captureResult.normalized_item_count}</dd></div>
            <div><dt>Ready for inbox review</dt><dd>{captureResult.ready_item_count}</dd></div>
            <div><dt>Duplicates</dt><dd>{captureResult.deduped_count}</dd></div>
            <div><dt>Skipped</dt><dd>{captureResult.skipped_count}</dd></div>
            <div><dt>Failed</dt><dd>{captureResult.failed_count}</dd></div>
            <div><dt>Warnings</dt><dd>{captureResult.warning_codes.length ? captureResult.warning_codes.join(", ") : captureResult.warning ?? "None"}</dd></div>
            <div><dt>Diagnostics</dt><dd>{captureResult.diagnostics_id}</dd></div>
            <div><dt>Captured at</dt><dd>{formatDateTime(captureResult.discovered_at)}</dd></div>
            <div><dt>Next route</dt><dd><a href={captureResult.next_suggested_route}>Open Capture Inbox</a></dd></div>
          </dl>
          {captureResult.failure_summaries.length ? (
            <div className="intake-status warn">
              <strong>Item-level diagnostics</strong>
              <ul>
                {captureResult.failure_summaries.slice(0, 5).map((failure, index) => (
                  <li key={`${failure.item_index ?? "session"}-${failure.code}-${index}`}>
                    item {failure.item_index ?? "session"} · {failure.stage} · {failure.code}: {failure.message}
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
        </>
      ) : latestCapture ? (
        <dl className="summary-list">
          <div><dt>Status</dt><dd>{latestCapture.status}</dd></div>
          <div><dt>Videos discovered</dt><dd>{latestCapture.videos_discovered_count}</dd></div>
          <div><dt>Candidates matched</dt><dd>{latestCapture.candidates_matched_count}</dd></div>
          <div><dt>Latest error/warning</dt><dd>{latestCapture.error_message ?? latestCapture.warning ?? "None"}</dd></div>
          <div><dt>Timestamp</dt><dd>{formatDateTime(latestCapture.created_at)}</dd></div>
        </dl>
      ) : <p className="muted">No capture history yet.</p>}
    </section>
  );
}

function TroubleshootingSection({ items }: { items: Array<{ state: string; action: string }> }) {
  return (
    <section className="operator-panel">
      <h2>Troubleshooting</h2>
      <ol className="intake-flow">
        {items.map((item) => (
          <li key={item.state}><strong>{item.state}:</strong> {item.action}</li>
        ))}
      </ol>
    </section>
  );
}

function HistorySection({ history }: { history: DouyinExtensionManagerHistoryResponse | null }) {
  return (
    <section className="operator-panel intake-recent">
      <h2>Recent history</h2>
      {history?.items.length ? (
        <div className="stacked-list">
          {history.items.map((item) => <HistoryCard item={item} key={item.event_id} />)}
        </div>
      ) : <p className="muted">No manager events recorded yet.</p>}
    </section>
  );
}

function HistoryCard({ item }: { item: DouyinExtensionManagerHistoryItem }) {
  return (
    <article className="operator-panel">
      <strong>{item.event_type} · {item.status}</strong>
      <p className="muted">{formatDateTime(item.created_at)} · {item.page_type ?? "no page type"}</p>
      <dl className="summary-list">
        <div><dt>Imported profiles</dt><dd>{item.imported_profile_count}</dd></div>
        <div><dt>Videos</dt><dd>{item.videos_discovered_count}</dd></div>
        <div><dt>Candidates</dt><dd>{item.candidates_matched_count}</dd></div>
        <div><dt>Message</dt><dd>{item.error_message ?? item.warning ?? item.recommended_next_action_label ?? "OK"}</dd></div>
      </dl>
    </article>
  );
}

function buildSnapshot(form: ManagerFormState): DouyinExtensionPageSnapshot {
  return {
    url: optional(form.url),
    title: optional(form.title),
    page_type: form.pageType,
    profile_url: optional(form.profileUrl),
    profile_external_id: optional(form.profileExternalId),
    handle: optional(form.handle),
    display_name: optional(form.displayName),
    video_link_count: Math.max(0, Number.parseInt(form.videoLinkCount || "0", 10) || 0)
  };
}

function buildProfile(form: ManagerFormState) {
  if (!form.profileExternalId && !form.handle && !form.displayName) return null;
  return {
    sec_uid: optional(form.profileExternalId),
    handle: optional(form.handle),
    unique_id: optional(form.handle),
    display_name: optional(form.displayName),
    nickname: optional(form.displayName)
  };
}

function buildVideos(form: ManagerFormState) {
  return form.videoUrls
    .split(/\r?\n/)
    .map((value) => value.trim())
    .filter(Boolean)
    .map((url) => ({ source_video_url: url, url }));
}

function buildTroubleshooting(status: DouyinExtensionStatusResponse | null, detectResult: DouyinExtensionDetectPageResponse | null, latest: DouyinExtensionManagerHistoryItem | null) {
  const items = [
    { state: "not_installed_or_not_connected", action: "Build/download the extension, load it manually, then run connection check from the popup." },
    { state: "stale_connection", action: "Open the extension popup and run Check extension connection again." },
    { state: "version_mismatch", action: "Rebuild or download the latest extension, reload it in Chrome/Edge, then reconnect." },
    { state: "backend_unreachable", action: "Confirm the API server is running and the popup backend URL is correct." }
  ];
  if (status?.status === "connected") items.unshift({ state: "capture_ready", action: "Open Douyin and use the extension popup for real active-tab capture. Use the collapsed manual backend form only for troubleshooting typed snapshot payloads." });
  if (detectResult?.detected_page_type === "login_page") items.unshift({ state: "login_required", action: "Log in to Douyin manually in the browser, then detect again." });
  if (detectResult?.detected_page_type === "challenge_page") items.unshift({ state: "challenge_required", action: "Solve the challenge manually in the browser, then detect again." });
  if (detectResult && !detectResult.supported_capture) items.unshift({ state: "unsupported_page", action: "Open a supported Douyin profile, feed, or video page." });
  if (latest?.status === "failed") items.unshift({ state: "capture_failed", action: latest.recommended_next_action_label ?? "Review the latest error and retry." });
  return items;
}

function statusTone(status: DouyinExtensionStatusResponse | null): "good" | "warn" | "danger" | "muted" {
  if (!status) return "muted";
  if (status.status === "connected") return "good";
  if (status.status === "version_mismatch" || status.status === "backend_unreachable_from_extension") return "danger";
  return "warn";
}

function optional(value: string): string | null {
  const trimmed = value.trim();
  return trimmed.length ? trimmed : null;
}

function formatDateTime(value: string | null): string {
  if (!value) return "Never";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
}
