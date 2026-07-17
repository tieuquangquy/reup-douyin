export type DouyinCalibrationPointName = "like" | "comment" | "favorite" | "share";
export type DouyinCalibrationStatus = "unknown" | "needed" | "calibrated";
export type DouyinCalibrationSource = "canonical" | "legacy_storage" | "chrome_storage" | "content_script" | "unknown";
export type DouyinCalibrationPointMap = Record<DouyinCalibrationPointName, Record<string, unknown> | null>;

export type DouyinCalibrationLayout = "profile_modal" | "direct_video" | "unknown";

export type DouyinScannerCalibration = {
  status: DouyinCalibrationStatus;
  ready: boolean;
  layout: DouyinCalibrationLayout;
  source_url: string | null;
  profile_url: string | null;
  aweme_id: string | null;
  source: DouyinCalibrationSource;
  updated_at: string | null;
  points: DouyinCalibrationPointMap;
  point_count: number;
  missing_points: DouyinCalibrationPointName[];
  migrated_from_legacy: boolean;
  storage_keys_checked_count: number | null;
};

export const DOUYIN_SCANNER_CALIBRATION_KEY = "douyinProfileScanner.calibration";
export const DOUYIN_SCANNER_STORAGE_ROOT_KEY = "douyinProfileScanner";
export const REQUIRED_DOUYIN_CALIBRATION_POINTS: DouyinCalibrationPointName[] = ["like", "comment", "favorite", "share"];

export const DOUYIN_CALIBRATION_STORAGE_KEYS = [
  DOUYIN_SCANNER_CALIBRATION_KEY,
  DOUYIN_SCANNER_STORAGE_ROOT_KEY,
  "douyinRightRailCalibration",
  "rightRailCalibration",
  "calibration_points",
  "calibration",
  "modalHarvestCalibration",
  "douyinModalHarvestCalibration"
] as const;

export type DouyinCalibrationStorage = {
  get(keys: string | string[]): Promise<Record<string, unknown>>;
  set(items: Record<string, unknown>): Promise<void>;
};

function emptyPoints(): DouyinCalibrationPointMap {
  return { like: null, comment: null, favorite: null, share: null };
}

