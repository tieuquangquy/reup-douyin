"use client";

import { useEffect, useMemo, useState, type ReactNode } from "react";
import {
  decideContentClassification,
  fetchContentTopics,
  fetchJob,
  fetchPublicationContentClassification,
  runPublicationContentClassification,
} from "../../lib/api";
import { useT } from "../../lib/i18n";
import { classificationSourceTitle, getClassificationSourcePresentation } from "../../lib/contentClassificationPresentation";
import type { ContentClassification, TopicCategory } from "../../types/content-intelligence";
import type { Job } from "../../types/jobs";
import { AsyncButton } from "../shared/AsyncButton";
import { useNotice } from "../shared/NoticeCenter";

const ACTIVE_JOB_STATUSES = new Set(["QUEUED", "RUNNING", "RETRYABLE"]);

type ClassificationIconKind = "sync" | "check" | "edit" | "close";

function ClassificationIcon({ kind }: { kind: ClassificationIconKind }) {
  const paths: Record<ClassificationIconKind, ReactNode> = {
    sync: <><path d="M20 7v5h-5" /><path d="M4 17v-5h5" /><path d="M6.1 9a7 7 0 0 1 11.8-2L20 9M4 15l2.1 2a7 7 0 0 0 11.8-2" /></>,
    check: <><circle cx="12" cy="12" r="8.5" /><path d="m8.2 12.2 2.5 2.5 5.2-5.4" /></>,
    edit: <><path d="M4 20h4l10.5-10.5a2.1 2.1 0 0 0-3-3L5 17z" /><path d="M13.5 6.5l3 3" /></>,
    close: <><path d="M7 7l10 10" /><path d="M17 7l-10 10" /></>,
  };
  return <svg aria-hidden="true" className="publication-library-icon" fill="none" viewBox="0 0 24 24"><g stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.8">{paths[kind]}</g></svg>;
}

function confidenceTone(confidence: number): string {
  if (confidence >= 0.75) return "high";
  if (confidence >= 0.5) return "medium";
  return "low";
}

function shortVersionLabel(value: string | null | undefined): string {
  const text = String(value || "").trim();
  if (!text) return "";
  return text.split(":")[0];
}

