import type { ExtensionCapturePayload, FullModalHarvestRequestPayload } from "./types.js";

export const HARVEST_PLAN_SCHEMA_VERSION = "douyin_extension_harvest_plan.v1" as const;
export const CAPTURE_CURRENT_PAGE_SCHEMA_VERSION = "douyin_extension_capture.v1" as const;
export const FULL_MODAL_HARVEST_SCHEMA_VERSION = "douyin_full_modal_harvest.v1" as const;

export type HarvestPlanRequestPayload = Omit<ExtensionCapturePayload, "schema_version"> & {
  schema_version: typeof HARVEST_PLAN_SCHEMA_VERSION;
};

export type CaptureCurrentPageRequestPayload = Omit<ExtensionCapturePayload, "schema_version"> & {
  schema_version: typeof CAPTURE_CURRENT_PAGE_SCHEMA_VERSION;
};

export function buildHarvestPlanRequestPayload(payload: ExtensionCapturePayload): HarvestPlanRequestPayload {
  return {
    ...payload,
    schema_version: HARVEST_PLAN_SCHEMA_VERSION
  };
}

export function buildCaptureCurrentPageRequestPayload(payload: ExtensionCapturePayload): CaptureCurrentPageRequestPayload {
  return {
    ...payload,
    schema_version: CAPTURE_CURRENT_PAGE_SCHEMA_VERSION
  };
}

export function buildFullModalHarvestRequestPayload(payload: Omit<FullModalHarvestRequestPayload, "schema_version">): FullModalHarvestRequestPayload {
  return {
    schema_version: FULL_MODAL_HARVEST_SCHEMA_VERSION,
    ...payload
  };
}

export function validateHarvestPlanRequestPayload(payload: { schema_version?: unknown }): void {
  if (payload.schema_version === HARVEST_PLAN_SCHEMA_VERSION) return;
  throw new Error(
    `harvest_plan_schema_version_mismatch: expected=${HARVEST_PLAN_SCHEMA_VERSION}, got=${String(payload.schema_version ?? "missing")}`
  );
}