function isObject(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function stableSerialize(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map((item) => stableSerialize(item)).join(",")}]`;
  if (value && typeof value === "object") {
    const entries = Object.entries(value as Record<string, unknown>).sort(([left], [right]) => left.localeCompare(right));
    return `{${entries.map(([key, item]) => `${JSON.stringify(key)}:${stableSerialize(item)}`).join(",")}}`;
  }
  return JSON.stringify(value);
}

function normalizeMetricName(value: unknown): DouyinCalibrationPointName | null {
  if (typeof value !== "string") return null;
  const normalized = value.trim().toLowerCase().replace(/-/g, "_");
  if (normalized === "like" || normalized === "like_count") return "like";
  if (normalized === "comment" || normalized === "comment_count") return "comment";
  if (normalized === "favorite" || normalized === "favourite" || normalized === "favorite_count" || normalized === "favourite_count") return "favorite";
  if (normalized === "share" || normalized === "share_count") return "share";
  return null;
}

function copyPoint(value: unknown): Record<string, unknown> | null {
  return isObject(value) ? { ...value } : null;
}

function addPoint(points: DouyinCalibrationPointMap, metric: unknown, value: unknown): void {
  const key = normalizeMetricName(metric);
  const point = copyPoint(value);
  if (key && point) points[key] = point;
}

function collectObjectPoints(raw: Record<string, unknown>, points: DouyinCalibrationPointMap): void {
  for (const [key, value] of Object.entries(raw)) addPoint(points, key, value);
}

function collectArrayPoints(raw: unknown[], points: DouyinCalibrationPointMap): void {
  for (const item of raw) {
    if (!isObject(item)) continue;
    addPoint(points, item.metric ?? item.name ?? item.key ?? item.type, item);
  }
}

function stringValue(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

export function resolveDouyinCalibrationLayout(sourceUrl: string | null | undefined): { layout: DouyinCalibrationLayout; profile_url: string | null; aweme_id: string | null } {
  if (!sourceUrl) return { layout: "unknown", profile_url: null, aweme_id: null };
  try {
    const parsed = new URL(sourceUrl);
    const modalId = parsed.searchParams.get("modal_id")?.trim() || null;
    const videoMatch = parsed.pathname.match(/\/video\/([^/?#]+)/);
    if (/\/user\/[^/?#]+/.test(parsed.pathname) && modalId) {
      parsed.searchParams.delete("modal_id");
      return { layout: "profile_modal", profile_url: parsed.toString(), aweme_id: modalId };
    }
    if (videoMatch?.[1]) return { layout: "direct_video", profile_url: null, aweme_id: videoMatch[1] };
  } catch {
    return { layout: sourceUrl.includes("modal_id=") ? "profile_modal" : sourceUrl.includes("/video/") ? "direct_video" : "unknown", profile_url: null, aweme_id: null };
  }
  return { layout: "unknown", profile_url: null, aweme_id: null };
}

export function normalizeDouyinCalibration(rawCalibration: unknown, options: { source?: DouyinCalibrationSource; updated_at?: string | null; migrated_from_legacy?: boolean; storage_keys_checked_count?: number } = {}): DouyinScannerCalibration {
  const points = emptyPoints();
  if (Array.isArray(rawCalibration)) {
    collectArrayPoints(rawCalibration, points);
  } else if (isObject(rawCalibration)) {
    if (isObject(rawCalibration.points)) collectObjectPoints(rawCalibration.points, points);
    if (isObject(rawCalibration.metrics)) collectObjectPoints(rawCalibration.metrics, points);
    if (Array.isArray(rawCalibration.points)) collectArrayPoints(rawCalibration.points, points);
    if (Array.isArray(rawCalibration.metrics)) collectArrayPoints(rawCalibration.metrics, points);
    collectObjectPoints(rawCalibration, points);
  }

  const missing_points = REQUIRED_DOUYIN_CALIBRATION_POINTS.filter((key) => !points[key]);
  const point_count = REQUIRED_DOUYIN_CALIBRATION_POINTS.length - missing_points.length;
  const ready = point_count === REQUIRED_DOUYIN_CALIBRATION_POINTS.length;
  const sourceUrl = isObject(rawCalibration) ? stringValue(rawCalibration.source_url ?? rawCalibration.url ?? rawCalibration.current_url ?? rawCalibration.page_url) : null;
  const context = resolveDouyinCalibrationLayout(sourceUrl);
  return {
    status: ready ? "calibrated" : rawCalibration == null ? "unknown" : "needed",
    ready,
    layout: isObject(rawCalibration) && (rawCalibration.layout === "profile_modal" || rawCalibration.layout === "direct_video") ? rawCalibration.layout : context.layout,
    source_url: sourceUrl,
    profile_url: isObject(rawCalibration) ? stringValue(rawCalibration.profile_url) ?? context.profile_url : context.profile_url,
    aweme_id: isObject(rawCalibration) ? stringValue(rawCalibration.aweme_id ?? rawCalibration.modal_id) ?? context.aweme_id : context.aweme_id,
    source: options.source ?? "unknown",
    updated_at: options.updated_at ?? (isObject(rawCalibration) && typeof rawCalibration.updated_at === "string" ? rawCalibration.updated_at : isObject(rawCalibration) && typeof rawCalibration.created_at === "string" ? rawCalibration.created_at : null),
    points,
    point_count,
    missing_points,
    migrated_from_legacy: options.migrated_from_legacy ?? false,
    storage_keys_checked_count: options.storage_keys_checked_count ?? null
  };
}

function sourceForKey(key: string): DouyinCalibrationSource {
  if (key === DOUYIN_SCANNER_CALIBRATION_KEY || key === DOUYIN_SCANNER_STORAGE_ROOT_KEY) return "canonical";
  if (key === "douyinRightRailCalibration") return "chrome_storage";
  return "legacy_storage";
}

function rawCalibrationFromStoredValue(key: string, value: unknown): unknown {
  if (key === DOUYIN_SCANNER_STORAGE_ROOT_KEY && isObject(value)) return value.calibration;
  return value;
}

function calibrationFingerprint(value: DouyinScannerCalibration): string {
  return stableSerialize({
    status: value.status,
    ready: value.ready,
    layout: value.layout,
    source_url: value.source_url,
    profile_url: value.profile_url,
    aweme_id: value.aweme_id,
    source: value.source,
    updated_at: value.updated_at,
    points: value.points,
    point_count: value.point_count,
    missing_points: value.missing_points,
    migrated_from_legacy: value.migrated_from_legacy,
    storage_keys_checked_count: value.storage_keys_checked_count
  });
}

function bridgeFingerprint(value: unknown): string {
  return stableSerialize(value);
}

export async function syncDouyinCalibrationFromStorage(storage: DouyinCalibrationStorage, now = new Date().toISOString()): Promise<DouyinScannerCalibration> {
  const keys = Array.from(new Set(DOUYIN_CALIBRATION_STORAGE_KEYS));
  const stored = await storage.get(keys);
  const canonicalStored = rawCalibrationFromStoredValue(DOUYIN_SCANNER_CALIBRATION_KEY, stored[DOUYIN_SCANNER_CALIBRATION_KEY]);
  let best: DouyinScannerCalibration | null = null;

  for (const key of keys) {
    const raw = rawCalibrationFromStoredValue(key, stored[key]);
    if (typeof raw === "undefined" || raw === null) continue;
    const normalized = normalizeDouyinCalibration(raw, {
      source: sourceForKey(key),
      migrated_from_legacy: key !== DOUYIN_SCANNER_CALIBRATION_KEY && key !== DOUYIN_SCANNER_STORAGE_ROOT_KEY,
      storage_keys_checked_count: keys.length
    });
    if (normalized.ready) {
      best = normalized;
      break;
    }
    if (!best || normalized.point_count > best.point_count) best = normalized;
  }

  const fallback = normalizeDouyinCalibration(null, { storage_keys_checked_count: keys.length });
  const canonical: DouyinScannerCalibration = best?.ready
    ? { ...best, status: "calibrated", ready: true, storage_keys_checked_count: keys.length }
    : {
        ...(best ?? fallback),
        status: best && best.point_count > 0 ? "needed" : "unknown",
        ready: false,
        storage_keys_checked_count: keys.length,
        updated_at: best?.updated_at ?? fallback.updated_at ?? (best ? now : null)
      };

  const canonicalBridge = { calibration: canonical };
  const nextCanonicalFingerprint = calibrationFingerprint(canonical);
  const currentCanonicalFingerprint = canonicalStored == null
    ? null
    : calibrationFingerprint(normalizeDouyinCalibration(canonicalStored, {
      source: "canonical",
      migrated_from_legacy: false,
      storage_keys_checked_count: keys.length
    }));
  const currentBridgeFingerprint = bridgeFingerprint(stored[DOUYIN_SCANNER_STORAGE_ROOT_KEY]);
  const nextBridgeFingerprint = bridgeFingerprint(canonicalBridge);

  if (currentCanonicalFingerprint !== nextCanonicalFingerprint || currentBridgeFingerprint !== nextBridgeFingerprint) {
    await storage.set({
      [DOUYIN_SCANNER_CALIBRATION_KEY]: canonical,
      [DOUYIN_SCANNER_STORAGE_ROOT_KEY]: canonicalBridge
    });
  }

  return canonical;
}
