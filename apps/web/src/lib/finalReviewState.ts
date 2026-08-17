import type {
  ChecklistState,
  CompareMode,
  MediaAssetManifestEntry,
  RenderOutput,
  SourceVideoAssetManifest
} from "../types/final-review";

export const DEFAULT_FINAL_REVIEW_CHECKLIST: ChecklistState = {
  narration_clear: false,
  subtitle_ok: false,
  timing_ok: false,
  render_clean: false,
  playable: false,
  warnings_checked: false
};

/** Prep hub before first render: OCR/clean → start render → compare. */
export type FinalReviewPrepFocus = "ocr" | "render";

/**
 * True when the operator has already completed at least one OCR/clean run.
 * Empty API summary shells (always returned even before first analyze) must stay false.
 */
export function hasFinalReviewOcrRun(
  summary: {
    cleaned_video_asset_id?: string | null;
    ocr_events_asset_id?: string | null;
    pipeline_version?: string | null;
    text_object_count?: number | null;
    frame_detection_count?: number | null;
    hardsub_events?: unknown[] | null;
    warnings?: string[] | null;
  } | null
): boolean {
  if (!summary) return false;
  if (summary.cleaned_video_asset_id) return true;
  if (summary.ocr_events_asset_id) return true;
  if (summary.pipeline_version) return true;
  if ((summary.text_object_count ?? 0) > 0) return true;
  if ((summary.frame_detection_count ?? 0) > 0) return true;
  if ((summary.hardsub_events?.length ?? 0) > 0) return true;
  const warnings = summary.warnings ?? [];
  return warnings.includes("no_hardsub_detected") || warnings.includes("clean_skipped_no_hardsub");
}

/**
 * The OCR job has finished, but its artifact is intentionally blocked at the
 * operator checkpoint.  This must not be treated as an in-flight job and must
 * not expose the normal Analyze action, otherwise a second run can supersede
 * the review authority of the current artifact.
 */
export function isFinalReviewOcrReviewPending(
  summary: {
    workflow_stage?: string | null;
    review_required?: number | null;
    review_objects?: unknown[] | null;
  } | null
): boolean {
  if (!summary || summary.workflow_stage !== "WAITING_OCR_REVIEW") return false;
  return (summary.review_required ?? 0) > 0 || (summary.review_objects?.length ?? 0) > 0;
}

export type FinalReviewOcrCheckpointMetrics = {
  total: number;
  automatic: number;
  manual: number;
};

function toNonNegativeCount(value: number | null | undefined): number {
  return typeof value === "number" && Number.isFinite(value)
    ? Math.max(0, Math.round(value))
    : 0;
}

/**
 * Normalize the Phase 2 handoff counters shown at the operator checkpoint.
 * The review array is retained as a fallback because older artifacts may not
 * persist review_required, while total must never be lower than the manual set.
 */
export function resolveFinalReviewOcrCheckpointMetrics(
  summary: {
    phase2_content_object_count?: number | null;
    text_object_count?: number | null;
    review_required?: number | null;
    review_objects?: unknown[] | null;
  } | null
): FinalReviewOcrCheckpointMetrics {
  const persistedManual = toNonNegativeCount(summary?.review_required);
  const listedManual = summary?.review_objects?.length ?? 0;
  const manual = Math.max(persistedManual, listedManual);
  const persistedTotal = toNonNegativeCount(
    summary?.phase2_content_object_count ?? summary?.text_object_count
  );
  const total = Math.max(persistedTotal, manual);
  return {
    total,
    automatic: Math.max(0, total - manual),
    manual
  };
}

/** OCR geometry is reusable; only approved Vietnamese dialogue authority is missing. */
export function isFinalReviewDialogueTranslationApprovalPending(
  summary: {
    workflow_stage?: string | null;
    requires_dialogue_translation_approval?: boolean;
    dialogue_translation_blocked_count?: number | null;
  } | null
): boolean {
  if (!summary) return false;
  return (
    summary.workflow_stage === "WAITING_DIALOGUE_TRANSLATION_APPROVAL" ||
    (summary.requires_dialogue_translation_approval === true &&
      (summary.dialogue_translation_blocked_count ?? 0) > 0)
  );
}

/**
 * A durable quality artifact at or beyond visual preview supersedes any
 * terminal error banner left in the mounted page by an older OCR/preview job.
 * Job history remains available in Ops; Final Review must present the current
 * artifact authority instead of a stale failure from a prior attempt.
 */
