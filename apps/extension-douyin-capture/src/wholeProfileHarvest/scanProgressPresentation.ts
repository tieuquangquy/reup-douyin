
export type ScanProgressPresentationFields = {
  /** Raw API/run discovered count (authority for headers). */
  discovered: number;
  expected: number | null;
  /** Capped count for profile-fraction bar (never above expected). */
  fractionDiscovered: number;
  overDisplayExtra: number | null;
  progressFractionLabel: string;
  percent: number | null;
};

export function resolveScanProgressOverDisplayExtra(
  discovered: number,
  expected: number | null
): number | null {
  if (expected == null || expected <= 0) return null;
  const extra = Math.round(discovered) - Math.round(expected);
  return extra > 0 ? extra : null;
}

export function resolveScanProgressProfileFractionDiscovered(
  discovered: number,
  expected: number | null
): number {
  const safeDiscovered = Math.max(0, Math.round(discovered));
  if (expected == null || expected <= 0) return safeDiscovered;
  return Math.min(safeDiscovered, Math.max(0, Math.round(expected)));
}

export function formatScanProgressFractionLabel(
  discovered: number,
  expected: number | null,
  _phaseLabel?: string
): string {
  if (expected == null || expected <= 0) return String(Math.max(0, Math.round(discovered)));
  const safeExpected = Math.max(0, Math.round(expected));
  const fractionDiscovered = resolveScanProgressProfileFractionDiscovered(discovered, safeExpected);
  return `${fractionDiscovered} / ${safeExpected}`;
}

export function computeScanProgressPercent(
  discovered: number,
  expected: number | null
): number | null {
  if (expected == null || expected <= 0) return null;
  const fractionDiscovered = resolveScanProgressProfileFractionDiscovered(discovered, expected);
  return Math.max(0, Math.min(100, Math.round((fractionDiscovered / Math.round(expected)) * 100)));
}

export function buildScanProgressPresentationFields(args: {
  discovered: number;
  expected: number | null;
  phaseLabel: string;
}): ScanProgressPresentationFields {
  const discovered = Math.max(0, Math.round(args.discovered));
  const expected = args.expected != null && args.expected > 0 ? Math.round(args.expected) : null;
  const fractionDiscovered = resolveScanProgressProfileFractionDiscovered(discovered, expected);
  const overDisplayExtra = resolveScanProgressOverDisplayExtra(discovered, expected);
  return {
    discovered,
    expected,
    fractionDiscovered,
    overDisplayExtra,
    progressFractionLabel: formatScanProgressFractionLabel(discovered, expected, args.phaseLabel),
    percent: computeScanProgressPercent(discovered, expected)
  };
}
