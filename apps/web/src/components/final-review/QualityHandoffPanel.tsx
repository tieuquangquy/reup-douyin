"use client";

import { useEffect, useMemo, useState } from "react";
import {
  approveQualityFinalHandoff,
  approveQualityMetadata,
  approveQualityRights,
  fetchLocalizationArtifactObjectUrl,
  fetchQualityHandoff,
  finalizeQualityManualExport
} from "../../lib/api";
import type { QualityHandoffSummary } from "../../types/quality-handoff";
import { AsyncButton } from "../shared/AsyncButton";

export function QualityHandoffPanel({
  sourceVideoId,
  publishReady,
  defaultTitle = "",
  defaultCaption = ""
}: {
  sourceVideoId: string;
  publishReady: boolean;
  defaultTitle?: string;
  defaultCaption?: string;
}) {
  const [summary, setSummary] = useState<QualityHandoffSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [pending, setPending] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [title, setTitle] = useState(defaultTitle);
  const [caption, setCaption] = useState(defaultCaption);
  const [cta, setCta] = useState("");
  const [hashtags, setHashtags] = useState("");
  const [rights, setRights] = useState({ source: false, music: false, responsibility: false });

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    fetchQualityHandoff(sourceVideoId)
      .then((value) => {
        if (cancelled) return;
        setSummary(value);
        const draft = value.publish_draft;
        if (draft) {
          setTitle(draft.title || defaultTitle);
          setCaption(draft.caption || defaultCaption);
          setCta(draft.cta_text || "");
          setHashtags(
            (draft.hashtags || [])
              .map((row) => (typeof row === "string" ? row : row.tag || ""))
              .filter(Boolean)
              .join(" ")
          );
        }
      })
      .catch((reason) => {
        if (!cancelled) setError(reason instanceof Error ? reason.message : String(reason));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [sourceVideoId, defaultTitle, defaultCaption]);

  const metadataApproved = summary?.metadata_status === "METADATA_APPROVED";
  const rightsApproved = summary?.rights_status === "SOURCE_RIGHTS_AND_MUSIC_APPROVED";
  const exportReady = summary?.manual_export_status === "MANUAL_EXPORT_READY";
  const allRights = rights.source && rights.music && rights.responsibility;
  const gates = useMemo(
    () => [
      ["Final", summary?.final_approval_status || "NOT_READY"],
      ["Metadata", summary?.metadata_status || "NOT_READY"],
      ["Rights & music", summary?.rights_status || "NOT_READY"],
      ["Manual export", summary?.manual_export_status || "NOT_READY"]
    ],
    [summary]
  );

  async function run(key: string, action: () => Promise<QualityHandoffSummary>) {
    setPending(key);
    setError(null);
    try {
      setSummary(await action());
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setPending(null);
    }
  }

  async function downloadArchive() {
    if (!summary?.archive_path) return;
    setPending("download");
    setError(null);
    try {
      const url = await fetchLocalizationArtifactObjectUrl(sourceVideoId, summary.archive_path);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = summary.archive_path.split("/").pop() || "manual-export.zip";
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      window.setTimeout(() => URL.revokeObjectURL(url), 30_000);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setPending(null);
    }
  }

  if (loading) {
    return <section className="final-panel fr-info"><p>Đang tải handoff…</p></section>;
  }

  return (
    <section className="final-panel fr-info" aria-label="Quality manual export handoff">
      <div className="fr-info__head">
        <h2>Export thủ công</h2>
        <span className="pill">{summary?.handoff_status || "NOT_READY"}</span>
      </div>
      <p className="fr-info__hint">
        Luồng hash-bound; không gọi API đăng bài và không tự cấp quyền xuất bản.
      </p>
      <dl className="metadata-list fr-info__list">
        {gates.map(([label, value]) => (
          <div key={label}><dt>{label}</dt><dd>{value}</dd></div>
        ))}
      </dl>
      {error ? <div className="inline-error fr-inline-error">{error}</div> : null}

      {summary?.final_approval_status !== "FINAL_APPROVED" ? (
        <AsyncButton
          pending={pending === "final"}
          onClick={() => void run("final", () => approveQualityFinalHandoff(sourceVideoId))}
        >
          Ghi nhận FINAL_APPROVED
        </AsyncButton>
      ) : null}

      {summary?.final_approval_status === "FINAL_APPROVED" && !metadataApproved ? (
        <div className="fr-rail__stack">
          <label>Tiêu đề<input value={title} onChange={(event) => setTitle(event.target.value)} /></label>
          <label>Caption<textarea value={caption} onChange={(event) => setCaption(event.target.value)} /></label>
          <label>CTA<input value={cta} onChange={(event) => setCta(event.target.value)} /></label>
          <label>Hashtag<input value={hashtags} onChange={(event) => setHashtags(event.target.value)} placeholder="#lamdep #review" /></label>
          <AsyncButton
            pending={pending === "metadata"}
            disabled={!title.trim()}
            onClick={() => void run("metadata", () => approveQualityMetadata(sourceVideoId, {
              title: title.trim(),
              caption: caption.trim(),
              cta_text: cta.trim(),
              hashtags: hashtags.split(/[\s,]+/).map((tag) => tag.replace(/^#/, "").trim()).filter(Boolean)
            }))}
          >
            Lưu và duyệt metadata
          </AsyncButton>
        </div>
      ) : null}

      {metadataApproved && !rightsApproved ? (
        <div className="fr-rail__stack">
          <label><input type="checkbox" checked={rights.source} onChange={(event) => setRights((value) => ({ ...value, source: event.target.checked }))} /> Tôi có quyền tái sử dụng video nguồn.</label>
          <label><input type="checkbox" checked={rights.music} onChange={(event) => setRights((value) => ({ ...value, music: event.target.checked }))} /> Tôi có quyền giữ và sử dụng nhạc nền trên nền tảng đích.</label>
          <label><input type="checkbox" checked={rights.responsibility} onChange={(event) => setRights((value) => ({ ...value, responsibility: event.target.checked }))} /> Tôi chịu trách nhiệm về xác nhận bản quyền này.</label>
          <AsyncButton
            pending={pending === "rights"}
            disabled={!allRights}
            onClick={() => void run("rights", () => approveQualityRights(sourceVideoId, {
              source_video_reuse_authorized: rights.source,
              retained_music_use_authorized: rights.music,
              operator_accepts_responsibility: rights.responsibility
            }))}
          >
            Duyệt source rights & music
          </AsyncButton>
        </div>
      ) : null}

      {rightsApproved && !exportReady ? (
        <AsyncButton
          pending={pending === "export"}
          disabled={!publishReady}
          title={publishReady ? undefined : "Hãy hoàn tất checklist và Mark publish-ready trước"}
          onClick={() => void run("export", () => finalizeQualityManualExport(sourceVideoId))}
        >
          Tạo gói MANUAL_EXPORT_ONLY
        </AsyncButton>
      ) : null}

      {exportReady ? (
        <div className="fr-rail__stack">
          <span className="pill">MANUAL_EXPORT_READY</span>
          <AsyncButton pending={pending === "download"} onClick={() => void downloadArchive()}>
            Tải gói ZIP
          </AsyncButton>
          {summary?.export_package_id ? <small>ExportPackage: {summary.export_package_id}</small> : null}
          {summary?.publish_handoff_id ? <small>PublishHandoff: {summary.publish_handoff_id}</small> : null}
        </div>
      ) : null}
    </section>
  );
}