export function hasCurrentQualityVisualAuthority(
  summary: {
    workflow_version?: string | null;
    workflow_stage?: string | null;
  } | null
): boolean {
  if (summary?.workflow_version !== "QUALITY_LOCALIZATION_V24_1") return false;
  return new Set([
    "WAITING_VISUAL_REVIEW",
    "VISUAL_APPROVED",
    "WAITING_AUDIO_REVIEW",
    "AUDIO_APPROVED",
    "FINAL_READY"
  ]).has(summary.workflow_stage ?? "");
}

/**
 * OCR prep is complete only when cleaned video exists, or OCR explicitly skipped clean
 * (no hard-sub / clean skipped). Orphan OCR events alone must not unlock Start render.
 */
export function isFinalReviewOcrPrepComplete(
  summary: {
    cleaned_video_asset_id?: string | null;
    ocr_events_asset_id?: string | null;
    clean_produced?: boolean;
    warnings?: string[] | null;
    workflow_version?: string | null;
    workflow_stage?: string | null;
    can_render_final?: boolean;
    review_required?: number | null;
    review_objects?: unknown[] | null;
  } | null
): boolean {
  if (!summary) return false;
  if (summary.workflow_version === "QUALITY_LOCALIZATION_V24_1") {
    return (
      (summary.workflow_stage === "AUDIO_APPROVED" || summary.workflow_stage === "FINAL_READY") &&
      summary.can_render_final === true
    );
  }
  if (summary.cleaned_video_asset_id) return true;
  const warnings = summary.warnings ?? [];
  return warnings.includes("no_hardsub_detected") || warnings.includes("clean_skipped_no_hardsub");
}

/** OCR data authority is complete before the later Visual Clean/audio gates. */
export function isFinalReviewOcrAnalysisComplete(
  summary: Parameters<typeof isFinalReviewOcrPrepComplete>[0]
): boolean {
  if (!summary) return false;
  if (summary.workflow_version === "QUALITY_LOCALIZATION_V24_1") {
    return Boolean(
      summary.workflow_stage &&
      summary.workflow_stage !== "NOT_STARTED" &&
      summary.workflow_stage !== "WAITING_OCR_REVIEW"
    );
  }
  return Boolean(
    summary.ocr_events_asset_id ||
    summary.cleaned_video_asset_id ||
    (summary.warnings ?? []).includes("no_hardsub_detected") ||
    (summary.warnings ?? []).includes("clean_skipped_no_hardsub")
  );
}

export function resolveFinalReviewPrepFocus(
  summary: Parameters<typeof isFinalReviewOcrPrepComplete>[0]
): FinalReviewPrepFocus {
  return isFinalReviewOcrPrepComplete(summary) ? "render" : "ocr";
}

/**
 * Compare/review workspace needs a render the operator can inspect or that is still in flight.
 * FAILED / ARCHIVED / PLANNED shells (e.g. missing render-prep) stay on prep so Start render remains available after refresh.
 */
export function isReviewableFinalRender(render: RenderOutput | null | undefined): boolean {
  if (!render) return false;
  return (
    render.status === "READY_FOR_REVIEW" ||
    render.status === "APPROVED" ||
    render.status === "RENDERING"
  );
}

export function resolveFinalReviewWorkspaceRender(
  latest: RenderOutput | null | undefined
): RenderOutput | null {
  return isReviewableFinalRender(latest) ? latest! : null;
}

/** Strip `error_code: ` prefix from persisted render failure messages for operator copy. */
export function formatFinalReviewFailedRenderDetail(errorMessage: string | null | undefined): string | null {
  const raw = (errorMessage ?? "").trim();
  if (!raw) return null;
  const stripped = raw.replace(/^[a-z][a-z0-9_]*:\s*/i, "").trim();
  return stripped || raw;
}

export type ParsedFinalReviewActionStatus = {
  title: string | null;
  detail: string;
  flags: string[];
};

const EXCEPTION_SEGMENT = /^[A-Z][A-Za-z0-9_]*(Error|Exception)$/;
const SNAKE_ERROR_CODE = /^[a-z][a-z0-9_]+$/;
const PIPELINE_WRAPPER = /(?:preflight|execution|pipeline)\s+failed$/i;
const TRAILING_FLAG_BLOCK = /\[([^\]]+)\]\s*\.?$/;

