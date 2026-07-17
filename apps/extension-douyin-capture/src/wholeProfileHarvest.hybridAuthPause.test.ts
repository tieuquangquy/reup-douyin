import assert from "node:assert/strict";
import { wholeProfileHarvestError } from "./wholeProfileHarvest/errors.js";
import {
  resumeHybridHarvest,
  type WholeProfileHarvestRuntime
} from "./wholeProfileHarvest/controller.js";
import { createWholeProfileHarvestIdleState, WHOLE_PROFILE_HARVEST_STATE_KEY, type WholeProfileHarvestState } from "./wholeProfileHarvest/state.js";

class MemoryStorage {
  values: Record<string, unknown> = {};
  async get(key: string | string[] | Record<string, unknown> | null): Promise<Record<string, unknown>> {
    if (typeof key === "string") return { [key]: this.values[key] };
    if (Array.isArray(key)) {
      const out: Record<string, unknown> = {};
      for (const entry of key) out[entry] = this.values[entry];
      return out;
    }
    return {};
  }
  async set(items: Record<string, unknown>): Promise<void> {
    Object.assign(this.values, items);
  }
}

function buildPausedHybridAuthState(at: string): WholeProfileHarvestState {
  const base = createWholeProfileHarvestIdleState(at);
  return {
    ...base,
    status: "paused",
    phase: "paused",
    profile_url: "https://www.douyin.com/user/test-profile",
    workflow: {
      ...base.workflow,
      collection: { ...base.workflow.collection, status: "paused", updated_at: at, last_error: null },
      active_task: null,
      action_lock: null
    },
    harvest: {
      ...base.harvest,
      status: "paused",
      paused_reason: "backend_auth_required",
      pause_message: "Backend login expired. Sign in to the app again in extension settings, then press Resume.",
      resume_available: true,
      batch_limit: "all",
      pending: 2,
      queue: [
        { aweme_id: "7000000000000000001", status: "pending", capture_status: "new", source_url: "https://www.douyin.com/video/7000000000000000001" },
        { aweme_id: "7000000000000000002", status: "pending", capture_status: "new", source_url: "https://www.douyin.com/video/7000000000000000002" }
      ],
      pause_diagnostics: {
        source: "hybrid_flush",
        hybrid_resume_after_auth: "yes",
        hybrid_unattended_collect: "yes"
      },
      updated_at: at
    },
    harvest_options: {
      ...base.harvest_options,
      batch_limit: 10
    },
    updated_at: at
  };
}

const authError = wholeProfileHarvestError("backend_auth_required");
assert.match(authError.message, /Backend login expired/i, "backend_auth_required must explain backend login expired");
assert.match(authError.next_action, /Sign in/i, "backend_auth_required must tell operator to sign in again");

const at = "2026-07-05T14:00:00.000Z";
const storage = new MemoryStorage();
storage.values[WHOLE_PROFILE_HARVEST_STATE_KEY] = buildPausedHybridAuthState(at);
let dispatchCount = 0;
const runtime = {
  storage,
  now: () => at,
  flushCanonicalHarvestPayload: async () => ({ ok: true, status: 200, error_code: null, error_message: null })
} as unknown as WholeProfileHarvestRuntime;

const originalChrome = (globalThis as { chrome?: unknown }).chrome;
(globalThis as { chrome?: { runtime?: { sendMessage?: (message: unknown) => Promise<unknown> } } }).chrome = {
  runtime: {
    sendMessage: async (message: unknown) => {
      const typed = message as { type?: string };
      assert.equal(typed.type, "DOUYIN_HYBRID_UNATTENDED_COLLECT_ALL", "resume after auth pause must dispatch unattended hybrid collect");
      dispatchCount += 1;
      return { ok: true };
    }
  }
};

try {
  const resumed = await resumeHybridHarvest(runtime);
  assert.equal(dispatchCount, 1, "resumeHybridHarvest must dispatch hybrid runner once");
  assert.notEqual(resumed.harvest.paused_reason, "backend_auth_required", "resume must clear backend auth pause reason before dispatch");
  const stored = storage.values[WHOLE_PROFILE_HARVEST_STATE_KEY] as WholeProfileHarvestState;
  assert.equal(stored.workflow.collection.status, "running", "resume must mark collection running before dispatch");
  assert.equal(
    (stored.debug.last_response_summary as Record<string, unknown> | undefined)?.hybrid_resume_after_auth,
    "yes",
    "resume must record hybrid_resume_after_auth diagnostics"
  );
} finally {
  if (typeof originalChrome === "undefined") {
    delete (globalThis as { chrome?: unknown }).chrome;
  } else {
    (globalThis as { chrome?: unknown }).chrome = originalChrome;
  }
}

console.log("wholeProfileHarvest.hybridAuthPause.test.ts: PASS");
