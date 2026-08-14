/** Display helpers for Transcript Editor (ZH-first operator quiet chrome). */

import type { AssetManifest } from "../types/transcript-editor";

export type FlagTone = "danger" | "warn" | "good" | "neutral";

const PIPELINE_FLAG_RE =
  /^(funasr|duration_fit|sentence_split|workspace_translation_prompt|duration_rewrite_applied|caption_agreed|auto_approved|machine_translate|cjk_|translation_fallback|translation_v3|prompt_)/i;

/** Flags that are pipeline telemetry — not “ZH matches video” signals. */
export function isPipelineFlag(flag: string): boolean {
  const key = (flag || "").trim();
  if (!key) return false;
  if (PIPELINE_FLAG_RE.test(key)) return true;
  return (
    key.includes("funasr") ||
    key.includes("duration_fit") ||
    key.includes("sentence_split") ||
    key.includes("workspace_translation") ||
    key.includes("rewrite_applied") ||
    key.includes("duration_rewrite")
  );
}

/** Operator noise: length / caption-OCR / review spam — hide from default UI. */
export function isOperatorNoiseFlag(flag: string): boolean {
  const key = (flag || "").toLowerCase();
  if (!key) return false;
  if (isPipelineFlag(key)) return true;
  if (key.includes("too_long") || key === "too_long") return true;
  if (key.includes("caption_asr") || key.includes("caption_conflict")) return true;
  if (key.includes("needs_operator_review") || key.endsWith("_review")) return true;
  if (key.includes("unverified") || key.includes("demucs")) return true;
  return false;
}

/** Keep only ASR confidence-style signals for the quiet operator surface. */
export function isSourceQualityFlag(flag: string): boolean {
  const key = (flag || "").toLowerCase();
  return key.includes("low_confidence") || key.includes("likely_mistranscribed");
}

/** Length/fit flags already covered by the TTS fit banner — do not re-list in quiet summary. */
export function isTtsFitDuplicateFlag(flag: string): boolean {
  const key = (flag || "").toLowerCase();
  if (!key) return false;
  if (key.includes("too_long") || key.includes("too_short") || key.includes("slightly_long")) return true;
  if (key.includes("translation_too_long") || key.includes("for_slot")) return true;
  return false;
}

function fitBannerOwnsLengthSignal(fitStatus: string | null | undefined): boolean {
  return fitStatus === "slightly_long" || fitStatus === "too_long" || fitStatus === "too_short";
}

/**
 * Quiet summary under the TTS fit banner: drop length/fit duplicates when the banner owns that signal.
 * Machine details still receives the full flag list.
 */
export function flagsForFocusQuietSummary(
  flags: string[],
  fitStatus: string | null | undefined
): string[] {
  const unique = Array.from(new Set(flags.filter(Boolean)));
  if (!fitBannerOwnsLengthSignal(fitStatus)) return unique;
  return unique.filter((flag) => !isTtsFitDuplicateFlag(flag));
}

export function classifyFlagTone(flag: string): FlagTone {
  const key = (flag || "").toLowerCase();
  if (
    key.includes("low") ||
    key.includes("too") ||
    key.includes("missing") ||
    key.includes("overlap") ||
    key.includes("conflict") ||
    key.includes("gate_failed") ||
    key.includes("awkward") ||
    key.includes("mistranscribed")
  ) {
    return "danger";
  }
  if (
    key.includes("placeholder") ||
    key.includes("fallback") ||
    key.includes("review") ||
    key.includes("unverified") ||
    key.includes("demucs")
  ) {
    return "warn";
  }
  if (key.includes("agreed") || key.includes("auto_approved")) {
    return "good";
  }
  return "neutral";
}

export function flagToneClassName(tone: FlagTone): string {
  if (tone === "danger") return "pill danger";
  if (tone === "warn") return "pill warn";
  if (tone === "good") return "pill good";
  return "pill";
}

export type TruncatedFlags = {
  visible: string[];
  overflowCount: number;
  pipeline: string[];
};

export type PartitionFlagsOptions = {
  /** Default true: hide pipeline + length/caption/review noise; show source-quality only. */
  operatorQuiet?: boolean;
};