function extractActionStatusFlags(message: string): { text: string; flags: string[] } {
  const match = message.match(TRAILING_FLAG_BLOCK);
  if (!match || match.index === undefined) return { text: message, flags: [] };
  const flags = match[1]
    .split(/\s*[·•|,;]\s*/)
    .map((flag) => flag.trim())
    .filter(Boolean);
  const text = message.slice(0, match.index).trim().replace(/[.:]\s*$/, "");
  return { text, flags };
}

function isExceptionNoise(part: string): boolean {
  if (EXCEPTION_SEGMENT.test(part)) return true;
  if (SNAKE_ERROR_CODE.test(part) && part.includes("_")) return true;
  if (PIPELINE_WRAPPER.test(part)) return true;
  return false;
}

/**
 * Split an operator status dump into title, human reason, and trailing recovery flags.
 * Backend nested chains stay the authority; the UI only hides class/code wrappers.
 */
export function parseFinalReviewActionStatus(
  phase: "queued" | "running" | "success" | "warning" | "error",
  message: string
): ParsedFinalReviewActionStatus {
  const trimmed = message.trim();
  const { text, flags } = extractActionStatusFlags(trimmed);
  if (phase !== "error") {
    return { title: null, detail: trimmed, flags: [] };
  }
  const parts = text
    .split(/:\s+/)
    .map((part) => part.trim())
    .filter(Boolean);
  if (parts.length <= 1) {
    return { title: null, detail: text || trimmed, flags };
  }
  const title = parts[0] ?? null;
  const human = parts.slice(1).filter((part) => !isExceptionNoise(part));
  const detail = (human.at(-1) ?? parts.at(-1) ?? text).replace(/[.:]\s*$/, "");
  return { title, detail, flags };
}

/** Success/warning toasts may fade; errors stay until the operator closes them. */
export function shouldAutoDismissFinalReviewActionStatus(
  phase: "queued" | "running" | "success" | "warning" | "error"
): boolean {
  return phase === "success" || phase === "warning";
}

export type FinalReviewPrepStepProgress = {
  clean: number;
  render: number;
  compare: number;
};

function clampInFlightPercent(raw: number | null | undefined, fallback = 8): number {
  if (typeof raw !== "number" || !Number.isFinite(raw)) return fallback;
  return Math.max(1, Math.min(99, Math.round(raw)));
}

/** Percent fill for prep step cards (Clean → Render → Compare). Compare stays 0 until a render exists. */
export function resolveFinalReviewPrepStepProgress(input: {
  ocrSummary: Parameters<typeof isFinalReviewOcrPrepComplete>[0];
  ocrBusy?: boolean;
  startRenderPending?: boolean;
  /** Live ANALYZE_OCR job.progress_percent while Clean is in flight. */
  ocrProgressPercent?: number | null;
  /** Live RENDER_FINAL job.progress_percent while Render is in flight. */
  renderProgressPercent?: number | null;
}): FinalReviewPrepStepProgress {
  const complete = isFinalReviewOcrPrepComplete(input.ocrSummary);
  let clean = 0;
  if (input.ocrBusy) clean = clampInFlightPercent(input.ocrProgressPercent);
  else if (complete) clean = 100;
  else if (typeof input.ocrProgressPercent === "number") {
    // Keep last live job % across UI watch-pause (ocrBusy false) — do not snap to idle 0%.
    clean = clampInFlightPercent(input.ocrProgressPercent);
  } else if (isFinalReviewDialogueTranslationApprovalPending(input.ocrSummary)) {
    // OCR geometry is done; operator gate owns the remaining Clean work.
    clean = 72;
  }

  let render = 0;
  if (input.startRenderPending) render = clampInFlightPercent(input.renderProgressPercent);
  else if (typeof input.renderProgressPercent === "number") {
    // Keep last live job % across UI watch-pause (pending false) — do not snap to 0%.
    render = clampInFlightPercent(input.renderProgressPercent);
  }

  return { clean, render, compare: 0 };
}

export type FinalReviewPrepBriefing = {
  phase: "clean" | "render";
  sourceLabel: string;
  caption: string | null;
  durationSeconds: number | null;
  ocrStatus: "idle" | "running" | "review" | "partial" | "ready";
  renderStatus: "none" | "running";
};

