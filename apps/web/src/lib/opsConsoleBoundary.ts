/**
 * Ops Console monitor/admin surfaces — not Operator Studio day-to-day workflow.
 * Operator routes that live under /ops/* (pipeline, capture-inbox) are allowlisted.
 */

export const OPS_CONSOLE_PREFIXES = [
  "/ops/jobs",
  "/ops/health",
  "/ops/risk",
  "/ops/reconciliation",
  "/ops/publish-health",
  "/ops/publish-attempts",
  "/ops/publish-control",
  "/ops/assets",
  "/ops/tools",
  "/ops/users",
  "/ops/routing-rules",
  "/ops/translation",
  "/ops/caption",
  "/ops/tts",
  "/ops/optimization"
] as const;

const PIPELINE_FALLBACK_PREFIXES = ["/ops/jobs", "/ops/health", "/ops/assets", "/ops/tools"] as const;

const DRAFTS_FALLBACK_PREFIXES = [
  "/ops/risk",
  "/ops/reconciliation",
  "/ops/publish-health",
  "/ops/publish-attempts",
  "/ops/publish-control",
  "/ops/routing-rules"
] as const;

export function isOpsConsoleHref(href: string | null | undefined): boolean {
  if (!href) return false;
  const path = href.split("?")[0] ?? href;
  if (path === "/ops") return true;
  // Operator workflow routes live under /ops/* but are not Ops Console.
  if (path === "/ops/pipeline" || path.startsWith("/ops/extensions/")) return false;
  return OPS_CONSOLE_PREFIXES.some(
    (prefix) => path === prefix || path.startsWith(`${prefix}/`) || path.startsWith(`${prefix}-`)
  );
}

export function operatorSafeHref(href: string | null | undefined, fallback: string): string {
  if (!href || isOpsConsoleHref(href)) return fallback;
  return href;
}

/** Map an Ops Console href to the nearest Operator Studio surface, or null to drop the CTA. */
export function operatorFallbackForOpsHref(href: string | null | undefined): string | null {
  if (!href) return null;
  const path = href.split("?")[0] ?? href;
  if (!isOpsConsoleHref(href)) return href;
  if (path === "/ops") return "/";
  if (PIPELINE_FALLBACK_PREFIXES.some((prefix) => path === prefix || path.startsWith(`${prefix}/`) || path.startsWith(`${prefix}-`))) {
    return "/ops/pipeline";
  }
  if (DRAFTS_FALLBACK_PREFIXES.some((prefix) => path === prefix || path.startsWith(`${prefix}/`) || path.startsWith(`${prefix}-`))) {
    return "/publishing/drafts";
  }
  // translation / caption / tts / optimization — drop Operator deep-links
  return null;
}
