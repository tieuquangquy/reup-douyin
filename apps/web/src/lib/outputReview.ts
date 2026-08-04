import type { ReupQueueItem } from "../types/reup-queue";

/**
 * Reading side of the post-render QA gate (`apps/api/src/services/render_qa_gate.py`).
 * The backend writes its verdict into `metadata_json.render_qa`; nothing here re-derives
 * quality, it only presents what the pipeline already decided.
 */
export type RenderQaStatus = "pass" | "warn" | "fail";
export type RenderQaCheckStatus = RenderQaStatus | "skipped";

export type RenderQaCheck = {
  key: string;
  status: RenderQaCheckStatus;
  detail: string;
};

export type RenderQaVerdict = {
  status: RenderQaStatus;
  summary: string;
  failed: string[];
  warned: string[];
  checks: RenderQaCheck[];
};

const QA_STATUSES: RenderQaStatus[] = ["pass", "warn", "fail"];
const CHECK_STATUSES: RenderQaCheckStatus[] = ["pass", "warn", "fail", "skipped"];

function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : null;
}

function asStringList(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((entry): entry is string => typeof entry === "string") : [];
}

function parseChecks(value: unknown): RenderQaCheck[] {
  if (!Array.isArray(value)) return [];
  const checks: RenderQaCheck[] = [];
  for (const entry of value) {
    const record = asRecord(entry);
    if (!record) continue;
    const key = typeof record.key === "string" ? record.key : null;
    const status = record.status as RenderQaCheckStatus;
    if (!key || !CHECK_STATUSES.includes(status)) continue;
    checks.push({ key, status, detail: typeof record.detail === "string" ? record.detail : "" });
  }
  return checks;
}

export function parseRenderQaVerdict(item: ReupQueueItem): RenderQaVerdict | null {
  const payload = asRecord(asRecord(item.metadata_json)?.render_qa);
  if (!payload) return null;
  const status = payload.status as RenderQaStatus;
  if (!QA_STATUSES.includes(status)) return null;
  return {
    status,
    summary: typeof payload.summary === "string" ? payload.summary : "",
    failed: asStringList(payload.failed),
    warned: asStringList(payload.warned),
    checks: parseChecks(payload.checks)
  };
}

/** Only items with a rendered file belong here; `ready_final` alone can mean "TTS done". */
export function isOutputReviewItem(item: ReupQueueItem): boolean {
  return Boolean(item.render_output_id) || parseRenderQaVerdict(item) !== null;
}

const QUEUE_RANK: Record<string, number> = { fail: 0, warn: 1, ungraded: 2, pass: 3 };

function queueRank(item: ReupQueueItem): number {
  return QUEUE_RANK[parseRenderQaVerdict(item)?.status ?? "ungraded"];
}

/** Finished clips, worst verdict first, so wasted review time goes to the risky ones. */
export function outputReviewQueue(items: ReupQueueItem[]): ReupQueueItem[] {
  return items
    .filter(isOutputReviewItem)
    .map((item, index) => ({ item, index }))
    .sort((a, b) => queueRank(a.item) - queueRank(b.item) || a.index - b.index)
    .map((entry) => entry.item);
}

export type OutputReviewCounts = {
  total: number;
  failed: number;
  warned: number;
  passed: number;
  ungraded: number;
};

export function outputReviewCounts(items: ReupQueueItem[]): OutputReviewCounts {
  const counts: OutputReviewCounts = { total: 0, failed: 0, warned: 0, passed: 0, ungraded: 0 };
  for (const item of items) {
    if (!isOutputReviewItem(item)) continue;
    counts.total += 1;
    const status = parseRenderQaVerdict(item)?.status;
    if (status === "fail") counts.failed += 1;
    else if (status === "warn") counts.warned += 1;
    else if (status === "pass") counts.passed += 1;
    else counts.ungraded += 1;
  }
  return counts;
}

export type OutputReviewFixTarget = {
  href: string;
  label: string;
  reason: string;
};

/**
 * Which stage produced the defect the QA gate found. Sending an operator to a generic
 * details page costs them the same diagnosis the gate already did.
 */
const FIX_BY_CHECK: Record<string, { stage: "transcript" | "render"; reason: string }> = {
  dub_audio: { stage: "transcript", reason: "The dub is missing — regenerate the voice-over." },
  subtitle_burned: { stage: "transcript", reason: "No subtitles were burned — check the Vietnamese lines." },
  duration_match: { stage: "render", reason: "The render does not match the source length — re-render." },
  resolution: { stage: "render", reason: "Output geometry is wrong — re-render with the right profile." },
  render_warnings: { stage: "render", reason: "The renderer reported warnings worth reading." },
  risk_gate: { stage: "render", reason: "Risk flags are open on this render." }
};

export function outputReviewFixTarget(item: ReupQueueItem): OutputReviewFixTarget {
  const verdict = parseRenderQaVerdict(item);
  const culprit = [...(verdict?.failed ?? []), ...(verdict?.warned ?? [])]
    .map((key) => FIX_BY_CHECK[key])
    .find((entry) => entry !== undefined);

  if (!culprit) {
    return {
      href: `/production/final-review/${item.source_video_id}`,
      label: "Open full review",
      reason: verdict?.summary || "Nothing flagged — open the full review to compare against the source."
    };
  }
  if (culprit.stage === "transcript") {
    return {
      href: `/production/transcript-editor/${item.source_video_id}`,
      label: "Fix transcript",
      reason: culprit.reason
    };
  }
  return {
    href: `/production/final-review/${item.source_video_id}`,
    label: "Fix render",
    reason: culprit.reason
  };
}

export type RenderQaBadgeTone = "positive" | "warning" | "critical" | "neutral";

export function renderQaBadgeTone(status: RenderQaStatus | null | undefined): RenderQaBadgeTone {
  if (status === "fail") return "critical";
  if (status === "warn") return "warning";
  if (status === "pass") return "positive";
  return "neutral";
}

export function renderQaBadgeLabel(status: RenderQaStatus | null | undefined): string {
  if (status === "fail") return "QA failed";
  if (status === "warn") return "QA warning";
  if (status === "pass") return "QA passed";
  return "Not graded";
}
