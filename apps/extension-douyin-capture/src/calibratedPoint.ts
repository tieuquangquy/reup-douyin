import type {
  ActionRailAssignedMetricDiagnostic,
  ActionRailBlockDiagnostic,
  ActionRailRejectedCandidateDiagnostic,
  CalibratedMetricName,
  CalibratedPointMetricResult,
  RawDomDetailMetrics,
  RightRailCalibration
} from "./types.js";

export const CALIBRATED_METRIC_ORDER: CalibratedMetricName[] = ["like_count", "comment_count", "favorite_count", "share_count"];

type PointExtractionResult = {
  point_results: Record<string, CalibratedPointMetricResult>;
  source_used: "calibrated_point_dom" | "calibrated_point_ocr" | "mixed_calibrated_point" | null;
  action_blocks_found: number;
  action_block_diagnostics: ActionRailBlockDiagnostic[];
  assigned_metrics: ActionRailAssignedMetricDiagnostic[];
  rejected_candidates_count: number;
  rejected_candidate_examples: ActionRailRejectedCandidateDiagnostic[];
  metric_confidence_by_field: Record<string, string> | null;
  rejected_metric_reasons: Record<string, string> | null;
  extraction_warning: string | null;
  ocr_used: boolean;
};

export function currentViewport(document: Document): { width: number; height: number } {
  return {
    width: window.innerWidth || document.documentElement?.clientWidth || 0,
    height: window.innerHeight || document.documentElement?.clientHeight || 0
  };
}

export function calibrationViewport(calibration: RightRailCalibration | null): { width: number; height: number } | null {
  return calibration ? { width: calibration.viewport_width, height: calibration.viewport_height } : null;
}

export function pointCalibrationWarning(calibration: RightRailCalibration | null, viewport: { width: number; height: number }): string | null {
  if (!calibration) return "calibration_missing";
  const widthRatio = calibration.viewport_width > 0 ? Math.abs(calibration.viewport_width - viewport.width) / calibration.viewport_width : 0;
  const heightRatio = calibration.viewport_height > 0 ? Math.abs(calibration.viewport_height - viewport.height) / calibration.viewport_height : 0;
  if (widthRatio > 0.18 || heightRatio > 0.18) return "viewport_changed_recalibration_recommended";
  return null;
}

export function parseCompactCount(text: string | null): number | null {
  if (!text) return null;
  const compact = compactText(text);
  if (!compact || compact.length > 16) return null;
  if (containsExcludedText(compact) || looksLikeTimelineText(compact) || looksLikeDateLikeDecimal(compact)) return null;
  const normalized = compact.replace(/\s+/g, "");
  if (!/^\d+(?:\.\d+)?(?:万|[wWkK])?$/.test(normalized)) return null;
  const suffix = normalized.slice(-1);
  const hasSuffix = /[万wWkK]/.test(suffix);
  const numeric = Number(hasSuffix ? normalized.slice(0, -1) : normalized);
  if (!Number.isFinite(numeric) || numeric < 0) return null;
  const multiplier = suffix === "万" || suffix.toLowerCase() === "w" ? 10_000 : suffix.toLowerCase() === "k" ? 1_000 : 1;
  return Math.round(numeric * multiplier);
}

export function parseCompactCountFromOcr(text: string | null): number | null {
  return parseCompactCount(text);
}