export function PublicationClassificationPanel({ publicationId }: { publicationId: string }) {
  const t = useT();
  const { notify } = useNotice();
  const [topics, setTopics] = useState<TopicCategory[]>([]);
  const [classification, setClassification] = useState<ContentClassification | null>(null);
  const [job, setJob] = useState<Job | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [overrideOpen, setOverrideOpen] = useState(false);
  const [overrideTopicId, setOverrideTopicId] = useState("");
  const [overrideReason, setOverrideReason] = useState("");

  async function load() {
    setLoading(true);
    try {
      const [topicPayload, classificationPayload] = await Promise.all([
        fetchContentTopics(),
        fetchPublicationContentClassification(publicationId),
      ]);
      setTopics(topicPayload.topics);
      setClassification(classificationPayload);
      setOverrideTopicId(classificationPayload?.primary_topic_id ?? "");
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : t("contentClassification.loadError"));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    setClassification(null);
    setJob(null);
    setOverrideOpen(false);
    setOverrideReason("");
    void load();
  }, [publicationId]);

  async function runClassification() {
    setBusy("run");
    setError(null);
    try {
      const payload = await runPublicationContentClassification(publicationId);
      if (payload.classification) {
        setClassification(payload.classification);
        setOverrideTopicId(payload.classification.primary_topic_id ?? "");
        notify({ message: t("contentClassification.reused"), tone: "info" });
      }
      if (payload.job) {
        setJob(payload.job);
        notify({ message: t("contentClassification.queued").replace("{id}", payload.job.id.slice(0, 8)), tone: "success" });
      } else {
        setBusy(null);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : t("contentClassification.runError"));
      setBusy(null);
    }
  }

  useEffect(() => {
    const jobId = job?.id;
    if (!jobId || !ACTIVE_JOB_STATUSES.has(job.status)) return;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | null = null;
    const poll = async () => {
      try {
        const updated = await fetchJob(jobId);
        if (cancelled) return;
        setJob(updated);
        if (updated.status === "COMPLETED") {
          const result = await fetchPublicationContentClassification(publicationId);
          if (cancelled) return;
          setClassification(result);
          setOverrideTopicId(result?.primary_topic_id ?? "");
          setBusy(null);
          notify({ message: t("contentClassification.completed"), tone: "success" });
          return;
        }
        if (["FAILED", "CANCELLED"].includes(updated.status)) {
          setError(updated.error_message || t("contentClassification.failed"));
          setBusy(null);
          return;
        }
        timer = setTimeout(() => void poll(), updated.status === "RETRYABLE" ? 5000 : 1200);
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : t("contentClassification.jobError"));
          timer = setTimeout(() => void poll(), 5000);
        }
      }
    };
    timer = setTimeout(() => void poll(), 600);
    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
  }, [job?.id, job?.status, publicationId]);

  async function approve() {
    if (!classification) return;
    setBusy("approve");
    setError(null);
    try {
      setClassification(await decideContentClassification(classification.id, { decision: "APPROVED" }));
      notify({ message: t("contentClassification.approved"), tone: "success" });
    } catch (err) {
      setError(err instanceof Error ? err.message : t("contentClassification.decisionError"));
    } finally {
      setBusy(null);
    }
  }

  async function saveOverride() {
    if (!classification || !overrideTopicId || !overrideReason.trim()) return;
    setBusy("override");
    setError(null);
    try {
      const updated = await decideContentClassification(classification.id, {
        decision: "OVERRIDDEN",
        primary_topic_id: overrideTopicId,
        reason: overrideReason.trim(),
      });
      setClassification(updated);
      setOverrideOpen(false);
      notify({ message: t("contentClassification.overridden"), tone: "success" });
    } catch (err) {
      setError(err instanceof Error ? err.message : t("contentClassification.decisionError"));
    } finally {
      setBusy(null);
    }
  }

  const evidence = classification?.evidence_json ?? [];
  const secondaryTopics = classification?.secondary_topics_json ?? [];
  const activeTopics = useMemo(() => topics.filter((topic) => topic.is_active), [topics]);
  const jobActive = job != null && ACTIVE_JOB_STATUSES.has(job.status);
  const classifierSource = classification ? getClassificationSourcePresentation(classification) : null;

  return (
    <section className="publication-classification">
      <header>
        <div>
          <strong>{t("contentClassification.title")}</strong>
          <small>{t("contentClassification.hint")}</small>
        </div>
        {classification ? (
          <span className={`publication-classification-status is-${classification.decision_status.toLowerCase()}`}>
            {t(`contentClassification.status.${classification.decision_status}`)}
          </span>
        ) : null}
      </header>
      {error ? <div className="publication-classification-error" role="alert">{error}</div> : null}
      {loading ? (
        <p className="muted">{t("contentClassification.loading")}</p>
      ) : !classification ? (
        <div className="publication-classification-empty">
          <div>
            <strong>{t("contentClassification.noResult")}</strong>
            <small>{t("contentClassification.noResultHint")}</small>
          </div>
          <AsyncButton className="primary" leadingIcon={<ClassificationIcon kind="sync" />} pending={busy === "run"} onClick={() => void runClassification()}>
            {t("contentClassification.run")}
          </AsyncButton>
        </div>
      ) : (
        <>
          <div className="publication-classification-result is-sheet">
            <div>
              <span>{t("contentClassification.primaryTopic")}</span>
              <strong title={classification.primary_topic_name || classification.primary_topic_code || undefined}>{classification.primary_topic_name || classification.primary_topic_code || "—"}</strong>
              <small title={classification.primary_topic_code || undefined}>{classification.primary_topic_code}</small>
            </div>
            <div>
              <span>{t("contentClassification.confidence")}</span>
              <strong className={`is-${confidenceTone(classification.confidence)}`}>{Math.round(classification.confidence * 100)}%</strong>
              <small title={classification.classifier_version || undefined}>{shortVersionLabel(classification.classifier_version)}</small>
            </div>
            <div>
              <span>{t("contentClassification.evidenceSources")}</span>
              <strong>{evidence.length}</strong>
              <small title={classification.taxonomy_version || undefined}>{shortVersionLabel(classification.taxonomy_version)}</small>
            </div>
          </div>
          <div className="publication-classification-insight">
            {classifierSource ? (
              <div className={`publication-classification-runtime is-${classifierSource.kind.toLowerCase()}`} title={classificationSourceTitle(classifierSource)}>
                <span>
                  <i aria-hidden="true" />
                  {t(`classificationSource.${classifierSource.kind}`)}
                </span>
                <div>
                  <strong>
                    {classifierSource.provider}
                    {classifierSource.model ? ` · ${classifierSource.model}` : ""}
                  </strong>
                  <small title={classifierSource.promptVersion || undefined}>
                    {classifierSource.promptVersion
                      ? t("classificationSource.prompt")
                      : t("classificationSource.noExternalPrompt")}
                  </small>
                </div>
              </div>
            ) : null}
            {secondaryTopics.length > 0 ? (
              <div className="publication-classification-secondary">
                <span>{t("contentClassification.secondaryTopics")}</span>
                <div>
                  {secondaryTopics.map((topic, index) => (
                    <em key={String(topic.topic_id || topic.code || index)}>{String(topic.name || topic.code || "")}</em>
                  ))}
                </div>
              </div>
            ) : null}
            <div className="publication-classification-rationale">
              <strong>{t("contentClassification.why")}</strong>
              <small>{classification.rationale || "—"}</small>
              <small>{classifierSource?.networkUsed ? t("contentClassification.aiUsed") : t("contentClassification.localOnly")}</small>
            </div>
          </div>
          <details className="publication-classification-evidence">
            <summary>{t("contentClassification.evidence").replace("{count}", String(evidence.length))}</summary>
            <div>
              {evidence.length === 0 ? (
                <p className="muted">{t("contentClassification.noEvidence")}</p>
              ) : (
                evidence.map((item, index) => (
                  <article key={`${item.source}-${item.source_id || index}`}>
                    <header>
                      <b>{t(`contentClassification.source.${item.source}`)}</b>
                      {item.confidence == null ? null : <span>{Math.round(item.confidence * 100)}%</span>}
                    </header>
                    <p>{item.text}</p>
                    {item.matched_keywords.length > 0 ? (
                      <footer>
                        {item.matched_keywords.map((keyword) => (
                          <em key={keyword}>{keyword.split(":").slice(1).join(":") || keyword}</em>
                        ))}
                      </footer>
                    ) : null}
                  </article>
                ))
              )}
            </div>
          </details>
          {job ? (
            <div className={`publication-classification-job is-${job.status.toLowerCase()}`}>
              <i />
              <div>
                <strong>{t(`contentClassification.jobStatus.${job.status}`)}</strong>
                <small>
                  {t("contentClassification.jobProgress")
                    .replace("{id}", job.id.slice(0, 8))
                    .replace("{progress}", String(job.progress_percent))}
                </small>
              </div>
            </div>
          ) : null}
          {overrideOpen ? (
            <div className="publication-classification-override">
              <label>
                <span>{t("contentClassification.overrideTopic")}</span>
                <select value={overrideTopicId} onChange={(event) => setOverrideTopicId(event.target.value)}>
                  <option value="">{t("contentClassification.selectTopic")}</option>
                  {activeTopics.map((topic) => (
                    <option key={topic.id} value={topic.id}>
                      {topic.name} · {topic.code}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                <span>{t("contentClassification.overrideReason")}</span>
                <textarea maxLength={1000} onChange={(event) => setOverrideReason(event.target.value)} value={overrideReason} />
              </label>
              <footer>
                <button onClick={() => setOverrideOpen(false)} type="button">
                  <ClassificationIcon kind="close" />
                  {t("common.cancel")}
                </button>
                <AsyncButton className="primary" disabled={!overrideTopicId || !overrideReason.trim()} leadingIcon={<ClassificationIcon kind="check" />} pending={busy === "override"} onClick={() => void saveOverride()}>
                  {t("contentClassification.saveOverride")}
                </AsyncButton>
              </footer>
            </div>
          ) : null}
          <footer className="publication-classification-actions">
            <AsyncButton leadingIcon={<ClassificationIcon kind="sync" />} pending={busy === "run" || jobActive} onClick={() => void runClassification()}>
              {t("contentClassification.reclassify")}
            </AsyncButton>
            {classification.decision_status !== "APPROVED" ? (
              <AsyncButton className="primary" disabled={jobActive} leadingIcon={<ClassificationIcon kind="check" />} pending={busy === "approve"} onClick={() => void approve()}>
                {t("contentClassification.approve")}
              </AsyncButton>
            ) : null}
            <button className="publication-classification-override-trigger" disabled={jobActive} onClick={() => setOverrideOpen((current) => !current)} type="button">
              <ClassificationIcon kind="edit" />
              {t("contentClassification.override")}
            </button>
          </footer>
        </>
      )}
    </section>
  );
}
