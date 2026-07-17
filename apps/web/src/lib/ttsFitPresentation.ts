/** Display helpers for TTS timing-fit badges in Transcript Editor. */

import type { FlagTone } from "./transcriptEditorPresentation";
import type { TtsClipFit, TtsFitStatus } from "../types/tts";
import { isTtsFitProblem } from "../types/tts";

export function classifyTtsFitTone(status: string | null | undefined): FlagTone {
  if (status === "too_long" || status === "too_short") return "danger";
  if (status === "slightly_long") return "warn";
  if (status === "fits_well") return "good";
  return "neutral";
}

export function formatTtsFitRatio(ratio: number | null | undefined): string | null {
  if (ratio == null || !Number.isFinite(ratio)) return null;
  return `${Math.round(ratio * 100)}%`;
}

export function ttsFitStatusKey(status: string | null | undefined): TtsFitStatus | "unknown" {
  if (
    status === "fits_well" ||
    status === "slightly_long" ||
    status === "too_long" ||
    status === "too_short"
  ) {
    return status;
  }
  return "unknown";
}

/** Beat rail: only show when fit is a problem (reduce noise). */
export function beatRailShowsTtsFit(clip: TtsClipFit | null | undefined): boolean {
  return Boolean(clip && isTtsFitProblem(clip.fit_status));
}