export function readCalibratedPointMetrics(document: Document, calibration: RightRailCalibration): PointExtractionResult {
  const viewport = currentViewport(document);
  const pointResults = Object.fromEntries(
    CALIBRATED_METRIC_ORDER.map((metric) => [metric, readCountAtPoint(document, metric, calibration, viewport)])
  ) as Record<string, CalibratedPointMetricResult>;
  const successful = Object.values(pointResults).filter((result) => result.value != null);
  const metricConfidenceByField: Record<string, string> = {};
  const rejectedMetricReasons: Record<string, string> = {};
  for (const metric of CALIBRATED_METRIC_ORDER) {
    const result = pointResults[metric]!;
    if (result.value != null) metricConfidenceByField[metric] = result.source === "calibrated_point_dom" ? "high" : "medium";
    else rejectedMetricReasons[metric] = result.warning_reason ?? "point_read_failed";
  }
  const diagnostics = pointResultsToDiagnostics(pointResults);
  return {
    point_results: pointResults,
    source_used: successful.length ? sourceUsedFromPointResults(pointResults) : null,
    action_blocks_found: successful.length,
    action_block_diagnostics: diagnostics,
    assigned_metrics: diagnostics.map((entry) => ({
      metric: (entry.assigned_metric ?? "like") as "like" | "comment" | "favorite" | "share",
      visible_text: entry.visible_text,
      value: entry.count_value,
      rect: entry.rect,
      source: "right_rail_element_from_point_fallback"
    })),
    rejected_candidates_count: CALIBRATED_METRIC_ORDER.length - successful.length,
    rejected_candidate_examples: Object.values(pointResults)
      .filter((result) => result.value == null)
      .map((result) => ({
        visible_text: result.raw_text,
        reason: result.warning_reason ?? "point_read_failed",
        rect: { x: result.point.x, y: result.point.y, width: 1, height: 1 }
      })),
    metric_confidence_by_field: Object.keys(metricConfidenceByField).length ? metricConfidenceByField : null,
    rejected_metric_reasons: Object.keys(rejectedMetricReasons).length ? rejectedMetricReasons : null,
    extraction_warning: successful.length === CALIBRATED_METRIC_ORDER.length ? pointCalibrationWarning(calibration, viewport) : "one_or_more_calibrated_points_failed",
    ocr_used: Object.values(pointResults).some((result) => result.source === "calibrated_point_ocr")
  };
}

function readCountAtPoint(
  document: Document,
  metric: CalibratedMetricName,
  calibration: RightRailCalibration,
  viewport: { width: number; height: number }
): CalibratedPointMetricResult {
  const storedPoint = calibration.points[metric];
  const point = {
    x: Math.round(storedPoint.x_ratio * viewport.width),
    y: Math.round(storedPoint.y_ratio * viewport.height),
    x_ratio: storedPoint.x_ratio,
    y_ratio: storedPoint.y_ratio
  };
  const elementsFromPoint = document.elementsFromPoint?.bind(document);
  if (!elementsFromPoint) {
    return { metric, source: "calibrated_point_dom", point, raw_text: null, value: null, warning_reason: "elements_from_point_unavailable" };
  }
  const offsets: Array<[number, number]> = [[0, 0], [0, -8], [0, 8], [-8, 0], [8, 0], [-12, -8], [12, -8], [-12, 8], [12, 8]];
  const candidates: Array<{ element: HTMLElement; text: string; value: number; distance: number; area: number }> = [];
  for (const [dx, dy] of offsets) {
    const x = Math.max(0, Math.min(viewport.width - 1, point.x + dx));
    const y = Math.max(0, Math.min(viewport.height - 1, point.y + dy));
    for (const node of elementsFromPoint(x, y)) {
      if (!isElementLike(node) || !isVisible(node)) continue;
      const rawText = compactText(node.innerText || node.textContent || "");
      const value = parseCompactCount(rawText);
      if (value == null) continue;
      const rect = node.getBoundingClientRect();
      const area = Math.max(1, rect.width * rect.height);
      const distance = Math.abs(rect.x + rect.width / 2 - point.x) + Math.abs(rect.y + rect.height / 2 - point.y);
      candidates.push({ element: node, text: normalizedCompactCountText(rawText), value, distance, area });
    }
  }
  const best = candidates.sort((left, right) => left.distance - right.distance || left.area - right.area)[0];
  if (!best) {
    return { metric, source: "calibrated_point_dom", point, raw_text: null, value: null, warning_reason: "compact_count_not_found_at_point" };
  }
  return {
    metric,
    source: "calibrated_point_dom",
    point,
    raw_text: best.text,
    value: best.value,
    candidate_path: descriptorForElement(best.element)
  };
}

function sourceUsedFromPointResults(results: Record<string, CalibratedPointMetricResult>): "calibrated_point_dom" | "calibrated_point_ocr" | "mixed_calibrated_point" {
  const sources = new Set(Object.values(results).filter((result) => result.value != null).map((result) => result.source));
  if (sources.size === 1 && sources.has("calibrated_point_dom")) return "calibrated_point_dom";
  if (sources.size === 1 && sources.has("calibrated_point_ocr")) return "calibrated_point_ocr";
  return "mixed_calibrated_point";
}