/** Operator-facing prep context derived from manifest + OCR authority (no extra network). */
export function resolveFinalReviewPrepBriefing(input: {
  sourceVideoId: string;
  manifest: {
    source_video?: {
      caption?: string | null;
      duration_seconds?: number | null;
      external_id?: string | null;
      source_video_external_id?: string | null;
    } | null;
  } | null;
  ocrSummary: Parameters<typeof isFinalReviewOcrPrepComplete>[0];
  ocrBusy?: boolean;
  startRenderPending?: boolean;
  prepFocus: FinalReviewPrepFocus;
}): FinalReviewPrepBriefing {
  const source = input.manifest?.source_video ?? null;
  const caption = typeof source?.caption === "string" && source.caption.trim() ? source.caption.trim() : null;
  const externalId =
    (typeof source?.external_id === "string" && source.external_id.trim()
      ? source.external_id.trim()
      : null) ??
    (typeof source?.source_video_external_id === "string" && source.source_video_external_id.trim()
      ? source.source_video_external_id.trim()
      : null);
  const shortId =
    input.sourceVideoId.length > 12 ? `${input.sourceVideoId.slice(0, 8)}…` : input.sourceVideoId;
  const sourceLabel = externalId ?? shortId;
  const durationSeconds =
    typeof source?.duration_seconds === "number" && Number.isFinite(source.duration_seconds)
      ? source.duration_seconds
      : null;

  let ocrStatus: FinalReviewPrepBriefing["ocrStatus"] = "idle";
  if (input.ocrBusy) ocrStatus = "running";
  else if (isFinalReviewOcrReviewPending(input.ocrSummary)) ocrStatus = "review";
  else if (isFinalReviewOcrAnalysisComplete(input.ocrSummary)) ocrStatus = "ready";
  else if (input.ocrSummary) ocrStatus = "partial";

  return {
    phase: input.prepFocus === "render" ? "render" : "clean",
    sourceLabel,
    caption,
    durationSeconds,
    ocrStatus,
    renderStatus: input.startRenderPending ? "running" : "none"
  };
}

export function getRenderWarnings(render: RenderOutput | null): string[] {
  if (!render) return [];
  const warningSummary = render.warning_summary_json ?? {};
  const metadata = render.metadata_json ?? {};
  const manifest = asRecord(metadata.manifest);
  const manifestWarnings = toStringArray(manifest?.warnings);
  const summaryWarnings = toStringArray(warningSummary.warnings);
  return [...summaryWarnings, ...manifestWarnings].filter((warning, index, all) => all.indexOf(warning) === index);
}

export function getFinalReviewMetadata(render: RenderOutput | null): Record<string, unknown> {
  return asRecord(render?.metadata_json?.final_review) ?? {};
}

export function isPublishReady(render: RenderOutput | null): boolean {
  const finalReview = getFinalReviewMetadata(render);
  return typeof finalReview.publish_ready_at === "string" && finalReview.publish_ready_at.length > 0;
}

export function isApproved(render: RenderOutput | null): boolean {
  return render?.status === "APPROVED";
}

export function findCurrentSourceVideoAsset(manifest: SourceVideoAssetManifest | null): MediaAssetManifestEntry | null {
  const assets = manifest?.assets ?? [];
  return (
    assets.find((asset) => asset.asset_type === "SOURCE_VIDEO_RAW" && asset.is_current !== false) ??
    assets.find((asset) => asset.asset_type === "SOURCE_VIDEO" && asset.is_current !== false) ??
    null
  );
}

export function buildOriginalPreviewUrl(
  manifest: SourceVideoAssetManifest | null,
  mediaAssetContentUrl: (assetId: string) => string
): string | null {
  const rawAsset = findCurrentSourceVideoAsset(manifest);
  if (rawAsset?.id) return mediaAssetContentUrl(rawAsset.id);
  return manifest?.source_video?.source_url ?? null;
}

export function nextCompareMode(mode: CompareMode): CompareMode {
  if (mode === "side_by_side") return "final_only";
  if (mode === "final_only") return "original_only";
  return "side_by_side";
}

export function checklistComplete(checklist: ChecklistState): boolean {
  return Object.values(checklist).every(Boolean);
}

export function formatRenderDuration(seconds: number | null): string {
  if (seconds == null) return "—";
  const wholeSeconds = Math.max(0, Math.round(seconds));
  const minutes = Math.floor(wholeSeconds / 60);
  const rest = wholeSeconds % 60;
  return `${minutes}:${rest.toString().padStart(2, "0")}`;
}

