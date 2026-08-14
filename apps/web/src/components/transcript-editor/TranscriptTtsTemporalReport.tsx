"use client";

import { useT } from "../../lib/i18n";
import type { TtsSummaryResponse } from "../../types/tts";

export function TranscriptTtsTemporalReport({ summary }: { summary: TtsSummaryResponse | null }) {
  const t = useT();
  const report = summary?.temporal;
  if (!report?.pipeline_version) return null;

  const ready = report.status === "TTS_TEMPORAL_READY" && report.final_timing_fit_passed === true;
  const performance = report.performance;
  const authority = report.tts_authority;
  const voiceModel = [authority?.provider, authority?.model_id].filter(Boolean).join(" · ") || "—";
  const voiceLine = [authority?.profile_name, voiceModel !== "—" ? voiceModel : null].filter(Boolean).join(" · ") || "—";

  const stats: Array<{ key: string; value: string; label: string; tone?: "exception" }> = [
    {
      key: "groups",
      value: String(report.dialogue_group_count ?? 0),
      label: t("transcriptEditorPage.temporalGroups"),
    },
    {
      key: "elapsed",
      value: performance?.total_elapsed_ms != null ? `${(performance.total_elapsed_ms / 1000).toFixed(1)}s` : "—",
      label: t("transcriptEditorPage.temporalElapsed"),
    },
    {
      key: "gap",
      value: performance?.whole_video_gap_borrowed_ms != null ? `${performance.whole_video_gap_borrowed_ms} ms` : "—",
      label: t("transcriptEditorPage.temporalBorrowedGap"),
    },
  ];

  const exceptionStats = [
    { key: "merged", label: t("transcriptEditorPage.temporalMerged"), count: report.merged_segment_count ?? 0 },
    { key: "corrections", label: t("transcriptEditorPage.temporalCorrections"), count: report.selective_correction_count ?? 0 },
    {
      key: "repairs",
      label: t("transcriptEditorPage.temporalCompactRepairs"),
      count: performance?.whole_video_repaired_segment_count ?? 0,
    },
    {
      key: "refits",
      label: t("transcriptEditorPage.temporalBlockRefits"),
      count: performance?.whole_video_block_refit_count ?? 0,
    },
  ]
    .filter((item) => item.count > 0)
    .map((item) => ({
      key: item.key,
      value: String(item.count),
      label: item.label,
      tone: "exception" as const,
    }));

  const detailRows: Array<{ key: string; label: string; value: string; hideWhenZero?: boolean; numeric?: number }> = [
    {
      key: "strategy",
      label: t("transcriptEditorPage.temporalSynthesisStrategy"),
      value: performance?.synthesis_strategy || "—",
    },
    {
      key: "background",
      label: t("transcriptEditorPage.temporalBackground"),
      value: report.background_audio_preserved ? t("common.yes") : t("common.no"),
    },
    {
      key: "artifacts",
      label: t("transcriptEditorPage.temporalArtifacts"),
      value: String(report.artifact_count ?? 0),
      hideWhenZero: true,
      numeric: report.artifact_count ?? 0,
    },
    {
      key: "probes",
      label: t("transcriptEditorPage.temporalProbes"),
      value: String(report.candidate_probe_count ?? 0),
    },
    {
      key: "fitted",
      label: t("transcriptEditorPage.temporalFittedCache"),
      value: String(performance?.fitted_cache_hit_count ?? 0),
      hideWhenZero: true,
      numeric: performance?.fitted_cache_hit_count ?? 0,
    },
    {
      key: "acoustic",
      label: t("transcriptEditorPage.temporalAcousticCache"),
      value: String(performance?.acoustic_cache_hit_count ?? 0),
      hideWhenZero: true,
      numeric: performance?.acoustic_cache_hit_count ?? 0,
    },
    {
      key: "clips",
      label: t("transcriptEditorPage.temporalProviderClips"),
      value: String(performance?.provider_synthesis_clip_count ?? 0),
    },
    {
      key: "calls",
      label: t("transcriptEditorPage.temporalProviderCalls"),
      value: String(performance?.provider_synthesis_call_count ?? 0),
    },
    {
      key: "blocks",
      label: t("transcriptEditorPage.temporalNarrationBlocks"),
      value: performance?.narration_block_count != null ? String(performance.narration_block_count) : "—",
    },
    {
      key: "single",
      label: t("transcriptEditorPage.temporalSingleRequest"),
      value: performance?.single_request_video ? t("common.yes") : t("common.no"),
    },
    {
      key: "fits",
      label: t("transcriptEditorPage.temporalBlockFits"),
      value: String(performance?.whole_video_block_fit_count ?? 0),
    },
  ].filter((row) => !(row.hideWhenZero && (row.numeric ?? 0) === 0));

  return (
    <section
      aria-label={t("transcriptEditorPage.temporalReportTitle")}
      className={`transcript-temporal-report${ready ? " is-ready" : " is-review"}`}
    >
      <div className="transcript-temporal-report__summary">
        <div className="transcript-temporal-report__head">
          <div>
            <strong>{t("transcriptEditorPage.temporalReportTitle")}</strong>
            <span className="transcript-temporal-report__version">{report.pipeline_version}</span>
            <p className="transcript-temporal-report__voice" title={voiceLine}>
              <strong>{authority?.profile_name || "—"}</strong>
              <em>{voiceModel}</em>
            </p>
          </div>
          <b>{ready ? t("transcriptEditorPage.temporalReady") : t("transcriptEditorPage.temporalReview")}</b>
        </div>
        <ul className="transcript-temporal-report__stats">
          {[...stats, ...exceptionStats].map((stat) => (
            <li className={`transcript-temporal-report__stat${stat.tone === "exception" ? " is-exception" : ""}`} key={stat.key}>
              <strong>{stat.value}</strong>
              <span>{stat.label}</span>
            </li>
          ))}
        </ul>
      </div>
      <details className="transcript-temporal-report__detail">
        <summary>{t("transcriptEditorPage.temporalPipelineDetail")}</summary>
        <ul className="transcript-temporal-report__tiles">
          {detailRows.map((row) => (
            <li className="transcript-temporal-report__tile" key={row.key}>
              <span>{row.label}</span>
              <strong>{row.value}</strong>
            </li>
          ))}
        </ul>
      </details>
    </section>
  );
}
