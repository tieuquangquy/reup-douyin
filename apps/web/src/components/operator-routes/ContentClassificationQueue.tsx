"use client";

import { useEffect, useState } from "react";
import { fetchContentClassificationQueue, runPublicationContentClassification } from "../../lib/api";
import { useT } from "../../lib/i18n";
import { classificationSourceTitle, getClassificationSourcePresentation } from "../../lib/contentClassificationPresentation";
import type { ContentClassificationQueueItem, ContentClassificationQueueResponse } from "../../types/content-intelligence";
import type { PlatformAccount } from "../../types/publish-draft";
import { formatDateTime } from "../ops-console/OpsShared";
import { AsyncButton } from "../shared/AsyncButton";
import { useNotice } from "../shared/NoticeCenter";


const EMPTY_QUEUE: ContentClassificationQueueResponse = {
  items: [],
  total: 0,
  limit: 100,
  offset: 0,
  kpis: {
    total_publications: 0,
    unclassified_count: 0,
    needs_review_count: 0,
    approved_count: 0,
    overridden_count: 0,
    low_confidence_count: 0,
  },
};


export function ContentClassificationQueue({
  accounts,
  onOpenPublication,
}: {
  accounts: PlatformAccount[];
  onOpenPublication: (item: ContentClassificationQueueItem) => Promise<void>;
}) {
  const t = useT();
  const { notify } = useNotice();
  const [queue, setQueue] = useState(EMPTY_QUEUE);
  const [accountFilter, setAccountFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [lowConfidenceOnly, setLowConfidenceOnly] = useState(false);
  const [queryInput, setQueryInput] = useState("");
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function load(showNotice = false) {
    setLoading(true);
    try {
      const payload = await fetchContentClassificationQueue({
        platformAccountId: accountFilter || undefined,
        decisionStatus: statusFilter || undefined,
        lowConfidenceOnly,
        query: query || undefined,
        limit: 100,
      });
      setQueue(payload);
      setError(null);
      if (showNotice) notify({ message: t("classificationQueue.refreshed"), tone: "success" });
    } catch (err) {
      setError(err instanceof Error ? err.message : t("classificationQueue.loadError"));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
    const timer = setInterval(() => void load(), 15_000);
    return () => clearInterval(timer);
  }, [accountFilter, statusFilter, lowConfidenceOnly, query]);

  async function classify(item: ContentClassificationQueueItem) {
    setBusy(item.platform_publication_id);
    setError(null);
    try {
      const result = await runPublicationContentClassification(item.platform_publication_id);
      notify({
        message: result.classification
          ? t("classificationQueue.alreadyCurrent")
          : t("classificationQueue.queued").replace("{id}", result.job?.id.slice(0, 8) ?? "—"),
        tone: result.classification ? "info" : "success",
      });
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : t("classificationQueue.runError"));
    } finally {
      setBusy(null);
    }
  }

  const kpis = queue.kpis;
  return <section className="classification-queue-page">
    {error ? <div className="inline-error" role="alert">{error}</div> : null}
    <section className="classification-queue-kpis"><article><span>{t("classificationQueue.total")}</span><strong>{kpis.total_publications}</strong><small>{t("classificationQueue.totalHint")}</small></article><article><span>{t("classificationQueue.unclassified")}</span><strong>{kpis.unclassified_count}</strong><small>{t("classificationQueue.unclassifiedHint")}</small></article><article className={kpis.needs_review_count ? "is-warning" : ""}><span>{t("classificationQueue.needsReview")}</span><strong>{kpis.needs_review_count}</strong><small>{t("classificationQueue.needsReviewHint")}</small></article><article><span>{t("classificationQueue.approved")}</span><strong>{kpis.approved_count + kpis.overridden_count}</strong><small>{t("classificationQueue.approvedHint").replace("{count}", String(kpis.overridden_count))}</small></article><article className={kpis.low_confidence_count ? "is-warning" : ""}><span>{t("classificationQueue.lowConfidence")}</span><strong>{kpis.low_confidence_count}</strong><small>{t("classificationQueue.lowConfidenceHint")}</small></article></section>
    <section className="classification-queue-toolbar"><label><span>{t("classificationQueue.page")}</span><select onChange={(event) => setAccountFilter(event.target.value)} value={accountFilter}><option value="">{t("classificationQueue.allPages")}</option>{accounts.map((account) => <option key={account.id} value={account.id}>{account.display_name}</option>)}</select></label><label><span>{t("classificationQueue.status")}</span><select onChange={(event) => setStatusFilter(event.target.value)} value={statusFilter}><option value="">{t("classificationQueue.allStatuses")}</option>{["UNCLASSIFIED", "NEEDS_REVIEW", "APPROVED", "OVERRIDDEN"].map((value) => <option key={value} value={value}>{t(`classificationQueue.statusValue.${value}`)}</option>)}</select></label><label className="classification-queue-low-confidence"><input checked={lowConfidenceOnly} onChange={(event) => setLowConfidenceOnly(event.target.checked)} type="checkbox" /><span>{t("classificationQueue.onlyLowConfidence")}</span></label><form onSubmit={(event) => { event.preventDefault(); setQuery(queryInput.trim()); }}><label><span>{t("classificationQueue.search")}</span><input onChange={(event) => setQueryInput(event.target.value)} placeholder={t("classificationQueue.searchPlaceholder")} value={queryInput} /></label><AsyncButton pending={loading} type="submit">{t("classificationQueue.apply")}</AsyncButton></form><AsyncButton pending={loading} onClick={() => void load(true)}>{t("common.refresh")}</AsyncButton></section>
    <section className="classification-queue-table-wrap"><header><div><strong>{t("classificationQueue.title")}</strong><small>{t("classificationQueue.results").replace("{count}", String(queue.total))}</small></div></header>{loading && queue.items.length === 0 ? <p className="muted">{t("classificationQueue.loading")}</p> : queue.items.length === 0 ? <p className="muted">{t("classificationQueue.empty")}</p> : <table className="classification-queue-table"><thead><tr><th>{t("classificationQueue.reel")}</th><th>{t("classificationQueue.page")}</th><th>{t("classificationQueue.result")}</th><th>{t("contentClassification.confidence")}</th><th>{t("classificationQueue.evidence")}</th><th>{t("classificationQueue.job")}</th><th>{t("classificationQueue.actions")}</th></tr></thead><tbody>{queue.items.map((item) => {
      const classification = item.classification;
      const status = classification?.decision_status ?? "UNCLASSIFIED";
      const source = classification ? getClassificationSourcePresentation(classification) : null;
      const jobActive = item.latest_job && ["QUEUED", "RUNNING", "RETRYABLE"].includes(item.latest_job.status);
      return <tr key={item.platform_publication_id}><td><div className="classification-queue-reel">{item.thumbnail_url ? <img alt="" src={item.thumbnail_url} /> : <span>Reel</span>}<div><b>{item.caption || item.external_reel_id || "Reel"}</b><small>{item.published_at ? formatDateTime(item.published_at) : item.external_reel_id}</small></div></div></td><td>{item.page_display_name}</td><td><span className={`classification-queue-status is-${status.toLowerCase()}`}>{t(`classificationQueue.statusValue.${status}`)}</span>{classification?.primary_topic_name ? <small>{classification.primary_topic_name}</small> : null}{source ? <span className={`classification-source-badge is-${source.kind.toLowerCase()}`} title={classificationSourceTitle(source)}><i aria-hidden="true" />{t(`classificationSource.${source.kind}`)}{source.kind === "AI" ? ` · ${source.provider}` : ""}</span> : null}</td><td>{classification ? <b className={`classification-confidence is-${classification.confidence >= .75 ? "high" : classification.confidence >= .5 ? "medium" : "low"}`}>{Math.round(classification.confidence * 100)}%</b> : "—"}</td><td>{classification?.evidence_json?.length ?? 0}</td><td>{item.latest_job ? <div className={`classification-queue-job is-${item.latest_job.status.toLowerCase()}`}><i /><span>{item.latest_job.status} · {item.latest_job.progress_percent}%</span></div> : "—"}</td><td><div className="classification-queue-actions"><AsyncButton disabled={Boolean(jobActive)} pending={busy === item.platform_publication_id} onClick={() => void classify(item)}>{classification ? t("contentClassification.reclassify") : t("contentClassification.run")}</AsyncButton><button onClick={() => void onOpenPublication(item)} type="button">{classification ? t("classificationQueue.review") : t("classificationQueue.open")}</button></div></td></tr>;
    })}</tbody></table>}</section>
  </section>;
}