export type RenderTechSpecs = {
  width: number | null;
  height: number | null;
  fps: number | null;
  duration_seconds: number | null;
  video_codec: string | null;
  audio_codec: string | null;
  output_format: string | null;
  audio_strategy: string | null;
  subtitle_burned: boolean;
  render_version: string | null;
  status: string;
  size_bytes: number | null;
  job_id: string | null;
  started_at: string | null;
  finished_at: string | null;
  approved_at: string | null;
  publish_ready_at: string | null;
};

/** Prefer render columns; fall back to persisted manifest probe / source duration. */
export function resolveRenderTechSpecs(
  render: RenderOutput,
  manifest: SourceVideoAssetManifest | null = null
): RenderTechSpecs {
  const meta = asRecord(render.metadata_json) ?? {};
  const manifestRecord = asRecord(meta.manifest) ?? {};
  const probe = asRecord(manifestRecord.probe) ?? {};
  const outputProbe = asRecord(probe.output) ?? {};
  const inputProbe = asRecord(probe.input) ?? {};
  const outputAsset = asRecord(manifestRecord.output) ?? {};
  const finalReview = asRecord(meta.final_review) ?? {};

  const width = render.width ?? asPositiveInt(outputProbe.width) ?? asPositiveInt(inputProbe.width);
  const height = render.height ?? asPositiveInt(outputProbe.height) ?? asPositiveInt(inputProbe.height);
  const fps = render.fps ?? asPositiveNumber(outputProbe.fps) ?? asPositiveNumber(inputProbe.fps);
  const duration_seconds =
    render.duration_seconds ??
    asPositiveNumber(outputProbe.duration_seconds) ??
    asPositiveNumber(inputProbe.duration_seconds) ??
    asPositiveNumber(manifest?.source_video?.duration_seconds);

  const linkedAsset =
    (manifest?.assets ?? []).find((asset) => asset.id === render.media_asset_id) ??
    (manifest?.assets ?? []).find((asset) => asset.asset_type === "FINAL_RENDER_VIDEO");

  const size_bytes =
    asPositiveInt(render.size_bytes) ??
    asPositiveInt(outputAsset.size_bytes) ??
    asPositiveInt(meta.size_bytes) ??
    asPositiveInt(linkedAsset?.size_bytes);

  const job_id =
    render.created_by_job_id ??
    asNonEmptyString(meta.created_by_job_id) ??
    asNonEmptyString(manifestRecord.job_id) ??
    asNonEmptyString(linkedAsset?.created_by_job_id) ??
    asNonEmptyString(asRecord(linkedAsset?.metadata_json)?.created_by_job_id);

  return {
    width,
    height,
    fps,
    duration_seconds,
    video_codec: render.video_codec ?? asNonEmptyString(outputProbe.video_codec),
    audio_codec: render.audio_codec ?? asNonEmptyString(outputProbe.audio_codec),
    output_format: render.output_format,
    audio_strategy: render.audio_strategy,
    subtitle_burned: Boolean(render.subtitle_burned),
    render_version: render.render_version ?? `v${render.version}`,
    status: render.status,
    size_bytes,
    job_id,
    started_at: render.started_at,
    finished_at: render.finished_at,
    approved_at: asNonEmptyString(finalReview.approved_at),
    publish_ready_at: asNonEmptyString(finalReview.publish_ready_at)
  };
}

export function formatResolution(width: number | null, height: number | null): string | null {
  if (width == null || height == null) return null;
  return `${width}×${height}`;
}

export function formatFps(fps: number | null): string | null {
  if (fps == null) return null;
  if (Number.isInteger(fps)) return String(fps);
  return String(Math.round(fps * 100) / 100);
}

export function formatBytes(sizeBytes: number | null): string | null {
  if (sizeBytes == null || sizeBytes <= 0) return null;
  if (sizeBytes < 1024) return `${sizeBytes} B`;
  if (sizeBytes < 1024 * 1024) return `${(sizeBytes / 1024).toFixed(1)} KB`;
  return `${(sizeBytes / (1024 * 1024)).toFixed(1)} MB`;
}

export type FinalReviewReadinessTone = "good" | "warn" | "bad" | "muted";

export type FinalReviewReadinessChip = {
  id: "checklist" | "warnings" | "risk" | "approved" | "publish_ready";
  tone: FinalReviewReadinessTone;
  done: boolean;
};

export type FinalReviewReadinessBlocker =
  | "checklist"
  | "approve"
  | "risk"
  | "risk_decision";