function pointResultsToDiagnostics(results: Record<string, CalibratedPointMetricResult>): ActionRailBlockDiagnostic[] {
  return CALIBRATED_METRIC_ORDER.map((metric, index) => {
    const result = results[metric]!;
    return {
      index,
      rect: { x: result.point.x, y: result.point.y, width: 1, height: 1 },
      visible_text: result.raw_text,
      aria_title_class_hints: result.candidate_path ?? null,
      assigned_metric: metric.replace("_count", "") as "like" | "comment" | "favorite" | "share",
      count_text: result.raw_text,
      count_value: result.value
    };
  });
}

function normalizedCompactCountText(text: string): string {
  return compactText(text).replace(/\s+/g, "");
}

function descriptorForElement(element: HTMLElement): string {
  const tag = element.tagName?.toLowerCase() ?? "unknown";
  const className = typeof element.className === "string" ? compactText(element.className).slice(0, 64) : "";
  return className ? `${tag}.${className}` : tag;
}

function containsExcludedText(text: string): boolean {
  return /豆瓣|纪录片|听抖音|@|第\d+集|合集|关注|follow|caption|player|control/i.test(text) || text.includes("#");
}

function looksLikeTimelineText(text: string): boolean {
  return /^\d{1,2}:\d{2}(?:\s*\/\s*\d{1,2}:\d{2}(?::\d{2})?)?$/.test(text);
}

function looksLikeDateLikeDecimal(text: string): boolean {
  return /^\d{1,2}\.\d$/.test(text);
}

function compactText(value: string): string {
  return value.replace(/\s+/g, " ").trim();
}

function isVisible(element: HTMLElement): boolean {
  const style = window.getComputedStyle(element);
  if (style.display === "none" || style.visibility === "hidden" || Number(style.opacity || "1") === 0) return false;
  const rect = element.getBoundingClientRect();
  return rect.width > 1 && rect.height > 1;
}

function isElementLike(value: unknown): value is HTMLElement {
  return Boolean(value && typeof value === "object" && "innerText" in value && "textContent" in value && "getBoundingClientRect" in value);
}

export function applyCalibratedPointMetricsToRawDomDetail(
  base: Pick<RawDomDetailMetrics, "duration_seconds" | "duration_text" | "selected_duration_source" | "duration_text_source" | "active_video_rect" | "viewport_width" | "viewport_height">,
  extraction: PointExtractionResult
): RawDomDetailMetrics {
  return {
    ...base,
    like_count: extraction.point_results.like_count!.value,
    like_count_text: extraction.point_results.like_count!.raw_text,
    like_count_source: extraction.point_results.like_count!.value != null ? extraction.point_results.like_count!.source : null,
    comment_count: extraction.point_results.comment_count!.value,
    comment_count_text: extraction.point_results.comment_count!.raw_text,
    comment_count_source: extraction.point_results.comment_count!.value != null ? extraction.point_results.comment_count!.source : null,
    favorite_count: extraction.point_results.favorite_count!.value,
    favorite_count_text: extraction.point_results.favorite_count!.raw_text,
    favorite_count_source: extraction.point_results.favorite_count!.value != null ? extraction.point_results.favorite_count!.source : null,
    share_count: extraction.point_results.share_count!.value,
    share_count_text: extraction.point_results.share_count!.raw_text,
    share_count_source: extraction.point_results.share_count!.value != null ? extraction.point_results.share_count!.source : null,
    point_results: extraction.point_results,
    action_blocks_found: extraction.action_blocks_found,
    modal_action_blocks_found: extraction.action_blocks_found,
    action_block_diagnostics: extraction.action_block_diagnostics,
    assigned_metrics: extraction.assigned_metrics,
    rejected_candidates_count: extraction.rejected_candidates_count,
    rejected_candidate_examples: extraction.rejected_candidate_examples,
    metric_confidence_by_field: extraction.metric_confidence_by_field,
    rejected_metric_reasons: extraction.rejected_metric_reasons,
    extraction_warning: extraction.extraction_warning,
    warning_reason: extraction.extraction_warning,
    ocr_used: extraction.ocr_used,
    extraction_mode: "right_rail_element_from_point_fallback",
    source_priority_used: "video_element_duration",
    source_used: extraction.source_used,
    extraction_source: extraction.source_used ?? "dom_detail_modal",
    confidence: "high"
  };
}