export function partitionSegmentFlags(
  flags: string[],
  maxVisible = 3,
  options: PartitionFlagsOptions = {}
): TruncatedFlags {
  const operatorQuiet = options.operatorQuiet !== false;
  const unique = Array.from(new Set(flags.filter(Boolean)));

  if (operatorQuiet) {
    const attention = unique
      .filter(isSourceQualityFlag)
      .sort((a, b) => toneRank(classifyFlagTone(a)) - toneRank(classifyFlagTone(b)));
    const visible = attention.slice(0, Math.max(0, maxVisible));
    return {
      visible,
      overflowCount: Math.max(0, attention.length - visible.length),
      pipeline: []
    };
  }

  const pipeline = unique.filter(isPipelineFlag);
  const attention = unique
    .filter((flag) => !isPipelineFlag(flag))
    .sort((a, b) => toneRank(classifyFlagTone(a)) - toneRank(classifyFlagTone(b)));
  const visible = attention.slice(0, Math.max(0, maxVisible));
  return {
    visible,
    overflowCount: Math.max(0, attention.length - visible.length),
    pipeline
  };
}

function toneRank(tone: FlagTone): number {
  if (tone === "danger") return 0;
  if (tone === "warn") return 1;
  if (tone === "good") return 2;
  return 3;
}

export function textsEqualForCompare(a: string, b: string): boolean {
  return (a || "").trim() === (b || "").trim();
}

export type SegmentCompareState = {
  vietnameseUnchanged: boolean;
  sourceUnchanged: boolean;
  timingUnchanged: boolean;
};

export function resolveSegmentCompareState(segment: {
  originalTranslatedText: string;
  translatedText: string;
  originalSourceText: string;
  sourceText: string;
  originalStartMs: number;
  originalEndMs: number;
  startMs: number;
  endMs: number;
}): SegmentCompareState {
  return {
    vietnameseUnchanged: textsEqualForCompare(segment.originalTranslatedText, segment.translatedText),
    sourceUnchanged: textsEqualForCompare(segment.originalSourceText, segment.sourceText),
    timingUnchanged:
      segment.originalStartMs === segment.startMs && segment.originalEndMs === segment.endMs
  };
}

export function formatFlagLabel(flag: string): string {
  return (flag || "").replace(/_/g, " ");
}

/** True when URL can reasonably load in an HTML <video> element. */
export function isDirectMediaPreviewUrl(url: string | null | undefined): boolean {
  const value = (url || "").trim();
  if (!value) return false;
  try {
    const parsed = new URL(value);
    const host = parsed.hostname.toLowerCase();
    if (host.includes("douyin.com") || host.includes("tiktok.com")) {
      // Page/share hosts are not streamable; CDN media hosts under *.douyinvod.* etc. may still be .mp4.
      if (!/\.(mp4|webm|mov|m4v)(\?|#|$)/i.test(parsed.pathname + parsed.search)) {
        return false;
      }
    }
    if (/\/video\/\d+/i.test(parsed.pathname)) return false;
    return /\.(mp4|webm|mov|m4v)(\?|#|$)/i.test(parsed.pathname + parsed.search);
  } catch {
    return /\.(mp4|webm|mov|m4v)(\?|#|$)/i.test(value);
  }
}

function findCurrentSourceVideoAsset(manifest: AssetManifest | null | undefined) {
  const assets = manifest?.assets ?? [];
  return (
    assets.find((asset) => asset.asset_type === "SOURCE_VIDEO_RAW" && asset.is_current !== false && asset.id) ??
    assets.find((asset) => asset.asset_type === "SOURCE_VIDEO" && asset.is_current !== false && asset.id) ??
    null
  );
}

export type TranscriptPreviewSource =
  | { kind: "media_asset"; assetId: string }
  | { kind: "direct"; url: string };

/**
 * Streamable preview for Transcript Editor: local SOURCE_VIDEO_RAW asset id (auth fetch),
 * or a rare direct .mp4 URL — never Douyin page/catalog URLs.
 */
export function resolveTranscriptPreviewSource(
  manifest: AssetManifest | null | undefined
): TranscriptPreviewSource | null {
  if (!manifest) return null;
  const rawAsset = findCurrentSourceVideoAsset(manifest);
  if (rawAsset?.id) return { kind: "media_asset", assetId: rawAsset.id };
  const fallback = manifest.source_video?.source_url ?? null;
  return isDirectMediaPreviewUrl(fallback) ? { kind: "direct", url: fallback as string } : null;
}

export function resolveTranscriptPreviewUrl(
  manifest: AssetManifest | null | undefined,
  mediaAssetContentUrl: (assetId: string) => string
): string | null {
  const source = resolveTranscriptPreviewSource(manifest);
  if (!source) return null;
  if (source.kind === "media_asset") return mediaAssetContentUrl(source.assetId);
  return source.url;
}