export type FinalReviewReadiness = {
  checklistOk: boolean;
  checklistCount: number;
  checklistTotal: number;
  warningCount: number;
  riskScanned: boolean;
  riskOk: boolean;
  riskNeedsDecision: boolean;
  approved: boolean;
  publishReady: boolean;
  blockers: FinalReviewReadinessBlocker[];
  chips: FinalReviewReadinessChip[];
};

/** Workspace readiness strip authority: checklist + render + optional risk gate. */
export function resolveFinalReviewReadiness(input: {
  checklist: ChecklistState;
  render: RenderOutput;
  riskSummary?: {
    gate?: {
      can_continue?: boolean;
      requires_operator_decision?: boolean;
    } | null;
    latest_decision?: unknown;
  } | null;
}): FinalReviewReadiness {
  const checklistTotal = Object.keys(DEFAULT_FINAL_REVIEW_CHECKLIST).length;
  const checklistCount = Object.values(input.checklist).filter(Boolean).length;
  const checklistOk = checklistComplete(input.checklist);
  const warningCount = getRenderWarnings(input.render).length;
  const approved = isApproved(input.render);
  const publishReady = isPublishReady(input.render);
  const riskScanned = Boolean(input.riskSummary);
  const gate = input.riskSummary?.gate ?? null;
  const riskOk = !riskScanned || gate?.can_continue !== false;
  const riskNeedsDecision = Boolean(
    riskScanned && gate?.requires_operator_decision && !input.riskSummary?.latest_decision
  );

  const blockers: FinalReviewReadinessBlocker[] = [];
  if (!publishReady) {
    if (!checklistOk) blockers.push("checklist");
    if (!approved) blockers.push("approve");
    if (!riskOk) blockers.push("risk");
    else if (riskNeedsDecision) blockers.push("risk_decision");
  }

  const chips: FinalReviewReadinessChip[] = [
    {
      id: "checklist",
      done: checklistOk,
      tone: checklistOk ? "good" : "warn"
    },
    {
      id: "warnings",
      done: warningCount === 0,
      tone: warningCount === 0 ? "good" : "warn"
    },
    {
      id: "risk",
      done: riskOk && !riskNeedsDecision,
      tone: !riskScanned ? "muted" : !riskOk || riskNeedsDecision ? "bad" : "good"
    },
    {
      id: "approved",
      done: approved,
      tone: approved ? "good" : "warn"
    },
    {
      id: "publish_ready",
      done: publishReady,
      tone: publishReady ? "good" : "muted"
    }
  ];

  return {
    checklistOk,
    checklistCount,
    checklistTotal,
    warningCount,
    riskScanned,
    riskOk,
    riskNeedsDecision,
    approved,
    publishReady,
    blockers,
    chips
  };
}

export type FinalReviewCompareDiff = {
  finalDurationSeconds: number | null;
  originalDurationSeconds: number | null;
  durationDeltaSeconds: number | null;
  subtitleBurned: boolean;
  resolution: string | null;
  sizeLabel: string | null;
};

/** Compact compare meta for operators judging original vs final. */
export function resolveFinalReviewCompareDiff(
  render: RenderOutput,
  manifest: SourceVideoAssetManifest | null = null
): FinalReviewCompareDiff {
  const specs = resolveRenderTechSpecs(render, manifest);
  const originalDurationSeconds =
    asPositiveNumber(manifest?.source_video?.duration_seconds) ?? null;
  const finalDurationSeconds = specs.duration_seconds;
  const durationDeltaSeconds =
    finalDurationSeconds != null && originalDurationSeconds != null
      ? Math.round((finalDurationSeconds - originalDurationSeconds) * 10) / 10
      : null;

  return {
    finalDurationSeconds,
    originalDurationSeconds,
    durationDeltaSeconds,
    subtitleBurned: specs.subtitle_burned,
    resolution: formatResolution(specs.width, specs.height),
    sizeLabel: formatBytes(specs.size_bytes)
  };
}

function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : null;
}

function toStringArray(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value.filter((item): item is string => typeof item === "string" && item.length > 0);
}

function asPositiveInt(value: unknown): number | null {
  const n = typeof value === "number" ? value : typeof value === "string" ? Number(value) : NaN;
  return Number.isFinite(n) && n > 0 ? Math.round(n) : null;
}

function asPositiveNumber(value: unknown): number | null {
  const n = typeof value === "number" ? value : typeof value === "string" ? Number(value) : NaN;
  return Number.isFinite(n) && n > 0 ? n : null;
}

function asNonEmptyString(value: unknown): string | null {
  return typeof value === "string" && value.trim().length > 0 ? value : null;
}
