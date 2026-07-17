export type DouyinEngagementMetric = "comment" | "share" | "like" | "view";

export type DouyinEngagementParseResult =
  | { kind: "numeric"; value: number; rawText: string }
  | { kind: "zero_sentinel"; value: 0; rawText: string; sentinel: string }
  | { kind: "missing" };

export const COMMENT_ZERO_SENTINELS = ["抢首评", "快来抢首评", "抢沙发"] as const;

const SHARE_ZERO_SENTINEL_PATTERN = /^分享$/;

function compactText(rawText: string | null | undefined): string {
  if (!rawText) return "";
  return rawText.replace(/\s+/g, " ").trim();
}

export function parseDouyinEngagementText(
  metric: DouyinEngagementMetric,
  rawText: string | null | undefined,
  options?: { shareIconContext?: boolean }
): DouyinEngagementParseResult {
  const text = compactText(rawText);
  if (!text) return { kind: "missing" };

  if (metric === "comment") {
    for (const sentinel of COMMENT_ZERO_SENTINELS) {
      if (text === sentinel || text.includes(sentinel)) {
        return { kind: "zero_sentinel", value: 0, rawText: sentinel, sentinel };
      }
    }
    return { kind: "missing" };
  }

  if (metric === "share") {
    if (options?.shareIconContext && SHARE_ZERO_SENTINEL_PATTERN.test(text)) {
      return { kind: "zero_sentinel", value: 0, rawText: text, sentinel: text };
    }
    return { kind: "missing" };
  }

  return { kind: "missing" };
}

export function parseDouyinEngagementCount(
  metric: DouyinEngagementMetric,
  rawText: string | null | undefined,
  options?: { shareIconContext?: boolean }
): number | null {
  const parsed = parseDouyinEngagementText(metric, rawText, options);
  return parsed.kind === "zero_sentinel" ? 0 : null;
}
