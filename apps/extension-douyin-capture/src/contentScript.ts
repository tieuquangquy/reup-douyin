import { FULL_MODAL_HARVEST_FLUSH_QUEUE_KEY } from "./flushQueue.js";
import { buildCaptureContext, buildCapturePayload, detectPageFromDocument, discoverGridVideos, filterNetworkItemsForContext } from "./extractor.js";
import { buildFullModalHarvestRequestPayload } from "./requestPayloads.js";
import { hydrateDetailEvidenceForDiscoveries } from "./detailHydration.js";
import {
  detectCaptchaOrLoginWall,
  detectCurrentAwemeId,
  normalizeHarvestOptions,
  probeCurrentModalMetrics,
  shouldRequireProbeOverride,
  waitForCurrentModalMetrics,
  waitForModalIdMatch
} from "./modalHarvest.js";
import { installDouyinNetworkHook, readDouyinNetworkCache } from "./networkCache.js";
import {
  buildPassiveNetworkStoredTarget22C12A,
  classifyPassiveNetworkEndpointKind22C12A,
  createPassiveNetworkProbeSummary22C12A,
  extractPassiveNetworkBatch22C12A,
  markPassiveNetworkProbeError22C12A,
  markPassiveNetworkProbeInjected22C12A,
  markPassiveNetworkProbeInjectionAttempted22C12A,
  markPassiveNetworkProbeListenerReady22C12A,
  markPassiveNetworkProbeReady22C12A,
  mergePassiveNetworkProbeBatch22C12A,
  type PassiveNetworkProbeSummary22C12A
} from "./networkProbe22C12A.js";
import * as modalWholeProfileTest22C11B from "./modalWholeProfileTest.js";
import { WHOLE_PROFILE_HARVEST_STATE_KEY, createWholeProfileHarvestIdleState, type WholeProfileHarvestState } from "./wholeProfileHarvest/state.js";
import { CONTENT_SCRIPT_RUNTIME_BUILD_ID, EXTENSION_BUILD_TIMESTAMP, EXTENSION_RUNTIME_BUILD_ID } from "./generated/buildIdentity.js";
import {
  appendRecentItem,
  completeHarvestRuntimeV2,
  createHarvestRuntimeV2,
  createIdleHarvestRuntimeV2,
  firstPendingTarget,
  HARVEST_PENDING_FLUSH_QUEUE_V2_KEY,
  HARVEST_RUNTIME_V2_KEY,
  heartbeatHarvestRuntimeV2,
  LEGACY_HARVEST_STORAGE_KEYS,
  normalizeHarvestRuntimeV2,
  pauseHarvestRuntimeV2,
  runtimeV2ToProgress,
  touchHarvestRuntimeV2,
  transitionHarvestRuntime,
  updateTargetStatus,
} from "./harvestRuntimeV2.js";
import type {
  DouyinContentScriptPong,
  DouyinPageContext,
  DouyinPageViewport,
  DouyinProfileVideoEvidenceProbe,
  ExtensionBackendPostResponse,
  ExtensionMessage,
  ExtensionMessageResponse,
  FullModalHarvestItemPayload,
  FullModalHarvestProgress,
  HarvestPlanProfileCardEvidence,
  HarvestRuntimeV2State,
  NetworkCacheMessage,
  PassiveNetworkProbeBatchMessage22C12A,
  PassiveNetworkProbeCursorFields22C12BR2,
  PassiveNetworkProbeEndpointKind22C12A,
  PassiveNetworkProbeStoredTarget22C12A,
  NetworkVideoMetadata,
  RightRailCalibration,
  SafeHarvestRunPhase,
  SafeHarvestRunState,
  SafeHarvestRunStopReason,
  SafeHarvestRunTargetStatus
} from "./types.js";

installDouyinNetworkHook();

const buildDouyinProfileDomProbe = modalWholeProfileTest22C11B.buildDouyinProfileDomProbe;
const RIGHT_RAIL_CALIBRATION_KEY = "douyinRightRailCalibration";
const HARVEST_DEBUG_PREFIX = "[reup-douyin][full-modal-harvest]";
const SAFE_HARVEST_RUN_KEY = "douyinSafeHarvestRun";
const CONTENT_SCRIPT_VERSION = "22C-13A";
const RUNTIME_AUTHORITY_VERSION_22C11B = "22C-11B";
const DIAGNOSTICS_RUNTIME_VERSION_22C11B = "22C-11B";
const SCAN_CONTROLLER_VERSION_22C11B = "22C-11B-unified-runtime";
const PAGINATION_VERIFICATION_VERSION_22C13A = "22C-13A";
const SCAN_PROFILE_PIPELINE_LOCK_22C13A = "network_stream_queue_adapter_22C12D|collector_idle_after_last_live_batch|success_unknown_expected|canonical_scan_routing";
const MANUAL_PAGINATION_TRUTH_TEST_MESSAGE_22C13A = "DOUYIN_MANUAL_PAGINATION_TRUTH_TEST_22C13A";
const POPUP_RUNTIME_SYNC_SOURCE_22C11B = "active_tab_runtime_authority_snapshot_22C11B";
const RUNTIME_AUTHORITY_SNAPSHOT_MESSAGE_22C11B = "DOUYIN_RUNTIME_AUTHORITY_SNAPSHOT_22C11B";
const PAGINATION_TRACE_VERSION_22C12C = "22C-12C";
const PAGINATION_TRACE_VERSION_22C12E = "22C-12E";
const ACTIVATION_TRUTH_PROBE_VERSION_22C12E = "22C-12E";
const INTERACTION_TRACE_RUNTIME_VERSION_22C12E = "22C-12E";
const NETWORK_STREAM_RUNTIME_VERSION_22C12D = "22C-11B";
const NETWORK_STREAM_IDLE_AFTER_LAST_BATCH_MS_22C12D = 5_000;
const NETWORK_STREAM_HARD_TIMEOUT_MS_22C12D = 30_000;
const NETWORK_PROBE_RUNTIME_BUILD_ID_22C12AR3 = "22C-12A-R3";
const ENABLE_SCAN_DEBUG_INSTRUMENTATION = false;
const NETWORK_PROBE_READY_EVENT_22C12AR3 = "REUP_DOUYIN_NETWORK_PROBE_READY_22C12A_R3";
const NETWORK_PROBE_BATCH_EVENT_22C12AR3 = "REUP_DOUYIN_NETWORK_AWEME_BATCH_22C12A_R3";
const CONTENT_SCRIPT_SUPPORTED_HANDLERS = [
  "DOUYIN_SCANNER_PING",
  RUNTIME_AUTHORITY_SNAPSHOT_MESSAGE_22C11B,
  "DOUYIN_NETWORK_PROBE_STATUS_22C12A_R3",
  "DOUYIN_PROFILE_DOM_PROBE",
  MANUAL_PAGINATION_TRUTH_TEST_MESSAGE_22C13A,
  "DOUYIN_SCAN_PROFILE_MINIMAL_22C11B_PING",
  "DOUYIN_SCAN_PROFILE_MINIMAL_22C11B",
  "DOUYIN_SCAN_PROFILE_POST_PAGE_22C14B",
  "DOUYIN_HYBRID_TAIL_GAP_DOM_SCROLL_PROBE"
] as const;
const MODAL_TEST_SCAN_DEBUG_PREFIX = "[reup-douyin][modal-test-profile-scan]";

let bridgedNetworkItems: NetworkVideoMetadata[] = [];
let harvestRuntimeSnapshot: HarvestRuntimeV2State = createIdleHarvestRuntimeV2();
let harvestProgress: FullModalHarvestProgress = runtimeV2ToProgress(createIdleHarvestRuntimeV2());
let passiveNetworkProbeSummary22C12A: PassiveNetworkProbeSummary22C12A = createPassiveNetworkProbeSummary22C12A();
let passiveNetworkProbePersistTimer22C12A: ReturnType<typeof setTimeout> | null = null;
let passiveNetworkProbeInitialized22C12A = false;
let passiveNetworkProbeReadyTimeout22C12A: ReturnType<typeof setTimeout> | null = null;
const passiveNetworkProbeTargetsByKind22C12A: Record<PassiveNetworkProbeEndpointKind22C12A, Map<string, PassiveNetworkProbeStoredTarget22C12A>> = {
  profile_post: new Map<string, PassiveNetworkProbeStoredTarget22C12A>(),
  favorite: new Map<string, PassiveNetworkProbeStoredTarget22C12A>(),
  other_aweme_list: new Map<string, PassiveNetworkProbeStoredTarget22C12A>()
};
const passiveNetworkProbePostCursorSamples22C12A: Array<string | number> = [];
const passiveNetworkProbePostCursorFieldSamples22C12BR2: PassiveNetworkProbeCursorFields22C12BR2[] = [];
let passiveNetworkProbePostHasMoreState22C12A: boolean | null = null;
let passiveNetworkProbeProfilePostBatchCount22C12BR2 = 0;
let passiveNetworkProbeProfilePostLastBatchAt22C12BR2: string | null = null;
let passiveNetworkProbeProfilePostLastNewIdAt22C12BR2: string | null = null;

type SafeHarvestRunner = {
  runId: string | null;
  abortController: AbortController | null;
  isRunning: boolean;
  start(message: ExtensionMessage): Promise<FullModalHarvestProgress>;
  resume(message: ExtensionMessage): Promise<FullModalHarvestProgress>;
  stop(): Promise<FullModalHarvestProgress>;
  drainQueue(runId: string): Promise<void>;
};

declare global {
  interface Window {
    __REUP_DOUYIN_SAFE_HARVEST_RUNNER?: SafeHarvestRunner;
    __REUP_DOUYIN_HARVEST_RUNNER_V2?: SafeHarvestRunner;
    __REUP_TRACE_PAGINATION_22C12C__?: boolean;
    __REUP_PAGINATION_DEBUG_22C12C__?: {
      printScrollContainers(): unknown;
      printLastPostBatch(): unknown;
      printIntersectionTargets(): unknown;
      simulateWheelBurst(): Promise<unknown>;
      simulateContainerScroll(): Promise<unknown>;
      dumpPaginationTimeline(): unknown;
    };
    __REUP_NETWORK_STREAM_22C12D__?: LiveNetworkStreamRuntime22C12D;
    __REUP_RUNTIME_AUTHORITY_22C11B__?: RuntimeAuthority22C11B;
    __REUP_MANUAL_PAGINATION_VERIFIER_22C13A__?: { runManualPaginationTruthTest(): Promise<Record<string, unknown>>; dumpManualPaginationTruth(): Record<string, unknown>; runExperiment(id: string): Promise<Record<string, unknown>> };
    __REUP_MANUAL_PARITY_TRACE_22C12E__?: ManualParityTraceRuntime22C12E;
    __REUP_DEBUG_PAGINATION_22C12E__?: PaginationDebugRuntime22C12E;
  }
}

type LiveNetworkStreamBatch22C12D = {
  batchId: string;
  emittedAt: string;
  endpoint_kind: PassiveNetworkProbeEndpointKind22C12A;
  endpoint_path: string;
  awemeCount: number;
  newAwemeCount: number;
  cursor: string | number | null;
  hasMore: boolean | null;
};

type LiveNetworkStreamTarget22C12D = {
  aweme_id: string;
  endpoint_kind: PassiveNetworkProbeEndpointKind22C12A;
  source_url: string;
  captured_at: string;
};

type LiveNetworkStreamEvent22C12D = { batch: LiveNetworkStreamBatch22C12D; targets: LiveNetworkStreamTarget22C12D[] };
type LiveNetworkStreamListener22C12D = (event: LiveNetworkStreamEvent22C12D) => void;

type ManualParityTraceRuntime22C12E = {
  printInteractionTimeline(): unknown;
  printLastPostRequest(): unknown;
  printContainerMatrix(): unknown;
  printSentinelAnalysis(): unknown;
  printHumanVsSyntheticDiff(): unknown;
  runExperiment(id: string): Promise<unknown>;
  dumpActivationFingerprint(): unknown;
  printRuntimeState(): unknown;
};

type PaginationDebugRuntime22C12E = ManualParityTraceRuntime22C12E;

type ActivationTraceEvent22C12E = {
  at: number;
  iso: string;
  type: string;
  source: "human_or_page" | "synthetic_experiment" | "network" | "observer";
  target: string;
  scrollY: number;
  activeElement: string;
  visibilityState: DocumentVisibilityState;
  focus: boolean;
  deltaY?: number;
  deltaX?: number;
  key?: string;
  pointerType?: string;
};

type ActivationPostRequestTrace22C12E = Record<string, unknown> & {
  request_started_at: string;
  request_completed_at: string;
  pre_post_request_event_sequence: string[];
};

const activationTruthProbeState22C12E: {
  installed: boolean;
  events: ActivationTraceEvent22C12E[];
  velocitySamples: Record<string, unknown>[];
  pointerTargetSamples: Record<string, unknown>[];
  focusStateTimeline: Record<string, unknown>[];
  visibilityStateTimeline: Record<string, unknown>[];
  containerActivity: Record<string, unknown>[];
  containerMatrix: Record<string, unknown>[];
  activeContainerConfidenceScores: Record<string, unknown>[];
  likelyPaginationContainer: Record<string, unknown> | null;
  likelyVirtualizedContainer: Record<string, unknown> | null;
  likelyIntersectionSentinelContainer: Record<string, unknown> | null;
  intersectionObserverCount: number;
  intersectionTargets: Map<string, Record<string, unknown>>;
  intersectionEvents: Record<string, unknown>[];
  probableBottomSentinelDetected: boolean;
  probableVirtualizationBoundaryDetected: boolean;
  mutationBurstCount: number;
  requestTimeline: ActivationPostRequestTrace22C12E[];
  experimentResults: Record<string, unknown>[];
  syntheticExperimentEventTypes: Set<string>;
  lastRafBurstAt: number | null;
} = { installed: false, events: [], velocitySamples: [], pointerTargetSamples: [], focusStateTimeline: [], visibilityStateTimeline: [], containerActivity: [], containerMatrix: [], activeContainerConfidenceScores: [], likelyPaginationContainer: null, likelyVirtualizedContainer: null, likelyIntersectionSentinelContainer: null, intersectionObserverCount: 0, intersectionTargets: new Map(), intersectionEvents: [], probableBottomSentinelDetected: false, probableVirtualizationBoundaryDetected: false, mutationBurstCount: 0, requestTimeline: [], experimentResults: [], syntheticExperimentEventTypes: new Set(), lastRafBurstAt: null };

function pushBounded22C12E<T>(items: T[], item: T, limit: number): void {
  items.push(item);
  while (items.length > limit) items.shift();
}

type LiveNetworkStreamRuntime22C12D = {
  subscribe(listener: LiveNetworkStreamListener22C12D): () => void;
  unsubscribe(listener: LiveNetworkStreamListener22C12D): void;
  getState(): Record<string, unknown>;
  getRecentBatches(): LiveNetworkStreamBatch22C12D[];
  getRecentTargets(): LiveNetworkStreamTarget22C12D[];
  emit(batch: PassiveNetworkProbeBatchMessage22C12A, endpointKind: PassiveNetworkProbeEndpointKind22C12A, endpointPath: string, capturedAt: string, newAwemeCount: number): LiveNetworkStreamEvent22C12D;
};

type RuntimeHealthStatus22C11B = "healthy" | "degraded" | "disconnected" | "stale_authority_detected" | "bridge_inconsistent";
type RuntimeAuthorityDomain22C11B = "scan" | "collector" | "network_stream" | "popup_diagnostics" | "content" | "controller" | "probe" | "tab" | "queue";
type RuntimeAuthoritySnapshot22C11B = Record<string, unknown> & {
  runtime_authority_version: string;
  diagnostics_runtime_version: string;
  scanner_runtime_version: string;
  state_machine_version: string;
  scan_controller_version: string;
  runtime_health_status: RuntimeHealthStatus22C11B;
  runtime_health_reasons: string[];
  disconnected_runtime_domains: string[];
  stale_authority_domains: string[];
};
type RuntimeAuthority22C11B = {
  updateDomain(domain: RuntimeAuthorityDomain22C11B, patch: Record<string, unknown>): RuntimeAuthoritySnapshot22C11B;
  getRuntimeSnapshot(): RuntimeAuthoritySnapshot22C11B;
  subscribe(listener: (snapshot: RuntimeAuthoritySnapshot22C11B) => void): () => void;
};

const liveNetworkStreamSeenTargetIds22C12D = new Set<string>();
const liveNetworkStreamBatches22C12D: LiveNetworkStreamBatch22C12D[] = [];
const liveNetworkStreamTargets22C12D: LiveNetworkStreamTarget22C12D[] = [];
const liveNetworkStreamSubscribers22C12D = new Set<LiveNetworkStreamListener22C12D>();
let liveNetworkStreamTotalTargets22C12D = 0;
let liveNetworkStreamLastEmitAt22C12D: string | null = null;
let liveNetworkStreamNextBatchId22C12D = 1;

void ensureRuntimeV2Initialized();

const EXTENSION_API_AUTH_TOKEN_STORAGE_KEY = "reup_douyin_api_auth_token";
const EXTENSION_AUTH_TOKEN_BRIDGE_EVENT = "REUP_DOUYIN_API_AUTH_TOKEN_SYNC";
const EXTENSION_AUTH_TOKEN_STORAGE_KEY = "apiAuthToken";

window.addEventListener("message", (event: MessageEvent<{ type?: string; storageKey?: string; token?: string | null; syncedAt?: string }>) => {
  if (event.source !== window || event.origin !== window.location.origin) return;
  if (event.data?.type !== EXTENSION_AUTH_TOKEN_BRIDGE_EVENT) return;
  if (event.data.storageKey !== EXTENSION_API_AUTH_TOKEN_STORAGE_KEY) return;
  const token = typeof event.data.token === "string" && event.data.token.trim() ? event.data.token.trim() : null;
  const syncedAt = event.data.syncedAt ?? new Date().toISOString();
  void chrome.storage.local.set(token
    ? { [EXTENSION_AUTH_TOKEN_STORAGE_KEY]: token, apiAuthTokenSyncedAt: syncedAt, apiAuthTokenSource: "web_local_storage_bridge", apiAuthRequired: false }
    : { [EXTENSION_AUTH_TOKEN_STORAGE_KEY]: "", apiAuthTokenSyncedAt: syncedAt, apiAuthTokenSource: "web_local_storage_bridge_logout", apiAuthRequired: true });
});

window.addEventListener("message", (event: MessageEvent<NetworkCacheMessage>) => {
  if (event.source !== window || event.origin !== window.location.origin) return;
  if (event.data?.type !== "REUP_DOUYIN_NETWORK_CACHE_UPDATE") return;
  if (!Array.isArray(event.data.items)) return;
  bridgedNetworkItems = mergeNetworkCacheItems(event.data.items.slice(0, 240));
});

window.addEventListener("message", (event: MessageEvent<PassiveNetworkProbeBatchMessage22C12A | { type?: string; traceVersion?: string }>) => {
  if (event.source !== window || event.origin !== window.location.origin) return;
  if (event.data?.type === NETWORK_PROBE_READY_EVENT_22C12AR3) {
    if (passiveNetworkProbeReadyTimeout22C12A) {
      clearTimeout(passiveNetworkProbeReadyTimeout22C12A);
      passiveNetworkProbeReadyTimeout22C12A = null;
    }
    passiveNetworkProbeSummary22C12A = markPassiveNetworkProbeReady22C12A(passiveNetworkProbeSummary22C12A, new Date().toISOString());
    schedulePassiveNetworkProbePersistence22C12A();
    return;
  }
  if (event.data?.type !== NETWORK_PROBE_BATCH_EVENT_22C12AR3) return;
  const batch = event.data as PassiveNetworkProbeBatchMessage22C12A;
  if (!Array.isArray(batch.targets) || typeof batch.urlPath !== "string") return;
  recordPassiveNetworkProbeBatch22C12A(batch);
});

function installPaginationReverseEngineering22C12C(): void {
  const state = paginationTraceState22C12C;
  const addEvent = (entry: Record<string, unknown>) => {
    if (!window.__REUP_TRACE_PAGINATION_22C12C__) return;
    state.events.push({ at: Date.now(), ...entry });
    while (state.events.length > 160) state.events.shift();
  };
  const scan = () => {
    const candidates = detectScrollContainers22C12C();
    state.scrollContainers = candidates;
    const active = candidates.find((item) => item.changed) ?? candidates.find((item) => !item.active_scroll_container_is_window) ?? candidates[0] ?? null;
    state.activeScrollContainer = active;
    return candidates;
  };
  ["scroll", "wheel", "pointermove", "pointerdown", "resize", "visibilitychange"].forEach((type) => {
    window.addEventListener(type, (event) => {
      scan();
      const wheel = event instanceof WheelEvent ? { deltaY: event.deltaY, deltaX: event.deltaX } : {};
      addEvent({ type, target: selectorForElement22C12C(event.target), scrollY: window.scrollY, ...wheel });
    }, { capture: true, passive: true });
  });
  const mutationObserver = new MutationObserver((mutations) => {
    const gridNear = findProfileGridRoot22C12C();
    const count = mutations.filter((mutation) => !gridNear || mutation.target === gridNear || gridNear.contains(mutation.target)).length;
    state.mutationBurstCount += count;
    addEvent({ type: "mutation", mutation_count: count });
  });
  mutationObserver.observe(document.documentElement, { childList: true, subtree: true, attributes: true });
  const OriginalIntersectionObserver = window.IntersectionObserver;
  window.IntersectionObserver = class ReupIntersectionObserver22C12C extends OriginalIntersectionObserver {
    constructor(callback: IntersectionObserverCallback, options?: IntersectionObserverInit) {
      const observerId = ++state.intersectionObserverCount;
      super((entries, observer) => {
        for (const entry of entries) {
          const targetSelector = selectorForElement22C12C(entry.target);
          state.intersectionTargets.set(targetSelector, { observerId, selector: targetSelector, ratio: entry.intersectionRatio, isIntersecting: entry.isIntersecting, at: new Date().toISOString() });
          if (isLikelyBottomSentinel22C12C(entry.target)) {
            state.bottomSentinelDetected = true;
            state.sentinelVisibilityChanges += 1;
            state.sentinelLastIntersectionRatio = entry.intersectionRatio;
          }
        }
        addEvent({ type: "intersection", observer_id: observerId, entry_count: entries.length, bottom_sentinel_detected: state.bottomSentinelDetected });
        callback(entries, observer);
      }, options);
      state.intersectionOptions.push({ observerId, threshold: JSON.stringify(options?.threshold ?? null), root: selectorForElement22C12C(options?.root ?? null) });
    }
    observe(target: Element): void {
      state.intersectionTargets.set(selectorForElement22C12C(target), { selector: selectorForElement22C12C(target), observed: true, at: new Date().toISOString() });
      return super.observe(target);
    }
  };
  window.__REUP_PAGINATION_DEBUG_22C12C__ = {
    printScrollContainers: () => scan(),
    printLastPostBatch: () => state.networkPostCursorTimeline.at(-1) ?? null,
    printIntersectionTargets: () => Array.from(state.intersectionTargets.values()).slice(-40),
    simulateWheelBurst: () => runPaginationExperiment22C12C("window_wheel_burst", () => window.dispatchEvent(new WheelEvent("wheel", { deltaY: 900, bubbles: true, cancelable: true }))),
    simulateContainerScroll: () => runPaginationExperiment22C12C("active_container_scrollTop_mutation", () => { const target = resolveActiveScrollElement22C12C(); if (target) target.scrollTop += 900; else window.scrollBy(0, 900); }),
    dumpPaginationTimeline: () => getPaginationReverseEngineeringDiagnostics22C12C()
  };
  scan();
}

type PaginationTraceEvent22C12C = { at: number; [key: string]: unknown };
type ScrollContainerDiagnostic22C12C = Record<string, unknown> & { active_scroll_container_selector: string; active_scroll_container_is_window: boolean; changed?: boolean };
const paginationTraceState22C12C: {
  events: PaginationTraceEvent22C12C[];
  scrollContainers: ScrollContainerDiagnostic22C12C[];
  activeScrollContainer: ScrollContainerDiagnostic22C12C | null;
  scrollPositions: Map<string, number>;
  intersectionObserverCount: number;
  intersectionOptions: Record<string, unknown>[];
  intersectionTargets: Map<string, Record<string, unknown>>;
  bottomSentinelDetected: boolean;
  sentinelVisibilityChanges: number;
  sentinelLastIntersectionRatio: number | null;
  mutationBurstCount: number;
  networkPostCursorTimeline: Record<string, unknown>[];
  networkPostHasMoreTimeline: Array<boolean | null>;
  networkPostBatchSizes: number[];
  experimentResults: Record<string, unknown>[];
} = { events: [], scrollContainers: [], activeScrollContainer: null, scrollPositions: new Map(), intersectionObserverCount: 0, intersectionOptions: [], intersectionTargets: new Map(), bottomSentinelDetected: false, sentinelVisibilityChanges: 0, sentinelLastIntersectionRatio: null, mutationBurstCount: 0, networkPostCursorTimeline: [], networkPostHasMoreTimeline: [], networkPostBatchSizes: [], experimentResults: [] };

type ManualPaginationRequest22C13A = Record<string, unknown> & { request_index: number; request_url: string; cursor: string | number | null; max_cursor: string | number | null; has_more: boolean | null; unique_aweme_count: number; request_timing_ms: number; trigger_source_timing: string[] };
const manualPaginationTruthState22C13A: { startedAtMs: number | null; firstRequestAtMs: number | null; lastRequestAtMs: number | null; requests: ManualPaginationRequest22C13A[]; uniqueAwemeIds: Set<string>; manualWheelSamples: Record<string, unknown>[]; syntheticSamples: Record<string, unknown>[]; containerSnapshots: Record<string, unknown>[]; experimentResults: Record<string, unknown>[]; manualScrollActive: boolean } = { startedAtMs: null, firstRequestAtMs: null, lastRequestAtMs: null, requests: [], uniqueAwemeIds: new Set(), manualWheelSamples: [], syntheticSamples: [], containerSnapshots: [], experimentResults: [], manualScrollActive: false };

function resetManualPaginationTruthState22C13A(): void {
  manualPaginationTruthState22C13A.startedAtMs = Date.now();
  manualPaginationTruthState22C13A.firstRequestAtMs = null;
  manualPaginationTruthState22C13A.lastRequestAtMs = null;
  manualPaginationTruthState22C13A.requests = [];
  manualPaginationTruthState22C13A.uniqueAwemeIds = new Set();
  manualPaginationTruthState22C13A.manualWheelSamples = [];
  manualPaginationTruthState22C13A.syntheticSamples = [];
  manualPaginationTruthState22C13A.containerSnapshots = [];
  manualPaginationTruthState22C13A.experimentResults = [];
  manualPaginationTruthState22C13A.manualScrollActive = true;
}

function recordManualPaginationPostRequest22C13A(batch: PassiveNetworkProbeBatchMessage22C12A, endpointKind: PassiveNetworkProbeEndpointKind22C12A, at: string): void {
  if (endpointKind !== "profile_post") return;
  const nowMs = Date.now();
  if (manualPaginationTruthState22C13A.startedAtMs == null) manualPaginationTruthState22C13A.startedAtMs = nowMs;
  if (manualPaginationTruthState22C13A.firstRequestAtMs == null) manualPaginationTruthState22C13A.firstRequestAtMs = nowMs;
  manualPaginationTruthState22C13A.lastRequestAtMs = nowMs;
  for (const target of batch.targets) manualPaginationTruthState22C13A.uniqueAwemeIds.add(target.aweme_id);
  const cursorFields = batch.cursorFields ?? null;
  const recent = activationTruthProbeState22C12E.events.filter((event) => nowMs - event.at <= 3_000).slice(-20);
  manualPaginationTruthState22C13A.requests.push({ request_index: manualPaginationTruthState22C13A.requests.length + 1, request_url: batch.urlPath, cursor: batch.cursor, max_cursor: cursorFields?.max_cursor ?? null, has_more: batch.hasMore, unique_aweme_count: batch.targets.length, request_timing_ms: nowMs - (manualPaginationTruthState22C13A.startedAtMs ?? nowMs), trigger_source_timing: recent.map((event) => `${event.source}:${event.type}`) });
  while (manualPaginationTruthState22C13A.requests.length > 20) manualPaginationTruthState22C13A.requests.shift();
}

function snapshotScrollContainerTruth22C13A(source: "manual" | "synthetic" | "inspection"): Record<string, unknown>[] {
  const matrix = detectScrollContainers22C12C().map((item) => ({ selector: item.active_scroll_container_selector, tag: item.active_scroll_container_tag, overflow_style: item.active_scroll_container_overflow, current_scrollTop: item.active_scroll_container_scrollTop, scrollHeight: item.active_scroll_container_scrollHeight, clientHeight: item.active_scroll_container_clientHeight, scrollTop_changes_during_real_manual_scroll: source === "manual" ? Boolean(item.changed) : null, scrollTop_changes_during_extension_synthetic_scroll: source === "synthetic" ? Boolean(item.changed) : null, request_emission_correlates: manualPaginationTruthState22C13A.requests.length > 1 && Boolean(item.changed) }));
  manualPaginationTruthState22C13A.containerSnapshots.push({ at: new Date().toISOString(), source, matrix: matrix.slice(0, 12) });
  while (manualPaginationTruthState22C13A.containerSnapshots.length > 20) manualPaginationTruthState22C13A.containerSnapshots.shift();
  return matrix;
}

function getManualPaginationTruthDiagnostics22C13A(): Record<string, unknown> {
  const requests = manualPaginationTruthState22C13A.requests;
  const realMoving = [...manualPaginationTruthState22C13A.containerSnapshots].reverse().find((item) => item.source === "manual") as Record<string, unknown> | undefined;
  const syntheticMoving = [...manualPaginationTruthState22C13A.containerSnapshots].reverse().find((item) => item.source === "synthetic") as Record<string, unknown> | undefined;
  const findMoving = (snapshot: Record<string, unknown> | undefined) => Array.isArray(snapshot?.matrix) ? (snapshot.matrix as Record<string, unknown>[]).find((item) => item.scrollTop_changes_during_real_manual_scroll === true || item.scrollTop_changes_during_extension_synthetic_scroll === true) ?? null : null;
  const realContainer = findMoving(realMoving);
  const syntheticContainer = findMoving(syntheticMoving);
  const triggeredPage2 = requests.length >= 2;
  const triggeredPage3 = requests.length >= 3;
  return { scanner_runtime_version: PAGINATION_VERIFICATION_VERSION_22C13A, pagination_verification_version: PAGINATION_VERIFICATION_VERSION_22C13A, active_scan_profile_engine: "live_network_stream_profile_collector_22C13A", scan_profile_pipeline_lock: SCAN_PROFILE_PIPELINE_LOCK_22C13A, manual_scroll_generated_additional_post_requests: triggeredPage2 ? "yes" : "no", manual_scroll_post_request_count: requests.length, manual_scroll_cursor_progression: requests.map((item) => item.cursor ?? item.max_cursor ?? null), manual_scroll_has_more_progression: requests.map((item) => item.has_more), manual_scroll_total_unique_aweme_count: manualPaginationTruthState22C13A.uniqueAwemeIds.size, manual_scroll_triggered_page_2: triggeredPage2 ? "yes" : "no", manual_scroll_triggered_page_3: triggeredPage3 ? "yes" : "no", post_request_sequence: requests, post_request_cursor_chain: requests.map((item) => item.cursor ?? item.max_cursor ?? null), post_request_has_more_chain: requests.map((item) => item.has_more), post_request_unique_counts: requests.map((item) => item.unique_aweme_count), real_moving_scroll_container: realContainer, synthetic_moving_scroll_container: syntheticContainer, container_scroll_correlation: manualPaginationTruthState22C13A.containerSnapshots.slice(-8), likely_real_pagination_container: realContainer ?? syntheticContainer, synthetic_missing_signal: triggeredPage2 ? "no" : "undetermined_until_manual_scroll", synthetic_missing_momentum: manualPaginationTruthState22C13A.syntheticSamples.length > 0 && requests.length < 2 ? "possible" : "unknown", synthetic_wrong_container: realContainer && syntheticContainer && realContainer.selector !== syntheticContainer.selector ? "yes" : "unknown", synthetic_wrong_focus_target: "unknown", synthetic_request_failure_reason: triggeredPage2 ? null : "no_additional_post_request_observed_yet", pagination_activation_results: manualPaginationTruthState22C13A.experimentResults, final_manual_pagination_case: triggeredPage2 ? "CASE_A" : "CASE_B" };
}

async function runManualPaginationTruthTest(): Promise<Record<string, unknown>> {
  resetManualPaginationTruthState22C13A();
  snapshotScrollContainerTruth22C13A("inspection");
  const started = Date.now();
  while (Date.now() - started < 20_000) {
    snapshotScrollContainerTruth22C13A("manual");
    const idleMs = manualPaginationTruthState22C13A.lastRequestAtMs == null ? 0 : Date.now() - manualPaginationTruthState22C13A.lastRequestAtMs;
    if (manualPaginationTruthState22C13A.requests.length >= 1 && idleMs >= 20_000) break;
    await new Promise((resolve) => setTimeout(resolve, 1_000));
  }
  manualPaginationTruthState22C13A.manualScrollActive = false;
  const diagnostics = getManualPaginationTruthDiagnostics22C13A();
  updateRuntimeAuthority22C11B("controller", diagnostics);
  return diagnostics;
}

async function runPaginationActivationExperiment22C13A(id: "real_wheel_cadence_replay" | "scroll_real_container" | "scroll_into_view_last_visible_card" | "pointer_movement_wheel_combined"): Promise<Record<string, unknown>> {
  const beforeRequests = manualPaginationTruthState22C13A.requests.length;
  const beforeCursor = manualPaginationTruthState22C13A.requests.at(-1)?.cursor ?? null;
  const active = resolveActiveScrollElement22C12C();
  if (id === "real_wheel_cadence_replay") [180, 220, 260, 180].forEach((deltaY, index) => setTimeout(() => window.dispatchEvent(new WheelEvent("wheel", { deltaY, bubbles: true, cancelable: true })), index * 140));
  if (id === "scroll_real_container") { if (active) active.scrollTop += Math.max(active.clientHeight * 0.8, 480); else window.scrollBy(0, Math.max(window.innerHeight * 0.8, 480)); }
  if (id === "scroll_into_view_last_visible_card") Array.from(document.querySelectorAll('a[href*="/video/"]')).at(-1)?.scrollIntoView({ block: "end", behavior: "auto" });
  if (id === "pointer_movement_wheel_combined") { window.dispatchEvent(new PointerEvent("pointermove", { bubbles: true, pointerType: "mouse" })); window.dispatchEvent(new WheelEvent("wheel", { deltaY: 320, bubbles: true, cancelable: true })); }
  manualPaginationTruthState22C13A.syntheticSamples.push({ at: new Date().toISOString(), id, activeElement: selectorForElement22C12C(document.activeElement) });
  await new Promise((resolve) => setTimeout(resolve, 1_800));
  snapshotScrollContainerTruth22C13A("synthetic");
  const after = manualPaginationTruthState22C13A.requests.at(-1);
  const result = { experiment: id, emitted_new_post_request: manualPaginationTruthState22C13A.requests.length > beforeRequests ? "yes" : "no", new_unique_aweme_count: manualPaginationTruthState22C13A.uniqueAwemeIds.size, cursor_progressed: (after?.cursor ?? null) !== beforeCursor ? "yes" : "no", has_more_progressed: after?.has_more ?? null };
  manualPaginationTruthState22C13A.experimentResults.push(result);
  return result;
}

function installManualPaginationVerifier22C13A(): void {
  window.__REUP_MANUAL_PAGINATION_VERIFIER_22C13A__ = { runManualPaginationTruthTest, dumpManualPaginationTruth: getManualPaginationTruthDiagnostics22C13A, runExperiment: (id: string) => runPaginationActivationExperiment22C13A(id as "real_wheel_cadence_replay" | "scroll_real_container" | "scroll_into_view_last_visible_card" | "pointer_movement_wheel_combined") };
}

function recordPaginationPostBatch22C12C(batch: PassiveNetworkProbeBatchMessage22C12A, endpointKind: PassiveNetworkProbeEndpointKind22C12A, at: string): void {
  if (endpointKind !== "profile_post") return;
  const previousEvents = paginationTraceState22C12C.events.filter((event) => Date.now() - event.at <= 2_000).slice(-24);
  const cursorFields = batch.cursorFields ?? null;
  const item = { request_timestamp: at, cursor: batch.cursor, has_more: batch.hasMore, max_cursor: cursorFields?.max_cursor ?? null, min_cursor: cursorFields?.min_cursor ?? null, offset: cursorFields?.offset ?? null, list_length: batch.awemeCount, preceding_events: previousEvents.map((event) => event.type), scroll_container: paginationTraceState22C12C.activeScrollContainer?.active_scroll_container_selector ?? null, mutation_count: paginationTraceState22C12C.mutationBurstCount };
  recordManualPaginationPostRequest22C13A(batch, endpointKind, at);
  paginationTraceState22C12C.networkPostCursorTimeline.push(item);
  while (paginationTraceState22C12C.networkPostCursorTimeline.length > 20) paginationTraceState22C12C.networkPostCursorTimeline.shift();
  paginationTraceState22C12C.networkPostHasMoreTimeline.push(batch.hasMore);
  while (paginationTraceState22C12C.networkPostHasMoreTimeline.length > 20) paginationTraceState22C12C.networkPostHasMoreTimeline.shift();
  paginationTraceState22C12C.networkPostBatchSizes.push(batch.awemeCount);
  while (paginationTraceState22C12C.networkPostBatchSizes.length > 20) paginationTraceState22C12C.networkPostBatchSizes.shift();
}

function getPaginationReverseEngineeringDiagnostics22C12C(): Record<string, unknown> {
  const active = paginationTraceState22C12C.activeScrollContainer;
  return {
    scanner_runtime_version: PAGINATION_TRACE_VERSION_22C12C,
    pagination_trace_version: PAGINATION_TRACE_VERSION_22C12C,
    pagination_reverse_engineering: "active",
    active_scroll_container_selector: active?.active_scroll_container_selector ?? null,
    active_scroll_container_tag: active?.active_scroll_container_tag ?? null,
    active_scroll_container_scrollTop: active?.active_scroll_container_scrollTop ?? null,
    active_scroll_container_scrollHeight: active?.active_scroll_container_scrollHeight ?? null,
    active_scroll_container_clientHeight: active?.active_scroll_container_clientHeight ?? null,
    active_scroll_container_overflow: active?.active_scroll_container_overflow ?? null,
    active_scroll_container_is_window: active?.active_scroll_container_is_window ?? null,
    candidate_scroll_container_count: paginationTraceState22C12C.scrollContainers.length,
    intersection_observer_count: paginationTraceState22C12C.intersectionObserverCount,
    profile_grid_intersection_targets: Array.from(paginationTraceState22C12C.intersectionTargets.values()).slice(-20),
    bottom_sentinel_detected: paginationTraceState22C12C.bottomSentinelDetected ? "yes" : "no",
    sentinel_visibility_changes: paginationTraceState22C12C.sentinelVisibilityChanges,
    sentinel_last_intersection_ratio: paginationTraceState22C12C.sentinelLastIntersectionRatio,
    post_batch_trigger_event_sequence: paginationTraceState22C12C.networkPostCursorTimeline.at(-1)?.preceding_events ?? [],
    post_batch_trigger_scroll_container: paginationTraceState22C12C.networkPostCursorTimeline.at(-1)?.scroll_container ?? null,
    post_batch_trigger_mutation_count: paginationTraceState22C12C.networkPostCursorTimeline.at(-1)?.mutation_count ?? 0,
    network_post_cursor_timeline: paginationTraceState22C12C.networkPostCursorTimeline,
    network_post_has_more_timeline: paginationTraceState22C12C.networkPostHasMoreTimeline,
    network_post_batch_sizes: paginationTraceState22C12C.networkPostBatchSizes,
    pagination_activation_experiment_results: paginationTraceState22C12C.experimentResults
  };
}

async function runPaginationExperiment22C12C(name: string, action: () => void): Promise<Record<string, unknown>> {
  const beforeCount = passiveNetworkProbeProfilePostBatchCount22C12BR2;
  const beforeCursor = passiveNetworkProbePostCursorSamples22C12A.at(-1) ?? null;
  const beforeMutations = paginationTraceState22C12C.mutationBurstCount;
  action();
  await new Promise((resolve) => setTimeout(resolve, 1200));
  const result = { experiment: name, at: new Date().toISOString(), new_post_batch_emitted: passiveNetworkProbeProfilePostBatchCount22C12BR2 > beforeCount ? "yes" : "no", cursor_changed: (passiveNetworkProbePostCursorSamples22C12A.at(-1) ?? null) !== beforeCursor ? "yes" : "no", has_more: passiveNetworkProbePostHasMoreState22C12A, mutation_burst_occurred: paginationTraceState22C12C.mutationBurstCount > beforeMutations ? "yes" : "no" };
  paginationTraceState22C12C.experimentResults.push(result);
  while (paginationTraceState22C12C.experimentResults.length > 12) paginationTraceState22C12C.experimentResults.shift();
  schedulePassiveNetworkProbePersistence22C12A();
  return result;
}

function recordActivationTraceEvent22C12E(event: Event | { type: string; target?: EventTarget | null; synthetic?: boolean }, source: ActivationTraceEvent22C12E["source"] = "human_or_page"): void {
  const at = Date.now();
  const previous = activationTruthProbeState22C12E.events.at(-1);
  const wheel = event instanceof WheelEvent ? { deltaY: event.deltaY, deltaX: event.deltaX } : {};
  const pointer = event instanceof PointerEvent ? { pointerType: event.pointerType } : {};
  const keyboard = event instanceof KeyboardEvent ? { key: event.key } : {};
  const target = event instanceof Event ? event.target : event.target;
  const entry: ActivationTraceEvent22C12E = { at, iso: new Date(at).toISOString(), type: event.type, source, target: selectorForElement22C12C(target), scrollY: window.scrollY, activeElement: selectorForElement22C12C(document.activeElement), visibilityState: document.visibilityState, focus: document.hasFocus(), ...wheel, ...pointer, ...keyboard };
  pushBounded22C12E(activationTruthProbeState22C12E.events, entry, 240);
  if (event.type.includes("pointer") || event.type.includes("mouse")) pushBounded22C12E(activationTruthProbeState22C12E.pointerTargetSamples, { at: entry.iso, type: event.type, target: entry.target, pointerType: entry.pointerType ?? null }, 80);
  if (["focus", "blur", "focusin", "focusout"].includes(event.type)) pushBounded22C12E(activationTruthProbeState22C12E.focusStateTimeline, { at: entry.iso, type: event.type, focus: entry.focus, activeElement: entry.activeElement }, 80);
  if (event.type === "visibilitychange") pushBounded22C12E(activationTruthProbeState22C12E.visibilityStateTimeline, { at: entry.iso, visibilityState: entry.visibilityState, focus: entry.focus }, 80);
  if (["scroll", "wheel", "touchmove"].includes(event.type)) {
    const dt = previous ? Math.max(at - previous.at, 1) : 1;
    const dy = entry.scrollY - (previous?.scrollY ?? entry.scrollY);
    pushBounded22C12E(activationTruthProbeState22C12E.velocitySamples, { at: entry.iso, type: event.type, scroll_delta_y: dy, elapsed_ms: dt, velocity_px_per_ms: dy / dt, wheel_delta_y: entry.deltaY ?? null, active_container_selector: activationTruthProbeState22C12E.likelyPaginationContainer?.candidate_selector ?? null }, 80);
  }
}

function detectScrollContainers22C12C(): ScrollContainerDiagnostic22C12C[] {
  const elements: Array<Element | Window> = [window, document.scrollingElement ?? document.documentElement, document.body, document.documentElement, ...Array.from(document.querySelectorAll("main, [class], [data-e2e], [style]"))];
  const unique = Array.from(new Set(elements));
  return unique.flatMap((node) => {
    const element = node === window ? document.scrollingElement ?? document.documentElement : node as Element;
    if (!(element instanceof Element)) return [];
    const style = window.getComputedStyle(element);
    const scrollTop = node === window ? window.scrollY : (element as HTMLElement).scrollTop;
    const scrollHeight = node === window ? document.documentElement.scrollHeight : (element as HTMLElement).scrollHeight;
    const clientHeight = node === window ? window.innerHeight : (element as HTMLElement).clientHeight;
    const selector = node === window ? "window" : selectorForElement22C12C(element);
    const previous = paginationTraceState22C12C.scrollPositions.get(selector);
    paginationTraceState22C12C.scrollPositions.set(selector, scrollTop);
    if (scrollHeight <= clientHeight && node !== window) return [];
    return [{ active_scroll_container_selector: selector, active_scroll_container_tag: node === window ? "window" : element.tagName.toLowerCase(), active_scroll_container_scrollTop: scrollTop, active_scroll_container_scrollHeight: scrollHeight, active_scroll_container_clientHeight: clientHeight, active_scroll_container_overflow: `${style.overflow}/${style.overflowY}`, active_scroll_container_is_window: node === window, changed: previous != null && previous !== scrollTop, transform: style.transform === "none" ? null : style.transform, position: style.position }];
  }).slice(0, 40);
}

function resolveActiveScrollElement22C12C(): HTMLElement | null {
  const selector = paginationTraceState22C12C.activeScrollContainer?.active_scroll_container_selector;
  if (!selector || selector === "window") return null;
  try { return document.querySelector(selector) as HTMLElement | null; } catch { return null; }
}

function findProfileGridRoot22C12C(): Element | null {
  return document.querySelector('[data-e2e*="user-post"], [data-e2e*="profile"], main') ?? document.querySelector('a[href*="/video/"]')?.closest('div') ?? null;
}

function isLikelyBottomSentinel22C12C(target: Element): boolean {
  const rect = target.getBoundingClientRect();
  const grid = findProfileGridRoot22C12C();
  return rect.top >= window.innerHeight * 0.55 || (grid ? grid.contains(target) && rect.height <= 80 : false);
}

function selectorForElement22C12C(value: EventTarget | Element | Document | null | undefined): string {
  if (!value || value === window) return "window";
  const element = value instanceof Element ? value : null;
  if (!element) return "unknown";
  if (element.id) return `#${CSS.escape(element.id)}`;
  const attr = element.getAttribute("data-e2e") || element.getAttribute("data-testid");
  if (attr) return `${element.tagName.toLowerCase()}[data-e2e="${attr.slice(0, 60)}"]`;
  const className = String(element.getAttribute("class") || "").split(/\s+/).filter(Boolean).slice(0, 2).map((part) => `.${CSS.escape(part)}`).join("");
  return `${element.tagName.toLowerCase()}${className}`;
}

function scanActivationContainers22C12E(): Record<string, unknown>[] {
  const previousBySelector = new Map(activationTruthProbeState22C12E.containerMatrix.map((item) => [String(item.candidate_selector), Number(item.scrollTop ?? 0)]));
  const matrix = detectScrollContainers22C12C().map((item) => {
    const selector = String(item.active_scroll_container_selector);
    const scrollTop = Number(item.active_scroll_container_scrollTop ?? 0);
    const scrollHeight = Number(item.active_scroll_container_scrollHeight ?? 0);
    const clientHeight = Number(item.active_scroll_container_clientHeight ?? 0);
    const scrollableDistance = Math.max(scrollHeight - clientHeight, 0);
    const previous = previousBySelector.get(selector);
    const changed = previous != null && previous !== scrollTop;
    const active_container_confidence = (changed ? 40 : 0) + (scrollableDistance > window.innerHeight ? 25 : 0) + (/main|profile|user/i.test(selector) ? 15 : 0) + (scrollTop > 0 ? 10 : 0);
    return { candidate_selector: selector, tag: item.active_scroll_container_tag, scrollTop, scrollHeight, clientHeight, scrollableDistance, overflow: item.active_scroll_container_overflow, changed, active_container_confidence, is_window: item.active_scroll_container_is_window };
  });
  activationTruthProbeState22C12E.containerMatrix = matrix;
  activationTruthProbeState22C12E.activeContainerConfidenceScores = matrix.map((item) => ({ candidate_selector: item.candidate_selector, active_container_confidence: item.active_container_confidence })).sort((left, right) => Number(right.active_container_confidence) - Number(left.active_container_confidence));
  activationTruthProbeState22C12E.likelyPaginationContainer = activationTruthProbeState22C12E.activeContainerConfidenceScores[0] ?? matrix[0] ?? null;
  activationTruthProbeState22C12E.likelyVirtualizedContainer = matrix.find((item) => Number(item.scrollHeight) > Number(item.clientHeight) * 4) ?? null;
  activationTruthProbeState22C12E.likelyIntersectionSentinelContainer = matrix.find((item) => /main|profile|user/i.test(String(item.candidate_selector))) ?? activationTruthProbeState22C12E.likelyPaginationContainer;
  pushBounded22C12E(activationTruthProbeState22C12E.containerActivity, { at: new Date().toISOString(), candidate_count: matrix.length, likely_pagination_container: activationTruthProbeState22C12E.likelyPaginationContainer }, 80);
  return matrix;
}

function recordActivationPostRequest22C12E(batch: PassiveNetworkProbeBatchMessage22C12A, endpointKind: PassiveNetworkProbeEndpointKind22C12A, at: string): void {
  if (endpointKind !== "profile_post") return;
  const requestAt = Date.parse(at);
  const before = activationTruthProbeState22C12E.events.filter((event) => requestAt - event.at <= 5_000 && requestAt >= event.at);
  const intersections = activationTruthProbeState22C12E.intersectionEvents.filter((event) => requestAt - Number(event.at_ms ?? 0) <= 5_000 && requestAt >= Number(event.at_ms ?? 0));
  const velocities = activationTruthProbeState22C12E.velocitySamples.slice(-12);
  const containers = scanActivationContainers22C12E();
  pushBounded22C12E(activationTruthProbeState22C12E.requestTimeline, { request_started_at: at, request_completed_at: at, request_endpoint_path: batch.urlPath, request_cursor: batch.cursor ?? null, request_has_more: batch.hasMore, request_aweme_count: batch.awemeCount, interaction_events_before_request: before.length, scroll_activity_before_request: before.filter((event) => ["scroll", "wheel", "touchmove"].includes(event.type)).length, intersection_events_before_request: intersections.length, mutation_burst_before_request: activationTruthProbeState22C12E.mutationBurstCount, focus_state_before_request: document.hasFocus() ? "focused" : "not_focused", visibility_state_before_request: document.visibilityState, container_scroll_delta_before_request: velocities.reduce((sum, item) => sum + Math.abs(Number(item.scroll_delta_y ?? 0)), 0), pre_post_request_event_sequence: before.map((event) => event.type).slice(-40), pre_post_request_scroll_activity: before.filter((event) => ["scroll", "wheel", "touchmove"].includes(event.type)).slice(-20), pre_post_request_pointer_activity: before.filter((event) => event.type.includes("pointer") || event.type.includes("mouse")).slice(-20), pre_post_request_focus_state: activationTruthProbeState22C12E.focusStateTimeline.at(-1) ?? { focus: document.hasFocus(), activeElement: selectorForElement22C12C(document.activeElement) }, pre_post_request_visibility_state: activationTruthProbeState22C12E.visibilityStateTimeline.at(-1) ?? { visibilityState: document.visibilityState }, pre_post_request_intersection_changes: intersections.slice(-20), pre_post_request_mutation_burst_count: activationTruthProbeState22C12E.mutationBurstCount, pre_post_request_scroll_velocity: velocities, pre_post_request_container_activity: containers.slice(0, 12) }, 24);
}

async function runActivationExperiment22C12E(id: string): Promise<Record<string, unknown>> {
  const beforeCount = passiveNetworkProbeProfilePostBatchCount22C12BR2;
  const beforeCursor = passiveNetworkProbePostCursorSamples22C12A.at(-1) ?? null;
  const active = resolveActiveScrollElement22C12C();
  const experiments: Record<string, () => void> = {
    real_wheel_replay: () => window.dispatchEvent(new WheelEvent("wheel", { deltaY: 720, bubbles: true, cancelable: true })),
    container_scroll_replay: () => { if (active) active.scrollTop += 720; else window.scrollBy(0, 720); },
    momentum_simulation: () => [360, 280, 180, 90].forEach((deltaY, index) => setTimeout(() => window.dispatchEvent(new WheelEvent("wheel", { deltaY, bubbles: true, cancelable: true })), index * 80)),
    pointer_wheel_combined: () => { window.dispatchEvent(new PointerEvent("pointermove", { bubbles: true, pointerType: "mouse" })); window.dispatchEvent(new WheelEvent("wheel", { deltaY: 720, bubbles: true, cancelable: true })); },
    hover_boundary_traversal: () => document.querySelector('a[href*="/video/"]')?.dispatchEvent(new MouseEvent("mouseover", { bubbles: true })),
    scroll_into_view_bottom_cards: () => Array.from(document.querySelectorAll('a[href*="/video/"]')).at(-1)?.scrollIntoView({ block: "end", behavior: "auto" }),
    synthetic_visibility_focus_refresh: () => { window.dispatchEvent(new Event("focus")); document.dispatchEvent(new Event("visibilitychange")); },
    intersection_sentinel_forced_visibility: () => Array.from(activationTruthProbeState22C12E.intersectionTargets.keys()).slice(-1).forEach((target) => recordActivationTraceEvent22C12E({ type: `synthetic_intersection_probe:${target}`, synthetic: true }, "synthetic_experiment"))
  };
  activationTruthProbeState22C12E.syntheticExperimentEventTypes.add(id);
  recordActivationTraceEvent22C12E({ type: `experiment_start:${id}`, synthetic: true }, "synthetic_experiment");
  const experimentAction = experiments[id] ?? experiments.real_wheel_replay;
  if (experimentAction) experimentAction();
  await new Promise((resolve) => setTimeout(resolve, 1_500));
  const result = { experiment_id: id, at: new Date().toISOString(), request_emitted: passiveNetworkProbeProfilePostBatchCount22C12BR2 > beforeCount ? "yes" : "no", cursor_progressed: (passiveNetworkProbePostCursorSamples22C12A.at(-1) ?? null) !== beforeCursor ? "yes" : "no", experiment_intersection_results: activationTruthProbeState22C12E.intersectionEvents.slice(-5), experiment_success_confidence: passiveNetworkProbeProfilePostBatchCount22C12BR2 > beforeCount ? "high" : "low" };
  pushBounded22C12E(activationTruthProbeState22C12E.experimentResults, result, 24);
  schedulePassiveNetworkProbePersistence22C12A();
  return result;
}

function humanVsSyntheticDiff22C12E(): Record<string, unknown> {
  const humanTypes = new Set(activationTruthProbeState22C12E.events.filter((event) => event.source === "human_or_page").map((event) => event.type));
  const syntheticTypes = activationTruthProbeState22C12E.syntheticExperimentEventTypes;
  const missing = ["wheel", "scroll", "pointermove", "mouseover", "focus", "visibilitychange", "intersection"].filter((type) => !humanTypes.has(type) && !syntheticTypes.has(type));
  return { human_vs_extension_scroll_differences: { human_event_types: Array.from(humanTypes).slice(-30), synthetic_experiment_types: Array.from(syntheticTypes).slice(-30), human_scroll_events: activationTruthProbeState22C12E.events.filter((event) => event.source === "human_or_page" && ["scroll", "wheel", "touchmove"].includes(event.type)).length, synthetic_scroll_events: activationTruthProbeState22C12E.events.filter((event) => event.source === "synthetic_experiment" && ["scroll", "wheel", "touchmove"].includes(event.type)).length }, missing_activation_signals: missing, synthetic_behavior_gaps: missing, likely_missing_trigger: missing[0] ?? "unknown_until_manual_trace" };
}

function getActivationTruthProbeDiagnostics22C12E(): Record<string, unknown> {
  const lastRequest = activationTruthProbeState22C12E.requestTimeline.at(-1) ?? null;
  const diff = humanVsSyntheticDiff22C12E();
  return { scanner_runtime_version: ACTIVATION_TRUTH_PROBE_VERSION_22C12E, pagination_trace_version: PAGINATION_TRACE_VERSION_22C12E, activation_truth_probe_version: ACTIVATION_TRUTH_PROBE_VERSION_22C12E, interaction_trace_runtime_version: INTERACTION_TRACE_RUNTIME_VERSION_22C12E, active_scan_profile_engine: "live_network_stream_profile_collector_22C12E", activation_truth_probe_active: activationTruthProbeState22C12E.installed ? "yes" : "no", recent_interaction_sequence: activationTruthProbeState22C12E.events.slice(-30).map((event) => event.type), interaction_event_timeline: activationTruthProbeState22C12E.events.slice(-80), interaction_velocity_samples: activationTruthProbeState22C12E.velocitySamples.slice(-30), interaction_scroll_container_samples: activationTruthProbeState22C12E.containerActivity.slice(-20), interaction_pointer_target_samples: activationTruthProbeState22C12E.pointerTargetSamples.slice(-30), interaction_focus_state_timeline: activationTruthProbeState22C12E.focusStateTimeline.slice(-20), interaction_visibility_state_timeline: activationTruthProbeState22C12E.visibilityStateTimeline.slice(-20), pre_post_request_event_sequence: lastRequest?.pre_post_request_event_sequence ?? [], pre_post_request_scroll_activity: lastRequest?.pre_post_request_scroll_activity ?? [], pre_post_request_pointer_activity: lastRequest?.pre_post_request_pointer_activity ?? [], pre_post_request_focus_state: lastRequest?.pre_post_request_focus_state ?? null, pre_post_request_visibility_state: lastRequest?.pre_post_request_visibility_state ?? null, pre_post_request_intersection_changes: lastRequest?.pre_post_request_intersection_changes ?? [], pre_post_request_mutation_burst_count: lastRequest?.pre_post_request_mutation_burst_count ?? 0, pre_post_request_scroll_velocity: lastRequest?.pre_post_request_scroll_velocity ?? [], pre_post_request_container_activity: lastRequest?.pre_post_request_container_activity ?? [], candidate_scroll_container_matrix: activationTruthProbeState22C12E.containerMatrix.slice(0, 20), active_container_confidence_scores: activationTruthProbeState22C12E.activeContainerConfidenceScores.slice(0, 20), likely_pagination_container: activationTruthProbeState22C12E.likelyPaginationContainer, likely_virtualized_container: activationTruthProbeState22C12E.likelyVirtualizedContainer, likely_intersection_sentinel_container: activationTruthProbeState22C12E.likelyIntersectionSentinelContainer, profile_intersection_observer_count: activationTruthProbeState22C12E.intersectionObserverCount, profile_intersection_target_count: activationTruthProbeState22C12E.intersectionTargets.size, probable_bottom_sentinel_detected: activationTruthProbeState22C12E.probableBottomSentinelDetected ? "yes" : "no", probable_virtualization_boundary_detected: activationTruthProbeState22C12E.probableVirtualizationBoundaryDetected ? "yes" : "no", sentinel_to_request_correlation: activationTruthProbeState22C12E.requestTimeline.map((request) => ({ request_started_at: request.request_started_at, intersection_events_before_request: request.intersection_events_before_request })).slice(-12), request_started_at: lastRequest?.request_started_at ?? "none", request_completed_at: lastRequest?.request_completed_at ?? "none", interaction_events_before_request: lastRequest?.interaction_events_before_request ?? 0, scroll_activity_before_request: lastRequest?.scroll_activity_before_request ?? 0, intersection_events_before_request: lastRequest?.intersection_events_before_request ?? 0, mutation_burst_before_request: lastRequest?.mutation_burst_before_request ?? 0, focus_state_before_request: lastRequest?.focus_state_before_request ?? "unknown", visibility_state_before_request: lastRequest?.visibility_state_before_request ?? document.visibilityState, container_scroll_delta_before_request: lastRequest?.container_scroll_delta_before_request ?? 0, pagination_activation_experiment_matrix: activationTruthProbeState22C12E.experimentResults, experiment_request_emission_results: activationTruthProbeState22C12E.experimentResults.map((item) => ({ experiment_id: item.experiment_id, request_emitted: item.request_emitted })), experiment_cursor_progression_results: activationTruthProbeState22C12E.experimentResults.map((item) => ({ experiment_id: item.experiment_id, cursor_progressed: item.cursor_progressed })), experiment_intersection_results: activationTruthProbeState22C12E.experimentResults.map((item) => item.experiment_intersection_results), experiment_success_confidence: activationTruthProbeState22C12E.experimentResults.at(-1)?.experiment_success_confidence ?? "not_run", ...diff };
}

function installActivationTruthProbe22C12E(): void {
  if (activationTruthProbeState22C12E.installed) return;
  activationTruthProbeState22C12E.installed = true;
  ["wheel", "scroll", "pointermove", "pointerdown", "mouseover", "mousemove", "focus", "blur", "focusin", "focusout", "visibilitychange", "resize", "keydown", "touchstart", "touchmove"].forEach((type) => window.addEventListener(type, (event) => { scanActivationContainers22C12E(); recordActivationTraceEvent22C12E(event); }, { capture: true, passive: true }));
  const observer = new MutationObserver((mutations) => { activationTruthProbeState22C12E.mutationBurstCount += mutations.length; recordActivationTraceEvent22C12E({ type: "mutation_burst" }, "observer"); });
  observer.observe(document.documentElement, { childList: true, subtree: true, attributes: true });
  const OriginalIntersectionObserver22C12E = window.IntersectionObserver;
  window.IntersectionObserver = class ReupIntersectionObserver22C12E extends OriginalIntersectionObserver22C12E {
    constructor(callback: IntersectionObserverCallback, options?: IntersectionObserverInit) {
      const observerId = ++activationTruthProbeState22C12E.intersectionObserverCount;
      super((entries, observerInstance) => {
        for (const entry of entries) {
          const selector = selectorForElement22C12C(entry.target);
          const item = { at: new Date().toISOString(), at_ms: Date.now(), observer_id: observerId, selector, ratio: entry.intersectionRatio, isIntersecting: entry.isIntersecting, root: selectorForElement22C12C(options?.root ?? null) };
          activationTruthProbeState22C12E.intersectionTargets.set(selector, item);
          pushBounded22C12E(activationTruthProbeState22C12E.intersectionEvents, item, 120);
          if (isLikelyBottomSentinel22C12C(entry.target)) activationTruthProbeState22C12E.probableBottomSentinelDetected = true;
          if (entry.boundingClientRect.height <= 4 || entry.intersectionRatio < 0.05) activationTruthProbeState22C12E.probableVirtualizationBoundaryDetected = true;
        }
        recordActivationTraceEvent22C12E({ type: "intersection" }, "observer");
        callback(entries, observerInstance);
      }, options);
    }
    observe(target: Element): void {
      activationTruthProbeState22C12E.intersectionTargets.set(selectorForElement22C12C(target), { at: new Date().toISOString(), observed: true, selector: selectorForElement22C12C(target) });
      return super.observe(target);
    }
  };
  const tick = () => { activationTruthProbeState22C12E.lastRafBurstAt = Date.now(); requestAnimationFrame(tick); };
  requestAnimationFrame(tick);
  const runtime: ManualParityTraceRuntime22C12E = { printInteractionTimeline: () => activationTruthProbeState22C12E.events.slice(-120), printLastPostRequest: () => activationTruthProbeState22C12E.requestTimeline.at(-1) ?? null, printContainerMatrix: () => scanActivationContainers22C12E(), printSentinelAnalysis: () => ({ profile_intersection_observer_count: activationTruthProbeState22C12E.intersectionObserverCount, profile_intersection_target_count: activationTruthProbeState22C12E.intersectionTargets.size, probable_bottom_sentinel_detected: activationTruthProbeState22C12E.probableBottomSentinelDetected, probable_virtualization_boundary_detected: activationTruthProbeState22C12E.probableVirtualizationBoundaryDetected, recent_intersection_events: activationTruthProbeState22C12E.intersectionEvents.slice(-30) }), printHumanVsSyntheticDiff: () => humanVsSyntheticDiff22C12E(), runExperiment: (id: string) => runActivationExperiment22C12E(id), dumpActivationFingerprint: () => getActivationTruthProbeDiagnostics22C12E(), printRuntimeState: () => ({ installed: activationTruthProbeState22C12E.installed, event_count: activationTruthProbeState22C12E.events.length, request_count: activationTruthProbeState22C12E.requestTimeline.length, last_raf_burst_at: activationTruthProbeState22C12E.lastRafBurstAt }) };
  window.__REUP_MANUAL_PARITY_TRACE_22C12E__ = runtime;
  window.__REUP_DEBUG_PAGINATION_22C12E__ = runtime;
  scanActivationContainers22C12E();
}

function createLiveNetworkStreamRuntime22C12D(): LiveNetworkStreamRuntime22C12D {
  return {
    subscribe(listener) {
      liveNetworkStreamSubscribers22C12D.add(listener);
      return () => this.unsubscribe(listener);
    },
    unsubscribe(listener) {
      liveNetworkStreamSubscribers22C12D.delete(listener);
    },
    getState() {
      return getLiveNetworkStreamDiagnostics22C12D();
    },
    getRecentBatches() {
      return [...liveNetworkStreamBatches22C12D];
    },
    getRecentTargets() {
      return [...liveNetworkStreamTargets22C12D];
    },
    emit(batch, endpointKind, endpointPath, capturedAt, newAwemeCount) {
      const streamBatch: LiveNetworkStreamBatch22C12D = { batchId: `22C12D-${liveNetworkStreamNextBatchId22C12D++}`, emittedAt: capturedAt, endpoint_kind: endpointKind, endpoint_path: endpointPath, awemeCount: batch.awemeCount, newAwemeCount, cursor: batch.cursor, hasMore: batch.hasMore };
      const streamTargets = batch.targets.map((target): LiveNetworkStreamTarget22C12D => ({ aweme_id: target.aweme_id, endpoint_kind: endpointKind, source_url: target.source_url || `${location.origin}/video/${target.aweme_id}`, captured_at: capturedAt }));
      for (const target of streamTargets) {
        if (!liveNetworkStreamSeenTargetIds22C12D.has(`${target.endpoint_kind}:${target.aweme_id}`)) {
          liveNetworkStreamSeenTargetIds22C12D.add(`${target.endpoint_kind}:${target.aweme_id}`);
          liveNetworkStreamTargets22C12D.push(target);
          liveNetworkStreamTotalTargets22C12D += 1;
        }
      }
      liveNetworkStreamBatches22C12D.push(streamBatch);
      while (liveNetworkStreamBatches22C12D.length > 80) liveNetworkStreamBatches22C12D.shift();
      while (liveNetworkStreamTargets22C12D.length > 400) liveNetworkStreamTargets22C12D.shift();
      liveNetworkStreamLastEmitAt22C12D = capturedAt;
      const event = { batch: streamBatch, targets: streamTargets };
      for (const listener of Array.from(liveNetworkStreamSubscribers22C12D)) {
        try { listener(event); } catch (error) { console.warn("[reup-douyin][22C-12D-stream] subscriber failed", error); }
      }
      return event;
    }
  };
}

function getLiveNetworkStreamRuntime22C12D(): LiveNetworkStreamRuntime22C12D {
  if (!window.__REUP_NETWORK_STREAM_22C12D__) window.__REUP_NETWORK_STREAM_22C12D__ = createLiveNetworkStreamRuntime22C12D();
  return window.__REUP_NETWORK_STREAM_22C12D__;
}

function createRuntimeAuthority22C11B(): RuntimeAuthority22C11B {
  const listeners = new Set<(snapshot: RuntimeAuthoritySnapshot22C11B) => void>();
  const domains = new Map<RuntimeAuthorityDomain22C11B, Record<string, unknown>>();
  const baseVersions = () => ({ scanner_runtime_version: RUNTIME_AUTHORITY_VERSION_22C11B, state_machine_version: RUNTIME_AUTHORITY_VERSION_22C11B, runtime_authority_version: RUNTIME_AUTHORITY_VERSION_22C11B, scan_controller_version: SCAN_CONTROLLER_VERSION_22C11B, diagnostics_runtime_version: DIAGNOSTICS_RUNTIME_VERSION_22C11B, popup_runtime_version: RUNTIME_AUTHORITY_VERSION_22C11B, controller_runtime_version: SCAN_CONTROLLER_VERSION_22C11B, stream_runtime_version: NETWORK_STREAM_RUNTIME_VERSION_22C12D });
  const build = (): RuntimeAuthoritySnapshot22C11B => {
    const flattened = Array.from(domains.values()).reduce<Record<string, unknown>>((acc, domain) => ({ ...acc, ...domain }), {});
    const disconnected: string[] = [];
    const stale: string[] = [];
    const reasons: string[] = [];
    const probeInstalled = flattened.network_probe_installed === "yes";
    const bridgeReady = flattened.network_probe_bridge_ready === "yes" || flattened.network_probe_page_bridge_ready === "yes";
    const streamBatches = Number(flattened.network_stream_total_batches ?? 0);
    const queueCount = Number(flattened.network_profile_post_unique_count ?? flattened.queue_target_count ?? 0);
    if (!probeInstalled) disconnected.push("probe");
    if (probeInstalled && !bridgeReady) { disconnected.push("probe_bridge"); reasons.push("probe_installed_without_ready_bridge"); }
    if (queueCount > 0 && !probeInstalled) { stale.push("probe"); reasons.push("collector_active_while_probe_disconnected"); }
    if (streamBatches > 0 && !bridgeReady) { reasons.push("stream_batches_seen_while_bridge_not_ready"); }
    const status: RuntimeHealthStatus22C11B = stale.length > 0 ? "stale_authority_detected" : reasons.includes("stream_batches_seen_while_bridge_not_ready") ? "bridge_inconsistent" : disconnected.length > 0 ? "degraded" : "healthy";
    return Object.freeze({
      ...flattened,
      ...baseVersions(),
      runtime_health_status: status,
      runtime_health_reasons: reasons,
      disconnected_runtime_domains: disconnected,
      stale_authority_domains: stale,
      runtime_snapshot_updated_at: new Date().toISOString(),
      runtime_domains: Array.from(domains.keys())
    }) as RuntimeAuthoritySnapshot22C11B;
  };
  return {
    updateDomain(domain, patch) {
      domains.set(domain, Object.freeze({ ...(domains.get(domain) ?? {}), ...patch, [`${domain}_runtime_last_update_at`]: new Date().toISOString() }));
      const snapshot = build();
      listeners.forEach((listener) => listener(snapshot));
      return snapshot;
    },
    getRuntimeSnapshot: build,
    subscribe(listener) {
      listeners.add(listener);
      return () => listeners.delete(listener);
    }
  };
}

function getRuntimeAuthority22C11B(): RuntimeAuthority22C11B {
  if (!window.__REUP_RUNTIME_AUTHORITY_22C11B__) window.__REUP_RUNTIME_AUTHORITY_22C11B__ = createRuntimeAuthority22C11B();
  return window.__REUP_RUNTIME_AUTHORITY_22C11B__;
}

function updateRuntimeAuthority22C11B(domain: RuntimeAuthorityDomain22C11B, patch: Record<string, unknown>): RuntimeAuthoritySnapshot22C11B {
  return getRuntimeAuthority22C11B().updateDomain(domain, patch);
}

function getRuntimeSnapshot(): RuntimeAuthoritySnapshot22C11B {
  const probe = getPassiveNetworkProbeSnapshot22C12A();
  updateRuntimeAuthority22C11B("content", { content_script_version: CONTENT_SCRIPT_VERSION, content_script_supported_handlers: [...CONTENT_SCRIPT_SUPPORTED_HANDLERS], current_url: window.location.href, document_ready_state: document.readyState });
  updateRuntimeAuthority22C11B("probe", { ...passiveNetworkProbeSummary22C12A, network_probe_page_bridge_ready: passiveNetworkProbeSummary22C12A.network_probe_bridge_ready, network_profile_post_targets: probe.profilePostTargets, network_favorite_targets: probe.favoriteTargets, network_other_aweme_targets: probe.otherTargets, network_post_cursor_values_sample: probe.postCursorValuesSample, network_post_cursor_fields_sample: probe.postCursorFieldSamples, network_post_has_more_state: probe.postHasMoreState, network_post_batch_count: probe.profilePostBatchCount, network_post_last_batch_at: probe.profilePostLastBatchAt, network_post_last_new_id_at: probe.profilePostLastNewIdAt });
  updateRuntimeAuthority22C11B("network_stream", getLiveNetworkStreamDiagnostics22C12D());
  updateRuntimeAuthority22C11B("controller", { canonical_scanner_function: "liveNetworkStreamProfileCollector22C13A", canonical_scanner_trace_version: PAGINATION_VERIFICATION_VERSION_22C13A, active_scan_profile_engine: "live_network_stream_profile_collector_22C13A", scan_profile_pipeline_lock: SCAN_PROFILE_PIPELINE_LOCK_22C13A });
  return getRuntimeAuthority22C11B().getRuntimeSnapshot();
}

function getRuntimeAuthorityDiagnostics22C11B(): Record<string, unknown> {
  return getRuntimeSnapshot();
}

function getLiveNetworkStreamDiagnostics22C12D(): Record<string, unknown> {
  return {
    network_stream_runtime_active: "yes",
    network_stream_runtime_version: NETWORK_STREAM_RUNTIME_VERSION_22C12D,
    network_stream_subscriber_count: liveNetworkStreamSubscribers22C12D.size,
    network_stream_total_batches: liveNetworkStreamBatches22C12D.length,
    network_stream_total_targets: liveNetworkStreamTotalTargets22C12D,
    network_stream_last_emit_at: liveNetworkStreamLastEmitAt22C12D ?? "none",
    network_stream_recent_batches: liveNetworkStreamBatches22C12D.slice(-10),
    network_stream_recent_profile_post_targets: liveNetworkStreamTargets22C12D.filter((target) => target.endpoint_kind === "profile_post").slice(-20)
  };
}

function buildNetworkStreamQueueTargets22C12D(targets: LiveNetworkStreamTarget22C12D[], profileUrl: string): MinimalActiveWorksTarget22C11B[] {
  return targets.filter((target) => target.endpoint_kind === "profile_post").map((target, index) => ({ aweme_id: target.aweme_id, source_url: target.source_url || `${location.origin}/video/${target.aweme_id}`, profile_url: profileUrl, index: index + 1, discovered_at: target.captured_at, discovery_source: "scan_queue_adapter_22C11B" }));
}

getRuntimeAuthority22C11B();
const scanDebugInstrumentationInstallersRan: string[] = [];

function installDebugScanInstrumentation22C13D(): void {
  installPaginationReverseEngineering22C12C();
  scanDebugInstrumentationInstallersRan.push("installPaginationReverseEngineering22C12C");
  installActivationTruthProbe22C12E();
  scanDebugInstrumentationInstallersRan.push("installActivationTruthProbe22C12E");
  installManualPaginationVerifier22C13A();
  scanDebugInstrumentationInstallersRan.push("installManualPaginationVerifier22C13A");
}

if (ENABLE_SCAN_DEBUG_INSTRUMENTATION) {
  installDebugScanInstrumentation22C13D();
}
getLiveNetworkStreamRuntime22C12D();
initializePassiveNetworkProbe22C12AR2();
updateRuntimeAuthority22C11B("content", { content_runtime_status: "ready", content_script_version: CONTENT_SCRIPT_VERSION, content_script_supported_handlers: [...CONTENT_SCRIPT_SUPPORTED_HANDLERS] });

chrome.runtime.onMessage.addListener((rawMessage, _sender, sendResponse: (response: ExtensionMessageResponse) => void) => {
  try {
    const message = rawMessage as ExtensionMessage;
    if (message.type === "DOUYIN_SCANNER_PING" || message.type === "REUP_DOUYIN_PING") {
      const pageContext = detectDouyinPageContext();
      const pong: DouyinContentScriptPong = {
        success: true,
        type: "REUP_DOUYIN_PONG",
        ready: true,
        url: window.location.href,
        version: CONTENT_SCRIPT_VERSION,
        page_context: pageContext,
        viewport: pageContext.viewport
      };
      const runtimeSnapshot = getRuntimeSnapshot();
      sendResponse({ ok: true, success: true, ready: true, type: "REUP_DOUYIN_PONG", url: pong.url, version: pong.version, contentScriptVersion: CONTENT_SCRIPT_VERSION, content_script_version: CONTENT_SCRIPT_VERSION, handlers: [...CONTENT_SCRIPT_SUPPORTED_HANDLERS], content_script_supported_handlers: [...CONTENT_SCRIPT_SUPPORTED_HANDLERS], page_context: pong.page_context, viewport: pong.viewport, pong, network_probe_summary: passiveNetworkProbeSummary22C12A, runtime_authority_snapshot: runtimeSnapshot, diagnostics: runtimeSnapshot });
      return true;
    }
    if (message.type === RUNTIME_AUTHORITY_SNAPSHOT_MESSAGE_22C11B) {
      const snapshot = getRuntimeSnapshot();
      sendResponse({ ok: true, traceVersion: RUNTIME_AUTHORITY_VERSION_22C11B, contentScriptVersion: CONTENT_SCRIPT_VERSION, content_script_version: CONTENT_SCRIPT_VERSION, runtime_authority_snapshot: snapshot, diagnostics: snapshot });
      return true;
    }
    if (message.type === "DOUYIN_NETWORK_PROBE_STATUS_22C12A_R3") {
      const runtimeSnapshot = getRuntimeSnapshot();
      sendResponse({ ok: true, traceVersion: RUNTIME_AUTHORITY_VERSION_22C11B, contentScriptVersion: CONTENT_SCRIPT_VERSION, content_script_version: CONTENT_SCRIPT_VERSION, runtime_authority_snapshot: runtimeSnapshot, diagnostics: runtimeSnapshot });
      return true;
    }
    if (message.type === MANUAL_PAGINATION_TRUTH_TEST_MESSAGE_22C13A) {
      if (!ENABLE_SCAN_DEBUG_INSTRUMENTATION) {
        sendResponse({
          ok: false,
          traceVersion: PAGINATION_VERIFICATION_VERSION_22C13A,
          reason: "scan_debug_instrumentation_disabled",
          diagnostics: {
            scan_debug_instrumentation_enabled: "no",
            scan_debug_instrumentation_installers_ran: [...scanDebugInstrumentationInstallersRan]
          }
        });
        return true;
      }
      void runManualPaginationTruthTest()
        .then((diagnostics) => sendResponse({ ok: true, traceVersion: PAGINATION_VERIFICATION_VERSION_22C13A, diagnostics }))
        .catch((error) => sendResponse({ ok: false, traceVersion: PAGINATION_VERIFICATION_VERSION_22C13A, reason: "manual_pagination_truth_test_failed", error: serializeModalTestScanError(error), diagnostics: getManualPaginationTruthDiagnostics22C13A() }));
      return true;
    }
    if (message.type === "DOUYIN_SCAN_PROFILE_MINIMAL_22C11B_PING") {
      sendResponse({
        ok: true,
        handler_registered: true,
        handler: "DOUYIN_SCAN_PROFILE_MINIMAL_22C11B",
        scanner_available: true,
        scanner_function: "collectActiveWorksGridTargets22C11B",
        traceVersion: "22C-11B",
        diagnostics: {
          canonical_content_handler_registered: "yes",
          canonical_scanner_function: "collectActiveWorksGridTargets22C11B",
          canonical_scanner_trace_version: "22C-11B",
          content_script_version: CONTENT_SCRIPT_VERSION,
          content_script_supported_handlers: [...CONTENT_SCRIPT_SUPPORTED_HANDLERS]
        }
      });
      return true;
    }
    if (message.type === "DOUYIN_SCAN_PROFILE_MINIMAL_22C11B") {
      const receivedAt = new Date().toISOString();
      void runMinimalActiveTabProfileScan22C11B(message, receivedAt)
        .then(sendResponse)
        .catch((error) => {
        const errorSafe = serializeModalTestScanError(error);
        sendResponse({
          ok: false,
          traceVersion: "22C-11B",
          messageTypeHandled: message.type,
          reason: "minimal_active_works_scanner_threw",
          error: errorSafe,
          verified_targets: [],
          verified_target_details: [],
          scan_rounds: 0,
          stop_reason: "minimal_active_works_scanner_threw",
          total_candidates: 0,
          rejected_count: 0,
          rejected_reasons: [],
          diagnostics: {
            canonical_content_handler_registered: "yes",
            canonical_content_handler_received: "yes",
            canonical_content_handler_received_at: receivedAt,
            canonical_scanner_function: "collectActiveWorksGridTargets22C11B",
            canonical_scanner_trace_version: "22C-11B",
            canonical_scanner_result: "failed",
            specific_scan_error: "minimal_active_works_scanner_threw",
            canonical_scanner_error: errorSafe,
            content_script_version: CONTENT_SCRIPT_VERSION,
            content_script_supported_handlers: [...CONTENT_SCRIPT_SUPPORTED_HANDLERS]
          }
        });
      });
    return true;
  }
    if (message.type === "DOUYIN_SCAN_PROFILE_POST_PAGE_22C14B") {
      const receivedAt = new Date().toISOString();
      void runActiveProfilePostPageFetch22C14B(message, receivedAt)
        .then(sendResponse)
        .catch((error) => {
          const errorSafe = serializeModalTestScanError(error);
          sendResponse({
            ok: false,
            traceVersion: "22C-14B",
            messageTypeHandled: message.type,
            reason: "active_profile_post_page_fetch_threw",
            error: errorSafe,
            verified_targets: [],
            verified_target_details: [],
            scan_rounds: 0,
            stop_reason: "active_profile_post_page_fetch_threw",
            total_candidates: 0,
            rejected_count: 0,
            rejected_reasons: ["active_profile_post_page_fetch_threw"],
            diagnostics: {
              active_profile_post_page_fetch_received: "yes",
              active_profile_post_page_fetch_received_at: receivedAt,
              active_profile_post_page_fetch_result: "failed",
              active_profile_post_page_fetch_error: errorSafe,
              scan_job_id: message.scan_job_id ?? null,
              scan_job_cursor: message.cursor ?? null,
              scan_job_page_index: message.page_index ?? null,
              content_script_version: CONTENT_SCRIPT_VERSION,
              content_script_supported_handlers: [...CONTENT_SCRIPT_SUPPORTED_HANDLERS]
            }
          });
        });
      return true;
    }
    if (message.type === "DOUYIN_PROFILE_DOM_PROBE" || message.type === "DOUYIN_PROFILE_DOM_PROBE_22C11B") {
      try {
        const probe = buildDouyinProfileDomProbe();
        const traceVersion = "22C-11B";
        const expectedProfileUrl = typeof message.expected_profile_url === "string" && message.expected_profile_url.trim() ? message.expected_profile_url : window.location.href;
        const tailReconcileProbe = collectActiveWorksGridTargets22C11B(expectedProfileUrl, new Date().toISOString());
        const tailReconcileCandidates = tailReconcileProbe.targets.slice(0, 120).map((target) => ({
          aweme_id: target.aweme_id,
          source_url: target.source_url,
          profile_url: target.profile_url,
          caption: target.caption ?? null,
          thumbnail_url: target.thumbnail_url ?? null
        }));
        const profileDomProbe = { ...probe, traceVersion, scan_run_id: message.scan_run_id ?? null, status: probe.probeError ? "failed" : "completed", error: probe.probeError ?? null, tail_reconcile_candidates: tailReconcileCandidates, tail_reconcile_candidate_ids: tailReconcileCandidates.map((target) => target.aweme_id) };
        const profileGridReady = profileDomProbe.profileGridFound || profileDomProbe.videoAnchorCount > 0 || profileDomProbe.modalIdLinkCount > 0 || profileDomProbe.awemeIdCount > 0 || profileDomProbe.gridCardCandidateCount > 0 || profileDomProbe.emptyProfileDetected;
        sendResponse({
          ok: !probe.probeError,
          profile_dom_probe: profileDomProbe,
          diagnostics: {
            ...profileDomProbe,
            profile_dom_probe: profileDomProbe,
            profile_dom_probe_status: profileDomProbe.status,
            profile_dom_probe_message_type: message.type,
            profile_dom_probe_message: profileDomProbe.status === "completed" ? "ok" : "failed",
            profile_dom_probe_response_received: "yes",
            profile_grid_ready: profileGridReady,
            video_anchor_count: profileDomProbe.videoAnchorCount,
            video_link_count: profileDomProbe.videoAnchorCount,
            modal_id_link_count: profileDomProbe.modalIdLinkCount,
            aweme_link_count: profileDomProbe.modalIdLinkCount,
            aweme_id_count: profileDomProbe.awemeIdCount,
            grid_card_candidate_count: profileDomProbe.gridCardCandidateCount,
            scroll_container_found: profileDomProbe.scrollContainerFound,
            tail_reconcile_candidates: tailReconcileCandidates,
            tail_reconcile_candidate_ids: tailReconcileCandidates.map((target) => target.aweme_id),
            tail_reconcile_dom_candidate_count: tailReconcileCandidates.length,
            tail_reconcile_dom_probe_source: "active_works_grid_22C11B",
            ...tailReconcileProbe.diagnostics,
            dom_probe_message_result: "ok",
            scan_no_round_reason: profileGridReady ? null : "profile_grid_not_ready_timeout",
            specific_scan_error: probe.probeError ? "scan_dom_probe_failed" : null,
            raw_scan_error: probe.probeError ?? null
          }
        });
      } catch (error) {
        const traceVersion = "22C-11B";
        const probeError = error instanceof Error ? error.message : String(error);
        sendResponse({ ok: false, error: probeError, profile_dom_probe: { traceVersion, scan_run_id: message.scan_run_id ?? null, status: "failed", probeError, error: probeError, url: window.location.href, pathname: window.location.pathname, documentReadyState: document.readyState }, diagnostics: { profile_dom_probe_status: "failed", profile_dom_probe_message: "failed", dom_probe_message_result: "ok", specific_scan_error: "scan_dom_probe_failed", raw_scan_error: probeError } });
      }
      return true;
    }
    if (message.type === "DOUYIN_HYBRID_TAIL_GAP_DOM_SCROLL_PROBE") {
      void (async () => {
        try {
          const profileUrl = typeof message.expected_profile_url === "string" && message.expected_profile_url.trim()
            ? message.expected_profile_url.trim()
            : typeof message.profileUrl === "string" && message.profileUrl.trim()
              ? message.profileUrl.trim()
              : window.location.href;
          const maxRounds = typeof message.max_rounds === "number" && Number.isFinite(message.max_rounds)
            ? Math.max(1, Math.min(8, Math.round(message.max_rounds)))
            : 6;
          const maxDurationMs = typeof message.max_duration_ms === "number" && Number.isFinite(message.max_duration_ms)
            ? Math.max(1_000, Math.min(20_000, Math.round(message.max_duration_ms)))
            : 15_000;
          const collected = await collectActiveWorksGridTargetsUntilStable22C11B(profileUrl, {
            maxRounds,
            maxDurationMs,
            minRounds: Math.min(2, maxRounds),
            noNewPatience: Math.min(2, maxRounds),
            bottomStablePatience: Math.min(2, maxRounds)
          });
          const tailReconcileCandidates = collected.targets.slice(0, 200).map((target) => ({
            aweme_id: target.aweme_id,
            source_url: target.source_url,
            profile_url: target.profile_url,
            caption: target.caption ?? null,
            thumbnail_url: target.thumbnail_url ?? null
          }));
          sendResponse({
            ok: true,
            stop_reason: collected.stopReason,
            tail_reconcile_candidate_ids: tailReconcileCandidates.map((target) => target.aweme_id),
            diagnostics: {
              hybrid_tail_gap_dom_scroll_rounds: collected.scanRounds,
              hybrid_tail_gap_dom_scroll_bottom_reached: collected.bottomReached ? "yes" : "no",
              hybrid_tail_gap_dom_scroll_stop_reason: collected.stopReason,
              hybrid_tail_gap_dom_scroll_budget_rounds: maxRounds,
              hybrid_tail_gap_dom_scroll_budget_ms: maxDurationMs,
              tail_reconcile_candidates: tailReconcileCandidates,
              tail_reconcile_candidate_ids: tailReconcileCandidates.map((target) => target.aweme_id),
              tail_reconcile_dom_candidate_count: tailReconcileCandidates.length,
              tail_reconcile_dom_probe_source: "active_works_grid_scroll_capped_22C11B"
            }
          });
        } catch (error) {
          const probeError = error instanceof Error ? error.message : String(error);
          sendResponse({
            ok: false,
            stop_reason: "scroll_probe_exception",
            error: probeError,
            diagnostics: {
              hybrid_tail_gap_dom_scroll_stop_reason: "scroll_probe_exception",
              hybrid_tail_gap_dom_scroll_error: probeError
            }
          });
        }
      })();
      return true;
    }
    if (message.type === "GET_DOUYIN_PAGE_VIEWPORT") {
      sendResponse({ ok: true, success: true, viewport: getDouyinPageViewport() });
      return true;
    }
    if (message.type === "REUP_DOUYIN_DETECT_PAGE_CONTEXT") {
      const pageContext = detectDouyinPageContext();
      sendResponse({ ok: true, success: true, detector_status: "ready", current_url: pageContext.url, page_context: { ...pageContext, detector_status: "ready", current_url: pageContext.url } });
      return true;
    }
    if (message.type === "REUP_DOUYIN_DETECT") {
      sendResponse({ ok: true, page: detectPageFromDocument(document, window.location.href) });
      return true;
    }
    if (message.type === "REUP_DOUYIN_MODAL_TEST_SCAN_PROFILE_PING") {
      sendResponse({ ok: true, handler_registered: true, current_url: window.location.href, version: CONTENT_SCRIPT_VERSION });
      return true;
    }
    if (message.type === "REUP_DOUYIN_MODAL_TEST_SCAN_PROFILE") {
      void runModalTestProfileScan(message)
        .then((response) => sendResponse(response))
        .catch((error) => sendResponse({ ok: false, reason: "profile_scan_exception", error: serializeModalTestScanError(error), diagnostics: { current_url: window.location.href, handler_registered: true } }));
      return true;
    }
    if (message.type === "REUP_DOUYIN_CAPTURE") {
      void handleCaptureMessage(message)
        .then((payload) => sendResponse({ ok: true, payload }))
        .catch((error) => sendResponse({ ok: false, error: error instanceof Error ? error.message : "Unknown content script error." }));
      return true;
    }
    if (message.type === "REUP_DOUYIN_START_RIGHT_RAIL_CALIBRATION") {
      void startRightRailCalibration()
        .then((calibration) => sendResponse({ ok: true, calibration }))
        .catch((error) => sendResponse({ ok: false, error: error instanceof Error ? error.message : "Could not start right rail calibration." }));
      return true;
    }
    if (message.type === "REUP_DOUYIN_STOP_RIGHT_RAIL_CALIBRATION") {
      const result = ensureCalibrationModeStopped();
      sendResponse({ ok: true, calibration_mode_active_before_stop: result.activeBeforeStop, calibration_mode_stopped: result.stopped });
      return true;
    }
    if (message.type === "REUP_DOUYIN_CLEAR_RIGHT_RAIL_CALIBRATION") {
      void clearRightRailCalibration()
        .then(() => sendResponse({ ok: true, calibration: null }))
        .catch((error) => sendResponse({ ok: false, error: error instanceof Error ? error.message : "Could not clear right rail calibration." }));
      return true;
    }
    if (message.type === "REUP_DOUYIN_SHOW_RIGHT_RAIL_CALIBRATION") {
      void loadRightRailCalibration()
        .then((calibration) => sendResponse({ ok: true, calibration }))
        .catch((error) => sendResponse({ ok: false, error: error instanceof Error ? error.message : "Could not load right rail calibration." }));
      return true;
    }
    if (message.type === "REUP_DOUYIN_START_FULL_MODAL_HARVEST") {
      void startHarvestV2(message)
        .then((progress) => {
          const runtime = loadRuntimeSnapshotSync();
          sendResponse({ ok: true, harvest_progress: progress, ...(runtime ? { harvest_runtime_v2: runtime } : {}) });
        })
        .catch((error) => sendResponse({ ok: false, error: error instanceof Error ? error.message : "Could not start full modal harvest." }));
      return true;
    }
    if (message.type === "REUP_DOUYIN_START_HARVEST_V2") {
      void startHarvestV2(message)
        .then((progress) => sendResponse({ ok: true, harvest_progress: progress }))
        .catch((error) => sendResponse({ ok: false, error: error instanceof Error ? error.message : "Could not start full modal harvest." }));
      return true;
    }
    if (message.type === "REUP_DOUYIN_RESUME_FULL_MODAL_HARVEST") {
      void resumeHarvestV2(message)
        .then((progress) => {
          const runtime = loadRuntimeSnapshotSync();
          sendResponse({ ok: true, harvest_progress: progress, ...(runtime ? { harvest_runtime_v2: runtime } : {}) });
        })
        .catch((error) => sendResponse({ ok: false, error: error instanceof Error ? error.message : "Could not resume full modal harvest." }));
      return true;
    }
    if (message.type === "REUP_DOUYIN_RESUME_HARVEST_V2") {
      void resumeHarvestV2(message)
        .then((progress) => sendResponse({ ok: true, harvest_progress: progress }))
        .catch((error) => sendResponse({ ok: false, error: error instanceof Error ? error.message : "Could not resume full modal harvest." }));
      return true;
    }
    if (message.type === "REUP_DOUYIN_STOP_FULL_MODAL_HARVEST") {
      void stopHarvestV2()
        .then((progress) => {
          const runtime = loadRuntimeSnapshotSync();
          sendResponse({ ok: true, harvest_progress: progress, ...(runtime ? { harvest_runtime_v2: runtime } : {}) });
        })
        .catch((error) => sendResponse({ ok: false, error: error instanceof Error ? error.message : "Could not stop full modal harvest." }));
      return true;
    }
    if (message.type === "REUP_DOUYIN_STOP_HARVEST_V2") {
      void stopHarvestV2()
        .then((progress) => sendResponse({ ok: true, harvest_progress: progress }))
        .catch((error) => sendResponse({ ok: false, error: error instanceof Error ? error.message : "Could not stop full modal harvest." }));
      return true;
    }
    if (message.type === "REUP_DOUYIN_START_SAFE_HARVEST_RUN") {
      void startSafeHarvestRun(message)
        .then((progress) => sendResponse({ ok: true, harvest_progress: progress }))
        .catch((error) => sendResponse({ ok: false, error: error instanceof Error ? error.message : "Could not start safe harvest run." }));
      return true;
    }
    if (message.type === "REUP_DOUYIN_RESUME_SAFE_HARVEST_RUN") {
      void resumeSafeHarvestRun(message)
        .then((progress) => sendResponse({ ok: true, harvest_progress: progress }))
        .catch((error) => sendResponse({ ok: false, error: error instanceof Error ? error.message : "Could not resume safe harvest run." }));
      return true;
    }
    if (message.type === "REUP_DOUYIN_STOP_SAFE_HARVEST_RUN") {
      void stopSafeHarvestRun()
        .then((progress) => sendResponse({ ok: true, harvest_progress: progress }))
        .catch((error) => sendResponse({ ok: false, error: error instanceof Error ? error.message : "Could not stop safe harvest run." }));
      return true;
    }
    if (message.type === "REUP_DOUYIN_FLUSH_FULL_MODAL_HARVEST") {
      void flushHarvestV2()
        .then((progress) => sendResponse({ ok: true, harvest_progress: progress }))
        .catch((error) => sendResponse({ ok: false, error: error instanceof Error ? error.message : "Could not flush harvested metadata." }));
      return true;
    }
    if (message.type === "REUP_DOUYIN_GET_FULL_MODAL_HARVEST_PROGRESS") {
      void getHarvestProgressV2().then((progress) => {
        const runtime = loadRuntimeSnapshotSync();
        sendResponse({ ok: true, harvest_progress: progress, ...(runtime ? { harvest_runtime_v2: runtime } : {}) });
      });
      return true;
    }
    if (message.type === "REUP_DOUYIN_GET_HARVEST_RUNTIME_V2") {
      {
        const runtime = loadRuntimeSnapshotSync();
        sendResponse({ ok: true, harvest_progress: harvestProgress, ...(runtime ? { harvest_runtime_v2: runtime } : {}) });
      }
      return true;
    }
    if (message.type === "REUP_DOUYIN_RESET_FULL_MODAL_HARVEST_STATE") {
      void resetHarvestStateV2()
        .then((progress) => {
          const runtime = loadRuntimeSnapshotSync();
          sendResponse({ ok: true, harvest_progress: progress, ...(runtime ? { harvest_runtime_v2: runtime } : {}) });
        })
        .catch((error) => sendResponse({ ok: false, error: error instanceof Error ? error.message : "Could not reset harvest state." }));
      return true;
    }
    if (message.type === "REUP_DOUYIN_RESET_HARVEST_RUNTIME_V2") {
      void resetHarvestStateV2()
        .then((progress) => sendResponse({ ok: true, harvest_progress: progress }))
        .catch((error) => sendResponse({ ok: false, error: error instanceof Error ? error.message : "Could not reset harvest state." }));
      return true;
    }
    if (message.type === "REUP_DOUYIN_GET_SAFE_HARVEST_RUN") {
      void getSafeHarvestRunProgress()
        .then((progress) => sendResponse({ ok: true, harvest_progress: progress }))
        .catch((error) => sendResponse({ ok: false, error: error instanceof Error ? error.message : "Could not load safe harvest run state." }));
      return true;
    }
    if (message.type === "REUP_DOUYIN_RESET_SAFE_HARVEST_RUN") {
      void resetSafeHarvestRun()
        .then((progress) => sendResponse({ ok: true, harvest_progress: progress }))
        .catch((error) => sendResponse({ ok: false, error: error instanceof Error ? error.message : "Could not reset safe harvest run state." }));
      return true;
    }
    if (message.type === "REUP_DOUYIN_PROBE_CURRENT_MODAL") {
      void probeCurrentModalWithCalibratedPoints()
        .then((probe) => sendResponse({ ok: true, harvest_probe: probe }))
        .catch((error) => sendResponse({ ok: false, error: error instanceof Error ? error.message : "Could not probe current modal." }));
      return true;
    }
    if (message.type === "REUP_DOUYIN_PROBE_PROFILE_VIDEO_EVIDENCE") {
      try {
        const evidence = probeDouyinProfileVideoEvidence();
        sendResponse({ ok: true, profile_video_evidence: evidence, ...(evidence.current_url ? { current_url: evidence.current_url } : {}), diagnostics: evidence.diagnostics });
      } catch (error) {
        sendResponse({ ok: false, error: error instanceof Error ? error.message : "Could not probe profile video evidence." });
      }
      return true;
    }
    if (message.type === "REUP_DOUYIN_CLOSE_MODAL_IF_PRESENT") {
      void closeDouyinModalIfPresent()
        .then((result) => sendResponse({
          ok: result.ok,
          attempted: result.attempted,
          modal_still_visible: result.modal_still_visible,
          ...(result.current_url ? { current_url: result.current_url } : {}),
          diagnostics: result.diagnostics,
          reason: result.ok ? null : "modal_cleanup_failed"
        }))
        .catch((error) => sendResponse({ ok: false, attempted: true, modal_still_visible: true, error: error instanceof Error ? error.message : "Could not close modal if present." }));
      return true;
    }
    sendResponse({ ok: false, error: "Unsupported extension message." });
  } catch (error) {
    sendResponse({ ok: false, error: error instanceof Error ? error.message : "Unknown content script error." });
  }
  return true;
});

type MinimalActiveWorksTarget22C11B = {
  aweme_id: string;
  source_url: string;
  profile_url: string;
  index: number;
  discovered_at: string;
  discovery_source: "active_works_grid_22C11B" | "scan_queue_adapter_22C11B";
  caption?: string;
  thumbnail_url?: string;
  profile_card_evidence?: Record<string, unknown>;
};

function parseCompactChineseCount22C11B(value: string | null | undefined): number | null {
  const text = (value ?? "").replace(/\s+/g, " ").trim();
  const match = text.match(/作品\s*([0-9][0-9,]*(?:\.[0-9]+)?\s*万?)/);
  if (!match) return null;
  const raw = match[1]?.replace(/,/g, "").trim() ?? "";
  const compact = raw.endsWith("万");
  const number = Number(raw.replace(/万$/, ""));
  if (!Number.isFinite(number)) return null;
  return Math.round(compact ? number * 10_000 : number);
}

function activeWorksTabInfo22C11B(): { label: string | null; countText: string | null; expectedCount: number | null; semanticsVerified: boolean } {
  const candidates = Array.from(document.querySelectorAll<HTMLElement>("[role='tab'], button, a, div, span"))
    .filter((node) => {
      const text = (node.textContent ?? "").replace(/\s+/g, " ").trim();
      return text.includes("作品") && text.length <= 40;
    });
  const active = candidates.find((node) => node.getAttribute("aria-selected") === "true" || /active|selected|current/i.test(node.className.toString())) ?? candidates[0] ?? null;
  const label = active?.textContent?.replace(/\s+/g, " ").trim() ?? null;
  const expectedCount = parseCompactChineseCount22C11B(label);
  return {
    label,
    countText: label,
    expectedCount,
    semanticsVerified: Boolean(active && label?.includes("作品") && expectedCount != null)
  };
}

function extractModalAwemeId22C11B(value: string | null | undefined): string | null {
  if (!value) return null;
  try {
    const url = new URL(value, window.location.href);
    const modal = url.searchParams.get("modal_id")?.trim();
    const aweme = url.searchParams.get("aweme_id")?.trim();
    const video = url.pathname.match(/\/video\/(\d{16,22})/i)?.[1] ?? null;
    return [video, modal, aweme].find((id) => id != null && /^\d{16,22}$/.test(id)) ?? null;
  } catch {}
  return value.match(/(?:\/video\/|modal_id=|aweme_id=)(\d{16,22})/i)?.[1] ?? null;
}

function isVisibleElement22C11B(element: HTMLElement): boolean {
  const rect = element.getBoundingClientRect();
  const style = window.getComputedStyle(element);
  return rect.width > 0 && rect.height > 0 && style.visibility !== "hidden" && style.display !== "none";
}

function isExcludedProfileLink22C11B(anchor: HTMLAnchorElement): boolean {
  const context = anchor.closest("aside, nav, footer, [data-e2e*='recommend'], [class*='recommend'], [class*='sidebar'], [class*='login']") as HTMLElement | null;
  if (context) return true;
  const text = (anchor.closest("div, li, article, section")?.textContent ?? "").slice(0, 120);
  return /推荐|相关|广告|登录|合集|短剧/.test(text) && !/作品/.test(text);
}

function collectActiveWorksGridTargets22C11B(profileUrl: string, discoveredAt: string): { targets: MinimalActiveWorksTarget22C11B[]; diagnostics: Record<string, unknown> } {
  const byAweme = new Map<string, MinimalActiveWorksTarget22C11B>();
  const anchors = Array.from(document.querySelectorAll<HTMLAnchorElement>('a[href*="/video/"], a[href*="modal_id="], a[href*="aweme_id="]'))
    .filter((anchor) => isVisibleElement22C11B(anchor) && !isExcludedProfileLink22C11B(anchor));
  for (const anchor of anchors) {
    const awemeId = extractModalAwemeId22C11B(anchor.href);
    if (!awemeId || byAweme.has(awemeId)) continue;
    byAweme.set(awemeId, {
      aweme_id: awemeId,
      source_url: anchor.href || `${location.origin}/video/${awemeId}`,
      profile_url: profileUrl,
      index: byAweme.size + 1,
      discovered_at: discoveredAt,
      discovery_source: "scan_queue_adapter_22C11B"
    });
  }
  const targets = Array.from(byAweme.values()).map((target, index) => ({ ...target, index: index + 1 }));
  return {
    targets,
    diagnostics: {
      active_works_anchor_scan_version: "22C-11B",
      scan_queue_builder_used: "scan_queue_adapter_22C11B",
      queue_discovery_source: "active_works_grid_22C11B",
      active_works_anchor_candidate_count: anchors.length,
      active_works_unique_aweme_count: targets.length,
      active_works_aweme_sample_first: targets.slice(0, 5).map((target) => target.aweme_id),
      active_works_aweme_sample_last: targets.slice(-5).map((target) => target.aweme_id)
    }
  };
}

function douyinLoadingSpinnerVisible22C11B(): boolean {
  return Array.from(document.querySelectorAll<HTMLElement>('[class*="loading"], [class*="spinner"], [class*="Loading"], [class*="Spinner"], [aria-busy="true"], [role="progressbar"], svg'))
    .some((element) => {
      if (!isVisibleElement22C11B(element)) return false;
      const rect = element.getBoundingClientRect();
      const text = (element.textContent ?? "").replace(/\s+/g, " ").trim();
      const nearViewportBottom = rect.top >= window.innerHeight * 0.55 && rect.top <= window.innerHeight + 160;
      const loadingText = /加载|载入|loading/i.test(text);
      const loadingClass = /loading|spinner/i.test(element.className.toString());
      return nearViewportBottom && (loadingText || loadingClass || element.getAttribute("aria-busy") === "true" || element.getAttribute("role") === "progressbar");
    });
}

type ActiveWorksScrollSnapshot22C11B = { top: number; height: number; clientHeight: number; remaining: number; bottom: boolean };

const ACTIVE_WORKS_SCAN_MAX_ROUNDS_22C11B = 80;
const ACTIVE_WORKS_SCAN_MAX_DURATION_MS_22C11B = 120_000;
const ACTIVE_WORKS_SCAN_MIN_ROUNDS_22C11B = 12;
const ACTIVE_WORKS_SCAN_NO_NEW_PATIENCE_22C11B = 6;
const ACTIVE_WORKS_SCAN_BOTTOM_STABLE_PATIENCE_22C11B = 3;
const ACTIVE_WORKS_SCAN_RENDER_WAIT_MS_22C11B = 2200;
const MINIMAL_SCAN_NETWORK_PROBE_READY_WAIT_MS_22C12B = 3_500;
const MINIMAL_SCAN_NETWORK_PROBE_POLL_MS_22C12B = 120;
const MINIMAL_SCAN_NETWORK_PROBE_POST_SCROLL_SETTLE_MS_22C12B = 1_000;
const MINIMAL_SCAN_ACTIVE_PROFILE_POST_FETCH_MAX_PAGES_22C12B = 128;
const MINIMAL_SCAN_ACTIVE_PROFILE_POST_FETCH_PAGE_SIZE_22C12B = 20;
const MINIMAL_SCAN_ACTIVE_PROFILE_POST_FETCH_MAX_UNIQUE_TARGETS_22C12B = 5_000;
const MINIMAL_SCAN_ACTIVE_PROFILE_POST_FETCH_TIMEOUT_MS_22C12B = 12_000;
const MINIMAL_SCAN_ACTIVE_PROFILE_POST_FETCH_MAX_RUNTIME_MS_22C12B = 300_000;
const MINIMAL_SCAN_ACTIVE_PROFILE_POST_FETCH_EXPECTED_COUNT_RETRY_WAIT_MS_22C13B = 600;

function activeWorksScrollElement22C11B(): HTMLElement | null {
  const candidates = Array.from(document.querySelectorAll<HTMLElement>("main, section, article, div, ul"))
    .map((element) => {
      const style = window.getComputedStyle(element);
      const candidateCount = element.querySelectorAll('a[href*="/video/"], a[href*="modal_id="], a[href*="aweme_id="]').length;
      const scrollableDistance = Math.max(element.scrollHeight - element.clientHeight, 0);
      const visible = element.getBoundingClientRect().height > 20 && style.display !== "none" && style.visibility !== "hidden";
      const score = (scrollableDistance > 200 ? 1000 : 0) + Math.min(candidateCount * 40, 800) + (/auto|scroll/i.test(`${style.overflowY} ${style.overflow}`) ? 250 : 0);
      return { element, score, visible, scrollableDistance };
    })
    .filter((item) => item.visible && item.score > 0)
    .sort((left, right) => right.score - left.score);
  return candidates.find((item) => item.scrollableDistance > 200)?.element ?? null;
}

function activeWorksScrollSnapshot22C11B(element = activeWorksScrollElement22C11B()): ActiveWorksScrollSnapshot22C11B {
  const top = element ? element.scrollTop : window.scrollY;
  const height = element ? element.scrollHeight : Math.max(document.documentElement.scrollHeight, document.body.scrollHeight);
  const clientHeight = element ? element.clientHeight : window.innerHeight;
  const remaining = Math.max(height - (top + clientHeight), 0);
  return { top, height, clientHeight, remaining, bottom: !douyinLoadingSpinnerVisible22C11B() && remaining <= 360 };
}

function scrollBottomReached22C11B(): boolean {
  return activeWorksScrollSnapshot22C11B().bottom;
}

async function dispatchSyntheticWheelFlick22C11B(_round: number): Promise<{ events: number; deltas: number[]; scroll_element: string; scroll_top_before: number; scroll_top_after: number; scroll_height_before: number; scroll_height_after: number }> {
  const element = activeWorksScrollElement22C11B();
  const before = activeWorksScrollSnapshot22C11B(element);
  const step = Math.max(900, Math.floor(before.clientHeight * 0.9));
  const deltas = [Math.floor(step * 0.45), Math.floor(step * 0.5), Math.floor(step * 0.55), Math.floor(step * 0.4), Math.floor(step * 0.3)];
  for (const deltaY of deltas) {
    const eventInit: WheelEventInit = {
      deltaY,
      deltaX: 0,
      deltaMode: WheelEvent.DOM_DELTA_PIXEL,
      bubbles: true,
      cancelable: true,
      composed: true,
      clientX: Math.floor(window.innerWidth * 0.5),
      clientY: Math.floor(window.innerHeight * 0.72)
    };
    window.dispatchEvent(new WheelEvent("wheel", eventInit));
    if (element) element.scrollTop += deltaY;
    window.scrollBy(0, deltaY);
    const scrollingElement = document.scrollingElement as HTMLElement | null;
    if (scrollingElement) scrollingElement.scrollTop += Math.floor(deltaY * 0.35);
    await new Promise((resolve) => window.setTimeout(resolve, 110));
  }
  const lastVisible = Array.from(document.querySelectorAll<HTMLElement>('a[href*="/video/"], a[href*="modal_id="], a[href*="aweme_id="]')).filter(isVisibleElement22C11B).at(-1);
  lastVisible?.scrollIntoView({ block: "end", behavior: "auto" });
  const after = activeWorksScrollSnapshot22C11B(element);
  return { events: deltas.length, deltas, scroll_element: element ? "active_scroll_element" : "window", scroll_top_before: before.top, scroll_top_after: after.top, scroll_height_before: before.height, scroll_height_after: after.height };
}

async function collectActiveWorksGridTargetsUntilStable22C11B(
  profileUrl: string,
  options: { maxRounds?: number; maxDurationMs?: number; minRounds?: number; noNewPatience?: number; bottomStablePatience?: number } = {}
): Promise<{ targets: MinimalActiveWorksTarget22C11B[]; diagnostics: Record<string, unknown>; scanRounds: number; stopReason: string; bottomReached: boolean; noNewScrollAttempts: number }> {
  const byAweme = new Map<string, MinimalActiveWorksTarget22C11B>();
  const roundDiagnostics: Record<string, unknown>[] = [];
  const started = Date.now();
  let noNewScrollAttempts = 0;
  let stableBottomRounds = 0;
  let stableGeometryRounds = 0;
  let bottomReached = false;
  let blockedReason: string | null = null;
  let stopReason = "max_scroll_rounds_reached_22C11B";
  const maxRounds = Math.max(1, Math.min(
    ACTIVE_WORKS_SCAN_MAX_ROUNDS_22C11B,
    typeof options.maxRounds === "number" && Number.isFinite(options.maxRounds) ? Math.round(options.maxRounds) : ACTIVE_WORKS_SCAN_MAX_ROUNDS_22C11B
  ));
  const maxDurationMs = Math.max(1_000, Math.min(
    ACTIVE_WORKS_SCAN_MAX_DURATION_MS_22C11B,
    typeof options.maxDurationMs === "number" && Number.isFinite(options.maxDurationMs) ? Math.round(options.maxDurationMs) : ACTIVE_WORKS_SCAN_MAX_DURATION_MS_22C11B
  ));
  const minRounds = Math.max(1, Math.min(
    maxRounds,
    typeof options.minRounds === "number" && Number.isFinite(options.minRounds) ? Math.round(options.minRounds) : Math.min(ACTIVE_WORKS_SCAN_MIN_ROUNDS_22C11B, maxRounds)
  ));
  const noNewPatience = Math.max(1, typeof options.noNewPatience === "number" && Number.isFinite(options.noNewPatience)
    ? Math.round(options.noNewPatience)
    : Math.min(ACTIVE_WORKS_SCAN_NO_NEW_PATIENCE_22C11B, maxRounds));
  const bottomStablePatience = Math.max(1, typeof options.bottomStablePatience === "number" && Number.isFinite(options.bottomStablePatience)
    ? Math.round(options.bottomStablePatience)
    : Math.min(ACTIVE_WORKS_SCAN_BOTTOM_STABLE_PATIENCE_22C11B, maxRounds));
  for (let round = 1; round <= maxRounds; round += 1) {
    const beforeCount = byAweme.size;
    const beforeScroll = activeWorksScrollSnapshot22C11B();
    const beforeCollected = collectActiveWorksGridTargets22C11B(profileUrl, new Date().toISOString());
    for (const target of beforeCollected.targets) {
      if (!byAweme.has(target.aweme_id)) byAweme.set(target.aweme_id, { ...target, index: byAweme.size + 1 });
    }
    const flick = await dispatchSyntheticWheelFlick22C11B(round);
    await new Promise((resolve) => window.setTimeout(resolve, ACTIVE_WORKS_SCAN_RENDER_WAIT_MS_22C11B));
    const afterCollected = collectActiveWorksGridTargets22C11B(profileUrl, new Date().toISOString());
    for (const target of afterCollected.targets) {
      if (!byAweme.has(target.aweme_id)) byAweme.set(target.aweme_id, { ...target, index: byAweme.size + 1 });
    }
    const afterScroll = activeWorksScrollSnapshot22C11B();
    const bodyText = (document.body?.innerText ?? "").slice(0, 4000);
    blockedReason = /login|passport|登录|请先登录/i.test(`${bodyText} ${location.href}`) ? "douyin_login_required" : /captcha|security check|verify you are human|验证码|安全验证|滑块|请完成验证|checkpoint|abnormal traffic|检测到异常/i.test(bodyText) ? "douyin_checkpoint_required" : null;
    const newCount = byAweme.size - beforeCount;
    bottomReached = afterScroll.bottom;
    const patienceEligible = round >= minRounds;
    const geometryStable = Math.abs(afterScroll.top - beforeScroll.top) < 4 && Math.abs(afterScroll.height - beforeScroll.height) < 4;
    if (newCount === 0) noNewScrollAttempts += 1;
    else noNewScrollAttempts = 0;
    stableBottomRounds = bottomReached ? stableBottomRounds + 1 : 0;
    stableGeometryRounds = geometryStable ? stableGeometryRounds + 1 : 0;
    roundDiagnostics.push({ round, new_count: newCount, total_count: byAweme.size, bottom_reached: bottomReached, bottom_reached_eligible: patienceEligible, no_new_scroll_attempts: noNewScrollAttempts, stable_bottom_rounds: stableBottomRounds, stable_geometry_rounds: stableGeometryRounds, scroll_top_before: beforeScroll.top, scroll_top_after: afterScroll.top, scroll_height_before: beforeScroll.height, scroll_height_after: afterScroll.height, scroll_remaining_after: afterScroll.remaining, scroll_geometry_stable: geometryStable ? "yes" : "no", blocked_reason: blockedReason, synthetic_wheel_flick_enabled_22C11B: "yes", synthetic_wheel_event_count_22C11B: flick.events, synthetic_wheel_deltas_22C11B: flick.deltas, synthetic_scroll_element_22C11B: flick.scroll_element, render_wait_ms_22C11B: ACTIVE_WORKS_SCAN_RENDER_WAIT_MS_22C11B, minimum_scroll_rounds_22C11B: minRounds, no_new_patience_22C11B: noNewPatience, bottom_stable_patience_22C11B: bottomStablePatience });
    if (blockedReason) {
      stopReason = blockedReason;
      break;
    }
    if (patienceEligible && bottomReached && stableBottomRounds >= bottomStablePatience && noNewScrollAttempts >= bottomStablePatience) {
      stopReason = byAweme.size > 0 ? "bottom_stable_no_new_queue_accepted_22C11B" : "bottom_stable_no_targets_22C11B";
      break;
    }
    if (patienceEligible && noNewScrollAttempts >= noNewPatience && stableGeometryRounds >= bottomStablePatience) {
      stopReason = byAweme.size > 0 ? "stable_no_new_after_6_scroll_attempts_22C11B" : "active_works_grid_no_targets_after_6_scroll_attempts_22C11B";
      break;
    }
    if (Date.now() - started >= maxDurationMs) {
      stopReason = "max_scroll_duration_reached_22C11B";
      break;
    }
  }
  const targets = Array.from(byAweme.values()).map((target, index) => ({ ...target, index: index + 1 }));
  return {
    targets,
    scanRounds: roundDiagnostics.length,
    stopReason,
    bottomReached,
    noNewScrollAttempts,
    diagnostics: {
      active_works_scroll_scan_version: "22C-11B-auto-scroll-hardened",
      active_works_scroll_rounds: roundDiagnostics.length,
      active_works_scroll_stop_reason: stopReason,
      active_works_scroll_bottom_reached: bottomReached ? "yes" : "no",
      active_works_no_new_scroll_attempts: noNewScrollAttempts,
      active_works_stable_bottom_rounds: stableBottomRounds,
      active_works_stable_geometry_rounds: stableGeometryRounds,
      active_works_blocked_reason: blockedReason,
      active_works_scroll_max_rounds: maxRounds,
      active_works_scroll_max_duration_ms: maxDurationMs,
      active_works_scroll_render_wait_ms: ACTIVE_WORKS_SCAN_RENDER_WAIT_MS_22C11B,
      active_works_scroll_no_new_patience: noNewPatience,
      active_works_round_diagnostics: roundDiagnostics,
      active_works_unique_aweme_count: targets.length,
      active_works_aweme_ids: targets.map((target) => target.aweme_id),
      active_works_aweme_sample_first: targets.slice(0, 5).map((target) => target.aweme_id),
      active_works_aweme_sample_last: targets.slice(-5).map((target) => target.aweme_id)
    }
  };
}

type MinimalScanProbeWaitResult22C12B = {
  result: "bridge_ready" | "profile_post_activity_detected" | "timeout_no_ready_or_post_batch";
  elapsedMs: number;
  initialSummary: PassiveNetworkProbeSummary22C12A;
  finalSummary: PassiveNetworkProbeSummary22C12A;
  initialSnapshot: ReturnType<typeof getPassiveNetworkProbeSnapshot22C12A>;
  finalSnapshot: ReturnType<typeof getPassiveNetworkProbeSnapshot22C12A>;
};

async function waitForPassiveNetworkProbeForMinimalScan22C12B(waitMs: number): Promise<MinimalScanProbeWaitResult22C12B> {
  const startedAtMs = Date.now();
  const initialSummary = { ...passiveNetworkProbeSummary22C12A };
  const initialSnapshot = getPassiveNetworkProbeSnapshot22C12A();
  const deadline = startedAtMs + Math.max(waitMs, 0);
  let result: MinimalScanProbeWaitResult22C12B["result"] = "timeout_no_ready_or_post_batch";

  while (Date.now() <= deadline) {
    const summary = passiveNetworkProbeSummary22C12A;
    const snapshot = getPassiveNetworkProbeSnapshot22C12A();
    const bridgeReady = summary.network_probe_bridge_ready === "yes";
    const hasProfilePostActivity = snapshot.profilePostBatchCount > 0 || snapshot.profilePostTargets.length > 0;
    if (bridgeReady) {
      result = "bridge_ready";
      break;
    }
    if (hasProfilePostActivity) {
      result = "profile_post_activity_detected";
      break;
    }
    await new Promise((resolve) => window.setTimeout(resolve, MINIMAL_SCAN_NETWORK_PROBE_POLL_MS_22C12B));
  }

  return {
    result,
    elapsedMs: Date.now() - startedAtMs,
    initialSummary,
    finalSummary: { ...passiveNetworkProbeSummary22C12A },
    initialSnapshot,
    finalSnapshot: getPassiveNetworkProbeSnapshot22C12A()
  };
}

type ActiveProfilePostFetchResult22C12B = {
  attempted: boolean;
  meaningfulAttempted: boolean;
  requestCount: number;
  batchCount: number;
  targets: PassiveNetworkProbeStoredTarget22C12A[];
  hasMoreState: boolean | null;
  stopReason: string;
  warmupAttempted: boolean;
  warmupAttemptCount: number;
  warmupAppliedTemplate: boolean;
  warmupStopReason: string;
  cursorValuesSample: Array<string | number>;
  cursorFieldSamples: PassiveNetworkProbeCursorFields22C12BR2[];
  endpointPath: string;
  endpointVariantsTried: string[];
  responseShape: string;
  lastHttpStatus: number | null;
  durationMs: number;
  error: string | null;
  diagnostics: Record<string, unknown>;
};

function secUserIdFromProfileUrl22C12B(rawUrl: string): string | null {
  try {
    const parsed = new URL(rawUrl, window.location.href);
    const match = parsed.pathname.match(/\/user\/([^/?#]+)/i);
    return match?.[1] ? decodeURIComponent(match[1]) : null;
  } catch {
    const match = String(rawUrl).match(/\/user\/([^/?#]+)/i);
    return match?.[1] ? decodeURIComponent(match[1]) : null;
  }
}

const ACTIVE_PROFILE_POST_REQUIRED_QUERY_KEYS_22C13B = ["sec_user_id", "count", "max_cursor"] as const;
const ACTIVE_PROFILE_POST_TEMPLATE_WARMUP_MAX_ATTEMPTS_22C13B = 3;
const ACTIVE_PROFILE_POST_TEMPLATE_WARMUP_WAIT_MS_22C13B = 220;
const ACTIVE_PROFILE_POST_TEMPLATE_WARMUP_SCROLL_DELTA_22C13B = 420;

type ActiveProfilePostTemplateSource22C13B = "performance_resource" | "passive_network_metadata_cache" | "page_shadow_cache" | "last_successful_template_cache" | "default_direct_api_fallback" | "fallback_unavailable";

type ActiveProfilePostRequestTemplate22C13B = {
  found: boolean;
  source: ActiveProfilePostTemplateSource22C13B;
  endpointPath: string;
  requestUrl: URL | null;
  queryKeys: string[];
  secretQueryKeys: string[];
  requiredQueryKeys: string[];
  requiredQueryKeysAvailable: boolean;
  missingRequiredQueryKeys: string[];
  sourcesTried: ActiveProfilePostTemplateSource22C13B[];
  selectedQueryKeys: string[];
  cacheHit: boolean;
  recoveryAttempted: boolean;
  recoverySteps: string[];
  recoveryResult: string;
  recoveryError: string | null;
  queryKeySources: Record<string, string>;
  addedDefaultCount: boolean;
  addedDefaultMaxCursor: boolean;
  derivedSecUserId: boolean;
  syntheticFallback: boolean;
};

type ActiveProfilePostFetchTier22C13B = "A_canonical" | "B_partial_inferred" | "C_last_successful_replay";

const activeProfilePostLastSuccessfulTemplateCache22C13B = new Map<string, ActiveProfilePostRequestTemplate22C13B>();

function isSensitiveProfilePostQueryKey22C13B(key: string): boolean {
  return /(token|msToken|a_bogus|x-bogus|verifyfp|signature|passport|cookie|sid|ttwid|webid|fp|device_id|iid)/i.test(key);
}

function activeProfilePostTemplateFromUrl22C13B(url: URL, source: ActiveProfilePostTemplateSource22C13B, sourcesTried: ActiveProfilePostTemplateSource22C13B[], secUserId: string, cacheHit = false): ActiveProfilePostRequestTemplate22C13B {
  const fallbackEndpointPath = "/aweme/v1/web/aweme/post/";
  const requiredQueryKeys = [...ACTIVE_PROFILE_POST_REQUIRED_QUERY_KEYS_22C13B];
  const safeUrl = new URL(url.toString());
  safeUrl.hash = "";
  const syntheticFallback = source === "fallback_unavailable";
  const queryKeySources: Record<string, string> = {};
  for (const key of Array.from(safeUrl.searchParams.keys())) queryKeySources[key] = source;
  const recoverySteps: string[] = [];
  let addedDefaultCount = false;
  let addedDefaultMaxCursor = false;
  let derivedSecUserId = false;
  if (!safeUrl.searchParams.get("sec_user_id")?.trim()) {
    safeUrl.searchParams.set("sec_user_id", secUserId);
    queryKeySources.sec_user_id = "derived_from_profile_url";
    recoverySteps.push("derived_sec_user_id_from_profile_url");
    derivedSecUserId = true;
  }
  if (!safeUrl.searchParams.get("count")?.trim()) {
    safeUrl.searchParams.set("count", String(MINIMAL_SCAN_ACTIVE_PROFILE_POST_FETCH_PAGE_SIZE_22C12B));
    queryKeySources.count = "default_profile_post_page_size";
    recoverySteps.push("added_default_count");
    addedDefaultCount = true;
  }
  if (!safeUrl.searchParams.get("max_cursor")?.trim()) {
    safeUrl.searchParams.set("max_cursor", "0");
    queryKeySources.max_cursor = "default_initial_cursor";
    recoverySteps.push("added_default_max_cursor");
    addedDefaultMaxCursor = true;
  }
  const queryKeys = Array.from(new Set(Array.from(safeUrl.searchParams.keys()).map((key) => key.trim()).filter((key) => key.length > 0))).slice(0, 64);
  const secretQueryKeys = queryKeys.filter((key) => isSensitiveProfilePostQueryKey22C13B(key)).slice(0, 32);
  const endpointPath = safeUrl.pathname && safeUrl.pathname.trim() ? safeUrl.pathname : fallbackEndpointPath;
  const missingRequiredQueryKeys = requiredQueryKeys.filter((key) => !queryKeys.includes(key));
  const usableRequiredKeys = !syntheticFallback && missingRequiredQueryKeys.length === 0;
  const directDefaultFallback = source === "default_direct_api_fallback";
  const directRecoverySteps = directDefaultFallback ? ["template_unavailable_after_warmup", "built_default_direct_api_template"] : recoverySteps;
  return { found: !syntheticFallback, source, endpointPath, requestUrl: syntheticFallback ? null : safeUrl, queryKeys: syntheticFallback ? [] : queryKeys, secretQueryKeys: syntheticFallback ? [] : secretQueryKeys, requiredQueryKeys, requiredQueryKeysAvailable: usableRequiredKeys, missingRequiredQueryKeys: usableRequiredKeys ? [] : missingRequiredQueryKeys.length > 0 ? missingRequiredQueryKeys : [...requiredQueryKeys], sourcesTried, selectedQueryKeys: syntheticFallback ? [] : queryKeys.filter((key) => !isSensitiveProfilePostQueryKey22C13B(key)), cacheHit, recoveryAttempted: !syntheticFallback && (directDefaultFallback || directRecoverySteps.length > 0), recoverySteps: syntheticFallback ? ["synthetic_fallback_not_usable"] : directRecoverySteps, recoveryResult: syntheticFallback ? "synthetic_fallback_not_usable" : directDefaultFallback && missingRequiredQueryKeys.length === 0 ? "template_recovered_from_default_direct_api" : missingRequiredQueryKeys.length === 0 ? (directRecoverySteps.length > 0 ? "recovered" : "not_needed") : "missing_required_query_keys", recoveryError: syntheticFallback ? "synthetic_fallback_not_usable" : missingRequiredQueryKeys.length === 0 ? null : `missing_required_query_keys:${missingRequiredQueryKeys.join("|")}`, queryKeySources: syntheticFallback ? {} : queryKeySources, addedDefaultCount: !syntheticFallback && addedDefaultCount, addedDefaultMaxCursor: !syntheticFallback && addedDefaultMaxCursor, derivedSecUserId: !syntheticFallback && derivedSecUserId, syntheticFallback };
}

function defaultDirectActiveProfilePostTemplate22C13B(sourcesTried: ActiveProfilePostTemplateSource22C13B[], secUserId: string): ActiveProfilePostRequestTemplate22C13B {
  const requestUrl = new URL("/aweme/v1/web/aweme/post/", window.location.origin);
  requestUrl.searchParams.set("device_platform", "webapp");
  requestUrl.searchParams.set("aid", "6383");
  requestUrl.searchParams.set("channel", "channel_pc_web");
  requestUrl.searchParams.set("sec_user_id", secUserId);
  requestUrl.searchParams.set("max_cursor", "0");
  requestUrl.searchParams.set("count", String(MINIMAL_SCAN_ACTIVE_PROFILE_POST_FETCH_PAGE_SIZE_22C12B));
  requestUrl.searchParams.set("publish_video_strategy_type", "2");
  requestUrl.searchParams.set("pc_client_type", "1");
  requestUrl.searchParams.set("version_code", "190500");
  requestUrl.searchParams.set("version_name", "19.5.0");
  requestUrl.searchParams.set("cookie_enabled", navigator.cookieEnabled ? "true" : "false");
  requestUrl.searchParams.set("screen_width", String(Math.max(Math.round(window.screen?.width ?? window.innerWidth ?? 0), 0)));
  requestUrl.searchParams.set("screen_height", String(Math.max(Math.round(window.screen?.height ?? window.innerHeight ?? 0), 0)));
  requestUrl.searchParams.set("browser_language", (navigator.language || "zh-CN").toLowerCase());
  requestUrl.searchParams.set("browser_platform", navigator.platform || "Win32");
  requestUrl.searchParams.set("browser_name", "Chrome");
  requestUrl.searchParams.set("browser_version", String(navigator.userAgent.match(/Chrome\/([\d.]+)/i)?.[1] ?? ""));
  requestUrl.searchParams.set("browser_online", navigator.onLine ? "true" : "false");
  requestUrl.searchParams.set("engine_name", "Blink");
  requestUrl.searchParams.set("os_name", /Windows/i.test(navigator.userAgent) ? "Windows" : "Unknown");
  requestUrl.searchParams.set("referer", window.location.href);
  return activeProfilePostTemplateFromUrl22C13B(requestUrl, "default_direct_api_fallback", [...sourcesTried, "default_direct_api_fallback"], secUserId, false);
}

function activeProfilePostTemplateRecoveryDiagnostics22C13B(template: ActiveProfilePostRequestTemplate22C13B, blockReason: string | null, httpStatus: number | null, statusCode: number | string | null, batchCount: number): Record<string, unknown> {
  const directApiFallback = template.source === "default_direct_api_fallback";
  const finalStrategy = template.source === "performance_resource" ? "template_discovered_from_page"
    : template.source === "passive_network_metadata_cache" || template.source === "page_shadow_cache" || template.source === "last_successful_template_cache" ? "template_recovered_from_cache"
      : directApiFallback ? "template_recovered_from_default_direct_api"
        : "template_unavailable_after_all_recovery";
  const recoveryResult = directApiFallback && batchCount > 0 ? "direct_api_fallback_batch_ok"
    : directApiFallback && (httpStatus != null || statusCode != null) ? "direct_api_fallback_response_rejected"
      : directApiFallback ? "direct_api_fallback_request_pending_or_failed"
        : blockReason ? "template_unavailable_after_all_recovery"
          : "template_ready";
  return {
    template_recovery_strategy_attempted: finalStrategy,
    template_recovery_strategies_tried: template.sourcesTried,
    template_recovery_final_strategy: finalStrategy,
    template_recovery_result: recoveryResult,
    template_recovery_block_reason: blockReason,
    template_missing_required_query_keys: template.missingRequiredQueryKeys,
    sec_user_id_present: template.queryKeys.includes("sec_user_id") ? "yes" : "no",
    direct_api_fallback_attempted: directApiFallback ? "yes" : "no",
    direct_api_fallback_url_shape_valid: directApiFallback && template.requestUrl?.origin === window.location.origin && /\/aweme\/v1\/web\/aweme\/post\/?/i.test(template.requestUrl.pathname) ? "yes" : "no",
    direct_api_fallback_http_status: directApiFallback ? httpStatus : null,
    direct_api_fallback_status_code: directApiFallback ? statusCode : null,
    direct_api_fallback_batch_count: directApiFallback ? batchCount : 0,
    active_profile_post_effective_attempted: httpStatus != null || batchCount > 0 ? "yes" : "no",
    active_profile_post_effective_attempt_reason: httpStatus != null || batchCount > 0 ? "network_request_dispatched" : (blockReason ?? "network_request_not_dispatched")
  };
}

function isUsableActiveProfilePostTemplate22C13B(template: ActiveProfilePostRequestTemplate22C13B): boolean {
  // Synthetic fallback query keys are not enough; active pagination requires a real, cached, or same-run default direct API profile-post template.
  return template.found === true
    && template.syntheticFallback !== true
    && template.source !== "fallback_unavailable"
    && template.requestUrl !== null
    && /\/aweme\/v1\/web\/aweme\/post\/?/i.test(template.endpointPath)
    && template.requiredQueryKeysAvailable === true;
}

function activeProfilePostTemplateBlockReason22C13B(template: ActiveProfilePostRequestTemplate22C13B): string | null {
  if (isUsableActiveProfilePostTemplate22C13B(template)) return null;
  const sawProfilePostEndpoint = passiveNetworkProbeProfilePostBatchCount22C12BR2 > 0 || passiveNetworkProbeTargetsByKind22C12A.profile_post.size > 0;
  if (template.syntheticFallback || template.source === "fallback_unavailable") return sawProfilePostEndpoint ? "profile_post_endpoint_seen_but_source_url_missing" : "usable_template_unavailable";
  if (!template.found) return sawProfilePostEndpoint ? "profile_post_endpoint_seen_but_source_url_missing" : "template_not_found";
  if (!template.requiredQueryKeysAvailable) return "required_query_keys_unavailable";
  if (!template.requestUrl) return "profile_post_endpoint_seen_but_source_url_missing";
  return "usable_template_unavailable";
}

async function warmupActiveProfilePostTemplate22C13B(input: { secUserId: string; initialTemplate: ActiveProfilePostRequestTemplate22C13B }): Promise<{ template: ActiveProfilePostRequestTemplate22C13B; attempted: boolean; attemptCount: number; appliedTemplate: boolean; stopReason: string; scrollAttempted: boolean; performanceResourceCount: number; networkProbeReady: boolean; postEndpointSeen: boolean }> {
  let template = input.initialTemplate;
  let attemptCount = 0;
  let appliedTemplate = false;
  let stopReason = isUsableActiveProfilePostTemplate22C13B(template) ? "template_ready_initial" : "template_warmup_exhausted";
  let scrollAttempted = false;
  let performanceResourceCount = 0;
  let postEndpointSeen = false;
  const attempted = !isUsableActiveProfilePostTemplate22C13B(template);
  if (!attempted) return { template, attempted, attemptCount, appliedTemplate, stopReason, scrollAttempted, performanceResourceCount, networkProbeReady: passiveNetworkProbeSummary22C12A.network_probe_bridge_ready === "yes", postEndpointSeen };

  // active profile-post API > same-run profile-post network template > DOM fallback evidence
  for (let attempt = 1; attempt <= ACTIVE_PROFILE_POST_TEMPLATE_WARMUP_MAX_ATTEMPTS_22C13B; attempt += 1) {
    attemptCount = attempt;
    try {
      performanceResourceCount = typeof performance !== "undefined" && typeof performance.getEntriesByType === "function" ? performance.getEntriesByType("resource").length : 0;
    } catch {
      performanceResourceCount = 0;
    }
    try {
      postEndpointSeen = postEndpointSeen || (typeof performance !== "undefined" && typeof performance.getEntriesByType === "function" && performance.getEntriesByType("resource").some((entry) => /\/aweme\/v1\/web\/aweme\/post\/?/i.test(String((entry as { name?: unknown }).name ?? ""))));
    } catch {
      // Keep previous endpoint-seen state.
    }
    const candidate = discoverActiveProfilePostRequestTemplate22C13B(input.secUserId, { includeDefaultDirectApiFallback: false });
    if (!template.found || candidate.queryKeys.length > template.queryKeys.length || isUsableActiveProfilePostTemplate22C13B(candidate)) template = candidate;
    if (isUsableActiveProfilePostTemplate22C13B(candidate)) {
      appliedTemplate = true;
      stopReason = "template_ready_after_warmup";
      break;
    }
    if (attempt === 1) {
      scrollAttempted = true;
      try {
        window.dispatchEvent(new WheelEvent("wheel", { deltaY: ACTIVE_PROFILE_POST_TEMPLATE_WARMUP_SCROLL_DELTA_22C13B, bubbles: true, cancelable: true }));
        window.scrollBy({ top: ACTIVE_PROFILE_POST_TEMPLATE_WARMUP_SCROLL_DELTA_22C13B, behavior: "instant" as ScrollBehavior });
      } catch {
        try { window.scrollBy(0, ACTIVE_PROFILE_POST_TEMPLATE_WARMUP_SCROLL_DELTA_22C13B); } catch { /* Ignore warm-up scroll failures. */ }
      }
    }
    await new Promise((resolve) => window.setTimeout(resolve, ACTIVE_PROFILE_POST_TEMPLATE_WARMUP_WAIT_MS_22C13B));
  }
  if (!appliedTemplate) {
    const warmupStopReason = activeProfilePostTemplateBlockReason22C13B(template) === "profile_post_endpoint_seen_but_source_url_missing" ? "profile_post_endpoint_seen_but_source_url_missing" : template.found ? "template_missing_required_query_keys_after_warmup" : "template_not_found_after_warmup";
    template = defaultDirectActiveProfilePostTemplate22C13B(template.sourcesTried, input.secUserId);
    appliedTemplate = isUsableActiveProfilePostTemplate22C13B(template);
    stopReason = appliedTemplate ? "template_recovered_from_default_direct_api" : warmupStopReason;
  }
  return { template, attempted, attemptCount, appliedTemplate, stopReason, scrollAttempted, performanceResourceCount, networkProbeReady: passiveNetworkProbeSummary22C12A.network_probe_bridge_ready === "yes", postEndpointSeen };
}

function emptyActiveProfilePostTemplate22C13B(sourcesTried: ActiveProfilePostTemplateSource22C13B[], secUserId?: string): ActiveProfilePostRequestTemplate22C13B {
  const requiredQueryKeys = [...ACTIVE_PROFILE_POST_REQUIRED_QUERY_KEYS_22C13B];
  const recoveryResult = secUserId ? "synthetic_fallback_not_usable" : "sec_uid_unavailable";
  return { found: false, source: "fallback_unavailable", endpointPath: "/aweme/v1/web/aweme/post/", requestUrl: null, queryKeys: [], secretQueryKeys: [], requiredQueryKeys, requiredQueryKeysAvailable: false, missingRequiredQueryKeys: [...requiredQueryKeys], sourcesTried, selectedQueryKeys: [], cacheHit: false, recoveryAttempted: false, recoverySteps: secUserId ? ["synthetic_fallback_not_usable"] : [], recoveryResult, recoveryError: recoveryResult, queryKeySources: {}, addedDefaultCount: false, addedDefaultMaxCursor: false, derivedSecUserId: false, syntheticFallback: true };
}

function discoverActiveProfilePostRequestTemplate22C13B(secUserId: string, options: { includeDefaultDirectApiFallback?: boolean } = {}): ActiveProfilePostRequestTemplate22C13B {
  const sourcesTried: ActiveProfilePostTemplateSource22C13B[] = [];
  const candidates: Array<{ url: URL; source: ActiveProfilePostTemplateSource22C13B; cacheHit?: boolean }> = [];
  const addCandidate = (rawUrl: string, source: ActiveProfilePostTemplateSource22C13B, cacheHit = false): void => {
    try {
      const parsed = new URL(rawUrl, window.location.href);
      if (parsed.origin !== window.location.origin) return;
      if (!/\/aweme\/v1\/web\/aweme\/post\/?/i.test(parsed.pathname)) return;
      const requestSecUid = parsed.searchParams.get("sec_user_id")?.trim() ?? null;
      if (requestSecUid && requestSecUid !== secUserId) return;
      candidates.push({ url: parsed, source, cacheHit });
    } catch {
      // Ignore malformed page-owned URLs.
    }
  };

  sourcesTried.push("performance_resource");
  try {
    const entries = typeof performance !== "undefined" && typeof performance.getEntriesByType === "function" ? performance.getEntriesByType("resource") : [];
    for (let index = entries.length - 1; index >= 0; index -= 1) {
      const entry = entries[index] as { name?: unknown } | null;
      if (entry && typeof entry.name === "string") addCandidate(entry.name, "performance_resource");
    }
  } catch {
    // Continue with alternate sources.
  }

  sourcesTried.push("passive_network_metadata_cache");
  try {
    for (const target of passiveNetworkProbeTargetsByKind22C12A.profile_post.values()) {
      if (target.request_url) addCandidate(target.request_url, "passive_network_metadata_cache");
    }
  } catch {
    // Continue with page shadow cache.
  }

  sourcesTried.push("page_shadow_cache");
  try {
    const cached = readDouyinNetworkCache(document, "active_profile_post_template_shadow_cache");
    for (const item of cached) {
      const metadata = item as unknown as Record<string, unknown>;
      if (typeof metadata.source === "string") addCandidate(metadata.source, "page_shadow_cache");
      if (typeof item.share_url === "string") addCandidate(item.share_url, "page_shadow_cache");
    }
  } catch {
    // Continue with last successful template cache.
  }

  const selected = candidates
    .map((candidate) => activeProfilePostTemplateFromUrl22C13B(candidate.url, candidate.source, [...sourcesTried], secUserId, candidate.cacheHit === true))
    .sort((left, right) => Number(right.requiredQueryKeysAvailable) - Number(left.requiredQueryKeysAvailable) || right.queryKeys.length - left.queryKeys.length)[0] ?? null;
  if (selected) return selected;

  sourcesTried.push("last_successful_template_cache");
  const cachedTemplate = activeProfilePostLastSuccessfulTemplateCache22C13B.get(secUserId) ?? null;
  if (cachedTemplate) return { ...cachedTemplate, source: "last_successful_template_cache", sourcesTried: [...sourcesTried], cacheHit: true, recoveryResult: "template_recovered_from_cache" };
  if (options.includeDefaultDirectApiFallback === true && secUserId) return defaultDirectActiveProfilePostTemplate22C13B(sourcesTried, secUserId);
  return emptyActiveProfilePostTemplate22C13B(sourcesTried, secUserId);
}

function buildActiveProfilePostRequestUrl22C13B(input: {
  template: ActiveProfilePostRequestTemplate22C13B;
  endpointPath: string;
  secUserId: string;
  cursor: string | number | null;
}): URL {
  const base = input.template.requestUrl ? new URL(input.template.requestUrl.toString()) : new URL(input.endpointPath, window.location.origin);
  base.hash = "";
  base.searchParams.set("sec_user_id", input.secUserId);
  base.searchParams.set("count", String(MINIMAL_SCAN_ACTIVE_PROFILE_POST_FETCH_PAGE_SIZE_22C12B));
  base.searchParams.set("max_cursor", String(input.cursor ?? 0));
  return base;
}

function activeProfilePostFetchTier22C13B(template: ActiveProfilePostRequestTemplate22C13B): ActiveProfilePostFetchTier22C13B {
  if (isUsableActiveProfilePostTemplate22C13B(template)) return "A_canonical";
  if (template.found && template.queryKeys.includes("sec_user_id")) return "B_partial_inferred";
  if (template.cacheHit) return "C_last_successful_replay";
  return "B_partial_inferred";
}

function inspectActiveProfilePostResponse22C13B(payload: unknown): {
  statusCode: number | string | null;
  statusMsg: string | null;
  topLevelKeys: string[];
  dataKeys: string[];
  resultKeys: string[];
  parserPathCounts: Record<string, number>;
  listSampleKeys: string[];
  rejectReasons: string[];
} {
  const top = objectLike22C12B(payload);
  const data = objectLike22C12B(pathValue22C12B(payload, ["data"]));
  const result = objectLike22C12B(pathValue22C12B(payload, ["result"]));
  const topLevelKeys = top ? Object.keys(top).slice(0, 24) : [];
  const dataKeys = data ? Object.keys(data).slice(0, 24) : [];
  const resultKeys = result ? Object.keys(result).slice(0, 24) : [];
  const statusCodeRaw = top?.status_code
    ?? top?.statusCode
    ?? data?.status_code
    ?? data?.statusCode
    ?? result?.status_code
    ?? result?.statusCode
    ?? null;
  const statusCode = typeof statusCodeRaw === "number" || typeof statusCodeRaw === "string"
    ? statusCodeRaw
    : null;
  const statusMsgRaw = top?.status_msg
    ?? top?.statusMsg
    ?? top?.message
    ?? data?.status_msg
    ?? data?.statusMsg
    ?? data?.message
    ?? result?.status_msg
    ?? result?.statusMsg
    ?? result?.message
    ?? null;
  const statusMsg = typeof statusMsgRaw === "string" && statusMsgRaw.trim() ? statusMsgRaw.trim() : null;

  const parserPathDefs: Array<{ key: string; path: string[] }> = [
    { key: "aweme_list", path: ["aweme_list"] },
    { key: "item_list", path: ["item_list"] },
    { key: "list", path: ["list"] },
    { key: "items", path: ["items"] },
    { key: "data.aweme_list", path: ["data", "aweme_list"] },
    { key: "data.item_list", path: ["data", "item_list"] },
    { key: "data.list", path: ["data", "list"] },
    { key: "data.items", path: ["data", "items"] },
    { key: "result.aweme_list", path: ["result", "aweme_list"] },
    { key: "result.item_list", path: ["result", "item_list"] },
    { key: "result.list", path: ["result", "list"] },
    { key: "result.items", path: ["result", "items"] }
  ];

  const parserPathCounts: Record<string, number> = {};
  const listSampleKeys: string[] = [];
  for (const candidate of parserPathDefs) {
    const value = pathValue22C12B(payload, candidate.path);
    if (!Array.isArray(value)) {
      parserPathCounts[candidate.key] = 0;
      continue;
    }
    parserPathCounts[candidate.key] = value.length;
    for (const entry of value.slice(0, 2)) {
      const record = objectLike22C12B(entry);
      if (!record) continue;
      const keys = Object.keys(record).slice(0, 8);
      if (keys.length === 0) continue;
      const sample = `${candidate.key}:${keys.join(",")}`;
      if (!listSampleKeys.includes(sample)) listSampleKeys.push(sample);
      if (listSampleKeys.length >= 12) break;
    }
    if (listSampleKeys.length >= 12) break;
  }

  const rejectReasons: string[] = [];
  const totalListCandidates = Object.values(parserPathCounts).reduce((sum, value) => sum + value, 0);
  if (totalListCandidates === 0) rejectReasons.push("no_list_candidates_detected");
  if (statusCode != null && statusCode !== 0 && statusCode !== "0") rejectReasons.push("active_profile_post_response_status_non_zero");
  if (top == null && !Array.isArray(payload)) rejectReasons.push("response_not_json_object_or_array");

  return {
    statusCode,
    statusMsg,
    topLevelKeys,
    dataKeys,
    resultKeys,
    parserPathCounts,
    listSampleKeys,
    rejectReasons
  };
}

function mergeNetworkStoredTargets22C12B(
  passiveTargets: PassiveNetworkProbeStoredTarget22C12A[],
  activeTargets: PassiveNetworkProbeStoredTarget22C12A[]
): PassiveNetworkProbeStoredTarget22C12A[] {
  const merged = new Map<string, PassiveNetworkProbeStoredTarget22C12A>();
  for (const target of passiveTargets) merged.set(target.aweme_id, target);
  for (const target of activeTargets) {
    const existing = merged.get(target.aweme_id);
    if (!existing) {
      merged.set(target.aweme_id, target);
      continue;
    }
    merged.set(target.aweme_id, {
      ...existing,
      source_url: existing.source_url || target.source_url,
      desc: existing.desc ?? target.desc,
      cover_url: existing.cover_url ?? target.cover_url,
      duration: existing.duration ?? target.duration,
      create_time: existing.create_time ?? target.create_time,
      like_count: existing.like_count ?? target.like_count,
      comment_count: existing.comment_count ?? target.comment_count,
      share_count: existing.share_count ?? target.share_count,
      captured_at: existing.captured_at || target.captured_at
    });
  }
  return Array.from(merged.values());
}

type ActiveProfilePostExtractedBatch22C12B = NonNullable<ReturnType<typeof extractPassiveNetworkBatch22C12A>>;

type ActiveProfilePostExtractionOutcome22C12B = {
  batch: ActiveProfilePostExtractedBatch22C12B | null;
  parserRoute: string;
  parserRoutesTried: string[];
  directRoutesTried: string[];
  directMatchCount: number;
  fallbackAttempted: boolean;
  fallbackMatchCount: number;
  fallbackCandidateCount: number;
  fallbackVisitedNodes: number;
};

function objectLike22C12B(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : null;
}

function pathValue22C12B(value: unknown, path: string[]): unknown {
  let cursor: unknown = value;
  for (const key of path) {
    const record = objectLike22C12B(cursor);
    if (!record || !(key in record)) return undefined;
    cursor = record[key];
  }
  return cursor;
}

function extractActiveProfilePostBatchWithFallback22C12B(input: {
  payload: unknown;
  endpointPath: string;
  method: "GET" | "POST";
  status: number | null;
}): ActiveProfilePostExtractionOutcome22C12B {
  const parserRoutesTried: string[] = [];
  const directRoutesTried: string[] = [];
  let directMatchCount = 0;
  const pushRoute = (value: string): void => {
    if (!value || parserRoutesTried.includes(value)) return;
    parserRoutesTried.push(value);
  };
  const pushDirectRoute = (value: string): void => {
    if (!value || directRoutesTried.includes(value)) return;
    directRoutesTried.push(value);
  };

  const tryExtract = (route: string, payload: unknown, origin: "direct" | "fallback"): ActiveProfilePostExtractedBatch22C12B | null => {
    pushRoute(route);
    if (origin === "direct") pushDirectRoute(route);
    const batch = extractPassiveNetworkBatch22C12A({
      payload,
      urlPath: input.endpointPath,
      method: input.method,
      status: input.status
    });
    if (batch && origin === "direct") directMatchCount += 1;
    return batch ? batch as ActiveProfilePostExtractedBatch22C12B : null;
  };

  const directPaths: Array<{ route: string; path: string[] }> = [
    { route: "primary_payload", path: [] },
    { route: "direct:data", path: ["data"] },
    { route: "direct:data.data", path: ["data", "data"] },
    { route: "direct:data.result", path: ["data", "result"] },
    { route: "direct:data.result.data", path: ["data", "result", "data"] },
    { route: "direct:data.response", path: ["data", "response"] },
    { route: "direct:data.payload", path: ["data", "payload"] },
    { route: "direct:data.aweme_list", path: ["data", "aweme_list"] },
    { route: "direct:data.item_list", path: ["data", "item_list"] },
    { route: "direct:data.list", path: ["data", "list"] },
    { route: "direct:data.items", path: ["data", "items"] },
    { route: "direct:aweme_list", path: ["aweme_list"] },
    { route: "direct:item_list", path: ["item_list"] },
    { route: "direct:list", path: ["list"] },
    { route: "direct:items", path: ["items"] },
    { route: "direct:result", path: ["result"] },
    { route: "direct:result.data", path: ["result", "data"] },
    { route: "direct:result.data.aweme_list", path: ["result", "data", "aweme_list"] },
    { route: "direct:result.data.item_list", path: ["result", "data", "item_list"] },
    { route: "direct:result.data.list", path: ["result", "data", "list"] },
    { route: "direct:result.data.items", path: ["result", "data", "items"] },
    { route: "direct:payload", path: ["payload"] },
    { route: "direct:payload.data", path: ["payload", "data"] },
    { route: "direct:payload.result", path: ["payload", "result"] },
    { route: "direct:payload.response", path: ["payload", "response"] },
    { route: "direct:response", path: ["response"] },
    { route: "direct:response.data", path: ["response", "data"] },
    { route: "direct:response.data.data", path: ["response", "data", "data"] },
    { route: "direct:response.result", path: ["response", "result"] }
  ];

  for (const candidate of directPaths) {
    const candidatePayload = candidate.path.length === 0 ? input.payload : pathValue22C12B(input.payload, candidate.path);
    const batch = tryExtract(candidate.route, candidatePayload, "direct");
    if (!batch) continue;
    return {
      batch,
      parserRoute: candidate.route,
      parserRoutesTried,
      directRoutesTried,
      directMatchCount,
      fallbackAttempted: false,
      fallbackMatchCount: 0,
      fallbackCandidateCount: 0,
      fallbackVisitedNodes: 0
    };
  }

  const fallbackCandidates: Array<{ route: string; payload: unknown }> = [];
  const seenObjects = new WeakSet<object>();
  const addCandidate = (route: string, candidate: unknown): void => {
    if (!candidate || typeof candidate !== "object") return;
    const objectCandidate = candidate as object;
    if (seenObjects.has(objectCandidate)) return;
    seenObjects.add(objectCandidate);
    fallbackCandidates.push({ route, payload: candidate });
  };

  const fallbackExplicitPaths: Array<{ route: string; path: string[] }> = [
    { route: "fallback:data", path: ["data"] },
    { route: "fallback:data.data", path: ["data", "data"] },
    { route: "fallback:data.result", path: ["data", "result"] },
    { route: "fallback:data.result.data", path: ["data", "result", "data"] },
    { route: "fallback:data.response", path: ["data", "response"] },
    { route: "fallback:data.payload", path: ["data", "payload"] },
    { route: "fallback:data.aweme_list", path: ["data", "aweme_list"] },
    { route: "fallback:data.item_list", path: ["data", "item_list"] },
    { route: "fallback:data.list", path: ["data", "list"] },
    { route: "fallback:data.items", path: ["data", "items"] },
    { route: "fallback:aweme_list", path: ["aweme_list"] },
    { route: "fallback:item_list", path: ["item_list"] },
    { route: "fallback:list", path: ["list"] },
    { route: "fallback:items", path: ["items"] },
    { route: "fallback:result", path: ["result"] },
    { route: "fallback:result.data", path: ["result", "data"] },
    { route: "fallback:result.data.aweme_list", path: ["result", "data", "aweme_list"] },
    { route: "fallback:result.data.item_list", path: ["result", "data", "item_list"] },
    { route: "fallback:result.data.list", path: ["result", "data", "list"] },
    { route: "fallback:result.data.items", path: ["result", "data", "items"] },
    { route: "fallback:payload", path: ["payload"] },
    { route: "fallback:payload.data", path: ["payload", "data"] },
    { route: "fallback:payload.result", path: ["payload", "result"] },
    { route: "fallback:payload.response", path: ["payload", "response"] },
    { route: "fallback:response", path: ["response"] },
    { route: "fallback:response.data", path: ["response", "data"] },
    { route: "fallback:response.data.data", path: ["response", "data", "data"] },
    { route: "fallback:response.result", path: ["response", "result"] }
  ];
  for (const candidate of fallbackExplicitPaths) addCandidate(candidate.route, pathValue22C12B(input.payload, candidate.path));

  const fallbackVisitLimit = 180;
  const fallbackDepthLimit = 6;
  const fallbackArrayScanLimit = 12;
  const fallbackObjectEntryLimit = 24;
  const stack: Array<{ value: unknown; route: string; depth: number }> = [{ value: input.payload, route: "root", depth: 0 }];
  let visitedNodes = 0;
  while (stack.length && visitedNodes < fallbackVisitLimit) {
    const current = stack.pop();
    if (!current) break;
    visitedNodes += 1;
    if (current.depth > fallbackDepthLimit || !current.value || typeof current.value !== "object") continue;

    if (Array.isArray(current.value)) {
      const sample = current.value.slice(0, fallbackArrayScanLimit);
      for (let index = sample.length - 1; index >= 0; index -= 1) {
        const next = sample[index];
        if (next && typeof next === "object") stack.push({ value: next, route: `${current.route}[${index}]`, depth: current.depth + 1 });
      }
      continue;
    }

    const record = current.value as Record<string, unknown>;
    const entries = Object.entries(record).slice(0, fallbackObjectEntryLimit);
    for (let index = entries.length - 1; index >= 0; index -= 1) {
      const [key, next] = entries[index]!;
      if (!next || typeof next !== "object") continue;
      const nextRoute = `${current.route}.${key}`;
      stack.push({ value: next, route: nextRoute, depth: current.depth + 1 });
      if (/(aweme(?:_id)?|awemeId|post|works?|list|items?|card|data|result|payload|response|detail)/i.test(key)) {
        addCandidate(`fallback:${nextRoute.replace(/^root\./, "")}`, next);
      }
    }
  }

  for (const candidate of fallbackCandidates) {
    const batch = tryExtract(candidate.route, candidate.payload, "fallback");
    if (!batch) continue;
    return {
      batch,
      parserRoute: candidate.route,
      parserRoutesTried,
      directRoutesTried,
      directMatchCount,
      fallbackAttempted: true,
      fallbackMatchCount: 1,
      fallbackCandidateCount: fallbackCandidates.length,
      fallbackVisitedNodes: visitedNodes
    };
  }

  return {
    batch: null,
    parserRoute: "none",
    parserRoutesTried,
    directRoutesTried,
    directMatchCount,
    fallbackAttempted: fallbackCandidates.length > 0 || visitedNodes > 0,
    fallbackMatchCount: 0,
    fallbackCandidateCount: fallbackCandidates.length,
    fallbackVisitedNodes: visitedNodes
  };
}

async function runActiveProfilePostPageFetch22C14B(message: ExtensionMessage, receivedAt: string): Promise<ExtensionMessageResponse> {
  const profileUrl = canonicalProfileUrl22C12B((message.profileUrl ?? message.expected_profile_url ?? window.location.href).trim());
  const scanJobId = message.scan_job_id ?? message.scanRunId ?? message.scan_run_id ?? message.run_id ?? null;
  const cursor = typeof message.cursor === "string" || typeof message.cursor === "number" ? message.cursor : 0;
  const pageIndex = Number.isFinite(message.page_index) && message.page_index != null ? Math.max(Math.trunc(message.page_index), 0) : 0;
  const fallbackEndpointVariants = ["/aweme/v1/web/aweme/post/", "/aweme/v1/web/aweme/post"];
  const secUserId = secUserIdFromProfileUrl22C12B(profileUrl);
  const startedAt = Date.now();
  if (!secUserId) {
    return { ok: false, traceVersion: "22C-14B", messageTypeHandled: message.type, reason: "sec_uid_missing_from_profile_url", verified_targets: [], verified_target_details: [], scan_rounds: 0, stop_reason: "sec_uid_missing_from_profile_url", total_candidates: 0, rejected_count: 1, rejected_reasons: ["sec_uid_missing_from_profile_url"], diagnostics: { active_profile_post_page_fetch_received: "yes", active_profile_post_page_fetch_received_at: receivedAt, scan_job_id: scanJobId, scan_job_cursor: cursor, scan_job_page_index: pageIndex, active_profile_post_page_fetch_stop_reason_22C14B: "sec_uid_missing_from_profile_url", content_script_version: CONTENT_SCRIPT_VERSION, content_script_supported_handlers: [...CONTENT_SCRIPT_SUPPORTED_HANDLERS] } };
  }

  const originalProfileUrl = (message.profileUrl ?? message.expected_profile_url ?? window.location.href).trim();
  let template = discoverActiveProfilePostRequestTemplate22C13B(secUserId);
  const warmup = await warmupActiveProfilePostTemplate22C13B({ secUserId, initialTemplate: template });
  template = warmup.template;
  const tier = activeProfilePostFetchTier22C13B(template);
  const templateBlockReason = activeProfilePostTemplateBlockReason22C13B(template);
  const endpointVariants = templateBlockReason ? [] : Array.from(new Set([template.endpointPath, ...fallbackEndpointVariants].filter((value): value is string => typeof value === "string" && value.trim().length > 0)));
  const profileScope = canonicalProfileUrl22C12B(profileUrl);
  const rejectReasons = new Set<string>();
  const endpointAttemptSamples: Record<string, unknown>[] = [];
  let lastHttpStatus: number | null = null;
  let lastStatusCode: number | string | null = null;
  let statusMsg: string | null = null;
  let responseShape = "unknown";
  let stopReason = "endpoint_variants_exhausted_no_batch";
  let error: string | null = null;
  let hasMoreState: boolean | null = null;
  let nextCursor: string | number | null = null;
  let parserRoute = "none";
  let parserRoutesTried: string[] = [];
  let parserDirectRoutesTried: string[] = [];
  let rawPageItemCount = 0;
  let rawPageAwemeIdCount = 0;
  let emptyOrMissingAwemeIdCount = 0;
  let targets: PassiveNetworkProbeStoredTarget22C12A[] = [];

  if (templateBlockReason) {
    rejectReasons.add(templateBlockReason);
    stopReason = templateBlockReason;
    error = templateBlockReason;
  }

  for (let endpointIndex = 0; endpointIndex < endpointVariants.length; endpointIndex += 1) {
    const endpointPath = endpointVariants[endpointIndex]!;
    const requestUrl = buildActiveProfilePostRequestUrl22C13B({ template, endpointPath, secUserId, cursor });
    const requestStartedAt = Date.now();
    const controller = typeof AbortController === "function" ? new AbortController() : null;
    const timeout = window.setTimeout(() => controller?.abort(), MINIMAL_SCAN_ACTIVE_PROFILE_POST_FETCH_TIMEOUT_MS_22C12B);
    let status: number | null = null;
    let payload: unknown = null;
    try {
      const response = await fetch(requestUrl.toString(), { method: "GET", credentials: "include", signal: controller?.signal ?? null, headers: { Accept: "application/json, text/plain, */*" } });
      status = response.status;
      lastHttpStatus = status;
      payload = await response.json().catch(() => null);
      responseShape = payload && typeof payload === "object" ? "json_object" : Array.isArray(payload) ? "json_array" : payload == null ? "null" : typeof payload;
      const inspection = inspectActiveProfilePostResponse22C13B(payload);
      lastStatusCode = inspection.statusCode;
      statusMsg = inspection.statusMsg;
      for (const reason of inspection.rejectReasons) rejectReasons.add(reason);
      if (inspection.statusCode != null && inspection.statusCode !== 0 && inspection.statusCode !== "0") {
        stopReason = "active_profile_post_response_status_non_zero";
        error = stopReason;
        template = discoverActiveProfilePostRequestTemplate22C13B(secUserId);
        endpointAttemptSamples.push({ page: pageIndex + 1, endpoint_path: endpointPath, status, result: stopReason, response_status_code: inspection.statusCode, response_status_msg: inspection.statusMsg, duration_ms: Math.max(Date.now() - requestStartedAt, 0) });
        continue;
      }
      if (!response.ok) {
        stopReason = "response_not_ok";
        error = status == null ? stopReason : `http_status_${status}`;
        endpointAttemptSamples.push({ page: pageIndex + 1, endpoint_path: endpointPath, status, result: stopReason, duration_ms: Math.max(Date.now() - requestStartedAt, 0) });
        continue;
      }
      const extraction = extractActiveProfilePostBatchWithFallback22C12B({ payload, endpointPath, method: "GET", status });
      parserRoute = extraction.parserRoute;
      parserRoutesTried = extraction.parserRoutesTried;
      parserDirectRoutesTried = extraction.directRoutesTried;
      if (!extraction.batch) {
        stopReason = "extractor_no_targets";
        error = stopReason;
        endpointAttemptSamples.push({ page: pageIndex + 1, endpoint_path: endpointPath, status, result: stopReason, duration_ms: Math.max(Date.now() - requestStartedAt, 0) });
        continue;
      }
      const batch = extraction.batch;
      rawPageItemCount = batch.awemeCount;
      rawPageAwemeIdCount = batch.targets.filter((target) => typeof target.aweme_id === "string" && /^\d{8,}$/.test(target.aweme_id)).length;
      emptyOrMissingAwemeIdCount = Math.max(rawPageItemCount - rawPageAwemeIdCount, 0);
      activeProfilePostLastSuccessfulTemplateCache22C13B.set(secUserId, template);
      hasMoreState = batch.hasMore ?? null;
      nextCursor = batch.cursorFields?.max_cursor ?? batch.cursorFields?.next_cursor ?? batch.cursor ?? null;
      targets = batch.targets.map((target) => buildPassiveNetworkStoredTarget22C12A({ target, profileUrl: profileScope, urlPath: endpointPath, capturedAt: receivedAt }));
      stopReason = batch.hasMore === false ? "has_more_false" : nextCursor == null ? "cursor_absent" : "page_ok_has_more";
      error = null;
      endpointAttemptSamples.push({ page: pageIndex + 1, endpoint_path: endpointPath, status, result: "batch_ok", parser_route: parserRoute, duration_ms: Math.max(Date.now() - requestStartedAt, 0) });
      break;
    } catch (caught) {
      const caughtError = caught instanceof Error ? caught : new Error(String(caught));
      stopReason = caughtError.name === "AbortError" ? "request_timeout" : "request_exception";
      error = stopReason;
      rejectReasons.add(stopReason);
      endpointAttemptSamples.push({ page: pageIndex + 1, endpoint_path: endpointPath, status, result: stopReason, duration_ms: Math.max(Date.now() - requestStartedAt, 0) });
    } finally {
      clearTimeout(timeout);
    }
  }

  const verifiedTargets = buildNetworkFirstProfileTargets22C12B(targets).map((target, index) => ({ ...target, index: pageIndex * MINIMAL_SCAN_ACTIVE_PROFILE_POST_FETCH_PAGE_SIZE_22C12B + index + 1, discovery_source: "active_profile_post_page_22C14B" }));
  return {
    ok: error == null,
    traceVersion: "22C-14B",
    messageTypeHandled: message.type,
    reason: error,
    verified_targets: verifiedTargets.map((target) => target.aweme_id),
    verified_target_details: verifiedTargets,
    scan_rounds: 1,
    stop_reason: stopReason,
    total_candidates: verifiedTargets.length,
    rejected_count: Array.from(rejectReasons).length,
    rejected_reasons: Array.from(rejectReasons),
    diagnostics: {
      active_profile_post_page_fetch_received: "yes",
      active_profile_post_page_fetch_received_at: receivedAt,
      active_profile_post_page_fetch_result: error == null ? "completed" : "failed",
      active_profile_post_page_fetch_stop_reason_22C14B: stopReason,
      active_profile_post_page_fetch_duration_ms_22C14B: Math.max(Date.now() - startedAt, 0),
      active_profile_post_page_fetch_raw_item_count_22C14B: rawPageItemCount,
      active_profile_post_page_fetch_raw_aweme_id_count_22C14B: rawPageAwemeIdCount,
      active_profile_post_page_fetch_empty_or_missing_aweme_id_count_22C14B: emptyOrMissingAwemeIdCount,
      active_profile_post_page_fetch_target_count_22C14B: verifiedTargets.length,
      active_profile_post_page_fetch_endpoint_path_22C14B: targets[0]?.endpoint_path ?? endpointVariants[0] ?? null,
      active_profile_post_page_fetch_endpoint_attempt_samples_22C14B: endpointAttemptSamples,
      active_profile_post_page_fetch_parser_route_22C14B: parserRoute,
      active_profile_post_page_fetch_parser_routes_tried_22C14B: parserRoutesTried,
      active_profile_post_page_fetch_parser_direct_routes_tried_22C14B: parserDirectRoutesTried,
      active_profile_post_page_fetch_response_shape_22C14B: responseShape,
      active_profile_post_page_fetch_last_http_status_22C14B: lastHttpStatus,
      active_profile_post_page_fetch_last_status_code_22C14B: lastStatusCode,
      active_profile_post_page_fetch_status_msg_22C14B: statusMsg,
      active_profile_post_page_fetch_error_22C14B: error,
      active_profile_post_template_usable: isUsableActiveProfilePostTemplate22C13B(template) ? "yes" : "no",
      active_profile_post_template_usable_reason: isUsableActiveProfilePostTemplate22C13B(template) ? "usable" : activeProfilePostTemplateBlockReason22C13B(template),
      active_profile_post_template_is_synthetic: template.syntheticFallback ? "yes" : "no",
      active_profile_post_template_recovery_attempted: template.recoveryAttempted ? "yes" : "no",
      active_profile_post_template_recovery_steps: template.recoverySteps,
      active_profile_post_template_recovery_result: template.recoveryResult,
      active_profile_post_template_recovery_error: template.recoveryError,
      active_profile_post_template_query_key_sources: template.queryKeySources,
      active_profile_post_template_added_default_count: template.addedDefaultCount ? "yes" : "no",
      active_profile_post_template_added_default_max_cursor: template.addedDefaultMaxCursor ? "yes" : "no",
      active_profile_post_template_derived_sec_user_id: template.derivedSecUserId ? "yes" : "no",
      active_profile_post_canonical_profile_url: profileUrl,
      active_profile_post_original_profile_url: originalProfileUrl,
      active_profile_post_warmup_scroll_attempted: warmup.scrollAttempted ? "yes" : "no",
      active_profile_post_warmup_performance_resource_count: warmup.performanceResourceCount,
      active_profile_post_warmup_network_probe_ready: warmup.networkProbeReady ? "yes" : "no",
      active_profile_post_warmup_post_endpoint_seen: warmup.postEndpointSeen ? "yes" : "no",
      active_profile_post_start_blocked_reason: templateBlockReason,
      ...activeProfilePostTemplateRecoveryDiagnostics22C13B(template, templateBlockReason, lastHttpStatus, lastStatusCode, targets.length > 0 ? 1 : 0),
      minimal_scan_active_profile_post_template_warmup_attempted_22C13B: warmup.attempted ? "yes" : "no",
      minimal_scan_active_profile_post_template_warmup_attempt_count_22C13B: warmup.attemptCount,
      minimal_scan_active_profile_post_template_warmup_applied_template_22C13B: warmup.appliedTemplate ? "yes" : "no",
      minimal_scan_active_profile_post_template_warmup_stop_reason_22C13B: warmup.stopReason,
      minimal_scan_active_profile_post_template_sources_tried_22C13B: template.sourcesTried,
      minimal_scan_active_profile_post_template_source_selected_22C13B: template.source,
      minimal_scan_active_profile_post_template_selected_query_keys_22C13B: isUsableActiveProfilePostTemplate22C13B(template) ? template.selectedQueryKeys : [],
      minimal_scan_active_profile_post_template_found_22C13B: isUsableActiveProfilePostTemplate22C13B(template) ? "yes" : "no",
      minimal_scan_active_profile_post_template_source_22C13B: isUsableActiveProfilePostTemplate22C13B(template) ? template.source : "none",
      minimal_scan_active_profile_post_template_endpoint_path_22C13B: isUsableActiveProfilePostTemplate22C13B(template) ? template.endpointPath : "none",
      minimal_scan_active_profile_post_template_query_keys_22C13B: isUsableActiveProfilePostTemplate22C13B(template) ? template.queryKeys : [],
      minimal_scan_active_profile_post_template_required_query_keys_22C13B: template.requiredQueryKeys,
      minimal_scan_active_profile_post_template_required_query_keys_available_22C13B: isUsableActiveProfilePostTemplate22C13B(template) ? "yes" : "no",
      minimal_scan_active_profile_post_template_missing_required_query_keys_22C13B: isUsableActiveProfilePostTemplate22C13B(template) ? [] : template.requiredQueryKeys,
      minimal_scan_active_profile_post_template_cache_hit_22C13B: template.cacheHit ? "yes" : "no",
      minimal_scan_active_profile_post_fetch_tier_attempted_22C13B: tier,
      minimal_scan_active_profile_post_fetch_tier_result_22C13B: error == null ? "usable" : "failed",
      minimal_scan_active_profile_post_fetch_tier_failure_reason_22C13B: error,
      minimal_scan_active_profile_post_fetch_status_non_zero_retryable_22C13B: lastStatusCode != null && lastStatusCode !== 0 && lastStatusCode !== "0" ? "yes" : "no",
      minimal_scan_active_profile_post_fetch_last_non_zero_code_22C13B: lastStatusCode != null && lastStatusCode !== 0 && lastStatusCode !== "0" ? lastStatusCode : null,
      minimal_scan_active_profile_post_fetch_last_non_zero_reason_22C13B: lastStatusCode != null && lastStatusCode !== 0 && lastStatusCode !== "0" ? statusMsg : null,
      active_profile_post_page_fetch_cursor_22C14B: cursor,
      active_profile_post_page_fetch_next_cursor_22C14B: nextCursor,
      active_profile_post_page_fetch_has_more_state_22C14B: hasMoreState,
      scan_job_id: scanJobId,
      scan_job_cursor: nextCursor,
      scan_job_has_more_state: hasMoreState,
      scan_job_page_index: pageIndex,
      scan_job_last_http_status: lastHttpStatus,
      scan_job_last_status_code: lastStatusCode,
      scan_job_last_error: error,
      content_script_version: CONTENT_SCRIPT_VERSION,
      content_script_supported_handlers: [...CONTENT_SCRIPT_SUPPORTED_HANDLERS]
    }
  };
}

async function runActiveSameOriginProfilePostFetch22C12B(profileUrl: string): Promise<ActiveProfilePostFetchResult22C12B> {
  const fallbackEndpointVariants = ["/aweme/v1/web/aweme/post/", "/aweme/v1/web/aweme/post"];
  const secUserId = secUserIdFromProfileUrl22C12B(profileUrl);
  if (!secUserId) {
    return {
      attempted: false,
      meaningfulAttempted: false,
      requestCount: 0,
      batchCount: 0,
      targets: [],
      hasMoreState: null,
      stopReason: "sec_uid_missing_from_profile_url",
      warmupAttempted: false,
      warmupAttemptCount: 0,
      warmupAppliedTemplate: false,
      warmupStopReason: "sec_uid_missing_from_profile_url",
      cursorValuesSample: [],
      cursorFieldSamples: [],
      endpointPath: fallbackEndpointVariants[0]!,
      endpointVariantsTried: [],
      responseShape: "not_attempted",
      lastHttpStatus: null,
      durationMs: 0,
      error: "sec_uid_missing_from_profile_url",
      diagnostics: {
        minimal_scan_active_profile_post_fetch_enabled_22C12B: "no",
        minimal_scan_active_profile_post_fetch_attempted_22C12B: "no",
        minimal_scan_active_profile_post_fetch_stop_reason_22C12B: "sec_uid_missing_from_profile_url",
        minimal_scan_active_profile_post_fetch_not_attempted_reason_22C12B: "sec_uid_missing_from_profile_url",
        minimal_scan_active_profile_post_fetch_response_shape_22C12B: "not_attempted",
        minimal_scan_active_profile_post_fetch_last_http_status_22C12B: null,
        minimal_scan_active_profile_post_fetch_duration_ms_22C12B: 0,
        minimal_scan_active_profile_post_fetch_error_22C12B: "sec_uid_missing_from_profile_url",
        minimal_scan_active_profile_post_fetch_endpoint_used_22C12B: fallbackEndpointVariants[0],
        minimal_scan_active_profile_post_fetch_endpoint_variants_tried_22C12B: [],
        minimal_scan_active_profile_post_fetch_endpoint_variant_attempt_count_22C12B: 0,
        minimal_scan_active_profile_post_fetch_endpoint_variant_success_22C12B: null,
        minimal_scan_active_profile_post_fetch_endpoint_attempt_samples_22C12B: [],
        minimal_scan_active_profile_post_fetch_parser_route_22C12B: "none",
        minimal_scan_active_profile_post_fetch_parser_routes_tried_22C12B: [],
        minimal_scan_active_profile_post_fetch_parser_direct_routes_tried_22C12B: [],
        minimal_scan_active_profile_post_fetch_parser_direct_match_count_22C12B: 0,
        minimal_scan_active_profile_post_fetch_parser_fallback_attempted_22C12B: "no",
        minimal_scan_active_profile_post_fetch_parser_fallback_match_count_22C12B: 0,
        minimal_scan_active_profile_post_fetch_parser_fallback_candidate_count_22C12B: 0,
        minimal_scan_active_profile_post_fetch_parser_fallback_visited_nodes_22C12B: 0,
        minimal_scan_active_profile_post_fetch_effective_attempted_22C13B: "no",
        minimal_scan_active_profile_post_fetch_effective_attempt_reason_22C13B: "sec_uid_missing_from_profile_url",
        active_profile_post_template_usable: "no",
        active_profile_post_template_usable_reason: "sec_uid_missing_from_profile_url",
        active_profile_post_template_is_synthetic: "yes",
        minimal_scan_active_profile_post_template_warmup_attempted_22C13B: "no",
        minimal_scan_active_profile_post_template_warmup_attempt_count_22C13B: 0,
        minimal_scan_active_profile_post_template_warmup_applied_template_22C13B: "no",
        minimal_scan_active_profile_post_template_warmup_stop_reason_22C13B: "sec_uid_missing_from_profile_url",
        minimal_scan_active_profile_post_template_found_22C13B: "no",
        minimal_scan_active_profile_post_template_source_22C13B: "fallback_unavailable",
        minimal_scan_active_profile_post_template_endpoint_path_22C13B: fallbackEndpointVariants[0],
        minimal_scan_active_profile_post_template_query_keys_22C13B: [],
        minimal_scan_active_profile_post_template_required_query_keys_22C13B: [...ACTIVE_PROFILE_POST_REQUIRED_QUERY_KEYS_22C13B],
        minimal_scan_active_profile_post_template_required_query_keys_available_22C13B: "no",
        minimal_scan_active_profile_post_template_missing_required_query_keys_22C13B: [...ACTIVE_PROFILE_POST_REQUIRED_QUERY_KEYS_22C13B],
        minimal_scan_active_profile_post_template_secret_keys_present_22C13B: "no",
        minimal_scan_active_profile_post_template_secret_query_keys_22C13B: [],
        minimal_scan_active_profile_post_fetch_response_status_code_22C13B: null,
        minimal_scan_active_profile_post_fetch_response_status_msg_22C13B: null,
        minimal_scan_active_profile_post_fetch_response_top_level_keys_22C13B: [],
        minimal_scan_active_profile_post_fetch_response_data_keys_22C13B: [],
        minimal_scan_active_profile_post_fetch_response_result_keys_22C13B: [],
        minimal_scan_active_profile_post_fetch_parser_path_counts_22C13B: {},
        minimal_scan_active_profile_post_fetch_list_sample_keys_22C13B: [],
        minimal_scan_active_profile_post_fetch_reject_reasons_22C13B: ["sec_uid_missing_from_profile_url"]
      }
    };
  }

  const templateInitial = discoverActiveProfilePostRequestTemplate22C13B(secUserId);
  let template = templateInitial;
  let fetchTierAttempted = activeProfilePostFetchTier22C13B(template);
  let fetchTierResult = "not_attempted";
  let fetchTierFailureReason: string | null = null;
  let statusNonZeroRetryCount = 0;
  let lastNonZeroCode: number | string | null = null;
  let lastNonZeroReason: string | null = null;
  const warmup = await warmupActiveProfilePostTemplate22C13B({ secUserId, initialTemplate: template });
  template = warmup.template;
  fetchTierAttempted = activeProfilePostFetchTier22C13B(template);
  const warmupAttempted = warmup.attempted;
  const warmupAttemptCount = warmup.attemptCount;
  const warmupAppliedTemplate = warmup.appliedTemplate;
  const warmupStopReason = warmup.stopReason;

  const templateBlockReason = activeProfilePostTemplateBlockReason22C13B(template);
  const endpointVariants = templateBlockReason ? [] : Array.from(new Set([
    template.endpointPath,
    ...fallbackEndpointVariants
  ].filter((value): value is string => typeof value === "string" && value.trim().length > 0)));
  const profileScope = canonicalProfileUrl22C12B(profileUrl);
  const byAweme = new Map<string, PassiveNetworkProbeStoredTarget22C12A>();
  const cursorValuesSample: Array<string | number> = [];
  const cursorFieldSamples: PassiveNetworkProbeCursorFields22C12BR2[] = [];
  const requestSamples: Record<string, unknown>[] = [];
  const endpointAttemptSamples: Record<string, unknown>[] = [];
  const parserRoutesTriedGlobal: string[] = [];
  const parserDirectRoutesTriedGlobal: string[] = [];
  const perPageRawCounts: number[] = [];
  const perPageAwemeIdCounts: number[] = [];
  const perPageAcceptedCounts: number[] = [];
  const perPageDuplicateDropCounts: number[] = [];
  const perPageMissingAwemeIdCounts: number[] = [];
  const perPageHasMoreStates: Array<boolean | null> = [];
  const perPageCursorPresent: boolean[] = [];
  const perPageStatusCodes: Array<number | string | null> = [];
  const perPageStopReasons: string[] = [];

  let requestCount = 0;
  let batchCount = 0;
  let pageCount = 0;
  let pageCapHitCount = 0;
  let pageCapHitWhileHasMoreCount = 0;
  let hasMoreState: boolean | null = null;
  let stopReason = "network_idle_no_has_more_signal";
  let cursor: string | number | null = 0;
  let previousCursorKey: string | null = null;
  let lastHttpStatus: number | null = null;
  let responseShape = "unknown";
  let error: string | null = null;
  let endpointPathUsed = endpointVariants[0] ?? template.endpointPath;
  let parserRoute = "none";
  let parserFallbackAttempted = false;
  let parserFallbackMatchCount = 0;
  let parserDirectMatchCount = 0;
  let parserFallbackCandidateCount = 0;
  let parserFallbackVisitedNodes = 0;
  let responseStatusCode: number | string | null = null;
  let responseStatusMsg: string | null = null;
  let responseTopLevelKeys: string[] = [];
  let responseDataKeys: string[] = [];
  let responseResultKeys: string[] = [];
  let parserPathCounts: Record<string, number> = {};
  let listSampleKeys: string[] = [];
  const rejectReasons = new Set<string>();
  if (templateBlockReason) rejectReasons.add(templateBlockReason);
  const startedAt = Date.now();

  if (templateBlockReason) {
    const durationMs = Math.max(Date.now() - startedAt, 0);
    return {
      attempted: true,
      meaningfulAttempted: false,
      requestCount: 0,
      batchCount: 0,
      targets: [],
      hasMoreState: null,
      stopReason: templateBlockReason,
      warmupAttempted,
      warmupAttemptCount,
      warmupAppliedTemplate,
      warmupStopReason,
      cursorValuesSample,
      cursorFieldSamples,
      endpointPath: template.endpointPath,
      endpointVariantsTried: [],
      responseShape: "not_attempted",
      lastHttpStatus: null,
      durationMs,
      error: templateBlockReason,
      diagnostics: {
        minimal_scan_active_profile_post_fetch_enabled_22C12B: "yes",
        minimal_scan_active_profile_post_fetch_attempted_22C12B: "no",
        minimal_scan_active_profile_post_fetch_request_count_22C12B: 0,
        minimal_scan_active_profile_post_fetch_batch_count_22C12B: 0,
        minimal_scan_active_profile_post_fetch_page_count_22C12B: 0,
        minimal_scan_active_profile_post_fetch_target_count_22C12B: 0,
        minimal_scan_active_profile_post_fetch_has_more_state_22C12B: null,
        minimal_scan_active_profile_post_fetch_stop_reason_22C12B: templateBlockReason,
        minimal_scan_active_profile_post_fetch_not_attempted_reason_22C12B: templateBlockReason,
        minimal_scan_active_profile_post_fetch_endpoint_variants_tried_22C12B: [],
        minimal_scan_active_profile_post_fetch_endpoint_variant_attempt_count_22C12B: 0,
        minimal_scan_active_profile_post_fetch_endpoint_variant_success_22C12B: null,
        minimal_scan_active_profile_post_fetch_endpoint_attempt_samples_22C12B: [],
        minimal_scan_active_profile_post_fetch_parser_route_22C12B: "none",
        minimal_scan_active_profile_post_fetch_parser_routes_tried_22C12B: [],
        minimal_scan_active_profile_post_fetch_parser_direct_routes_tried_22C12B: [],
        minimal_scan_active_profile_post_fetch_parser_direct_match_count_22C12B: 0,
        minimal_scan_active_profile_post_fetch_parser_fallback_attempted_22C12B: "no",
        minimal_scan_active_profile_post_fetch_parser_fallback_match_count_22C12B: 0,
        minimal_scan_active_profile_post_fetch_parser_fallback_candidate_count_22C12B: 0,
        minimal_scan_active_profile_post_fetch_parser_fallback_visited_nodes_22C12B: 0,
        minimal_scan_active_profile_post_fetch_effective_attempted_22C13B: "no",
        minimal_scan_active_profile_post_fetch_effective_attempt_reason_22C13B: templateBlockReason,
        active_profile_post_template_usable: "no",
        active_profile_post_template_usable_reason: templateBlockReason,
        active_profile_post_template_is_synthetic: template.syntheticFallback ? "yes" : "no",
        minimal_scan_active_profile_post_template_warmup_attempted_22C13B: warmupAttempted ? "yes" : "no",
        minimal_scan_active_profile_post_template_warmup_attempt_count_22C13B: warmupAttemptCount,
        minimal_scan_active_profile_post_template_warmup_applied_template_22C13B: warmupAppliedTemplate ? "yes" : "no",
        minimal_scan_active_profile_post_template_warmup_stop_reason_22C13B: warmupStopReason,
        active_profile_post_start_blocked_reason: templateBlockReason,
        ...activeProfilePostTemplateRecoveryDiagnostics22C13B(template, templateBlockReason, null, null, 0),
        minimal_scan_active_profile_post_fetch_response_shape_22C12B: "not_attempted",
        minimal_scan_active_profile_post_fetch_last_http_status_22C12B: null,
        minimal_scan_active_profile_post_fetch_duration_ms_22C12B: durationMs,
        minimal_scan_active_profile_post_fetch_error_22C12B: templateBlockReason,
        minimal_scan_active_profile_post_template_found_22C13B: "no",
        minimal_scan_active_profile_post_template_source_22C13B: "none",
        minimal_scan_active_profile_post_template_sources_tried_22C13B: template.sourcesTried,
        minimal_scan_active_profile_post_template_source_selected_22C13B: "none",
        minimal_scan_active_profile_post_template_cache_hit_22C13B: template.cacheHit ? "yes" : "no",
        minimal_scan_active_profile_post_template_endpoint_path_22C13B: "none",
        minimal_scan_active_profile_post_template_query_keys_22C13B: [],
        minimal_scan_active_profile_post_template_selected_query_keys_22C13B: [],
        minimal_scan_active_profile_post_template_required_query_keys_22C13B: template.requiredQueryKeys,
        minimal_scan_active_profile_post_template_required_query_keys_available_22C13B: "no",
        minimal_scan_active_profile_post_template_missing_required_query_keys_22C13B: template.requiredQueryKeys,
        minimal_scan_active_profile_post_template_secret_keys_present_22C13B: "no",
        minimal_scan_active_profile_post_template_secret_query_keys_22C13B: [],
        minimal_scan_active_profile_post_fetch_tier_attempted_22C13B: fetchTierAttempted,
        minimal_scan_active_profile_post_fetch_tier_result_22C13B: "failed",
        minimal_scan_active_profile_post_fetch_tier_failure_reason_22C13B: templateBlockReason,
        minimal_scan_active_profile_post_fetch_response_status_code_22C13B: null,
        minimal_scan_active_profile_post_fetch_response_status_msg_22C13B: null,
        minimal_scan_active_profile_post_fetch_reject_reasons_22C13B: Array.from(rejectReasons).slice(0, 16)
      }
    };
  }

  const pushParserRoute = (route: string): void => {
    if (!route || parserRoutesTriedGlobal.includes(route)) return;
    parserRoutesTriedGlobal.push(route);
  };
  const pushParserDirectRoute = (route: string): void => {
    if (!route || parserDirectRoutesTriedGlobal.includes(route)) return;
    parserDirectRoutesTriedGlobal.push(route);
  };

  for (let pageIndex = 0; ; pageIndex += 1) {
    pageCount = pageIndex + 1;
    const runtimeElapsedMs = Math.max(Date.now() - startedAt, 0);
    if (runtimeElapsedMs >= MINIMAL_SCAN_ACTIVE_PROFILE_POST_FETCH_MAX_RUNTIME_MS_22C12B) {
      stopReason = "pagination_runtime_timeout";
      error = "pagination_runtime_timeout";
      break;
    }
    if (byAweme.size >= MINIMAL_SCAN_ACTIVE_PROFILE_POST_FETCH_MAX_UNIQUE_TARGETS_22C12B) {
      stopReason = "max_unique_targets_reached";
      break;
    }
    if (pageIndex + 1 >= MINIMAL_SCAN_ACTIVE_PROFILE_POST_FETCH_MAX_PAGES_22C12B) {
      pageCapHitCount += 1;
      if (hasMoreState !== false) pageCapHitWhileHasMoreCount += 1;
    }

    let pageResolved = false;
    let shouldContinue = true;
    let pageFailureReason: string | null = null;
    let pageFailureError: string | null = null;
    let pageSawStatusNonZero = false;

    for (let endpointIndex = 0; endpointIndex < endpointVariants.length; endpointIndex += 1) {
      const endpointPath = endpointVariants[endpointIndex]!;
      const requestUrl = buildActiveProfilePostRequestUrl22C13B({
        template,
        endpointPath,
        secUserId,
        cursor
      });

      const requestStartedAt = Date.now();
      const controller = typeof AbortController === "function" ? new AbortController() : null;
      const timeout = window.setTimeout(() => controller?.abort(), MINIMAL_SCAN_ACTIVE_PROFILE_POST_FETCH_TIMEOUT_MS_22C12B);

      let status: number | null = null;
      let payload: unknown = null;
      let responseOk = false;
      try {
        const response = await fetch(requestUrl.toString(), {
          method: "GET",
          credentials: "include",
          signal: controller?.signal ?? null,
          headers: {
            Accept: "application/json, text/plain, */*"
          }
        });
        status = response.status;
        lastHttpStatus = status;
        payload = await response.json().catch(() => null);
        responseShape = payload && typeof payload === "object" ? "json_object" : Array.isArray(payload) ? "json_array" : payload == null ? "null" : typeof payload;
        responseOk = response.ok;
        requestCount += 1;
        requestSamples.push({
          page: pageIndex + 1,
          endpoint_path: endpointPath,
          endpoint_variant_index: endpointIndex,
          template_found: template.found ? "yes" : "no",
          template_query_key_count: template.queryKeys.length,
          status,
          duration_ms: Math.max(Date.now() - requestStartedAt, 0)
        });

        const responseInspection = inspectActiveProfilePostResponse22C13B(payload);
        responseStatusCode = responseInspection.statusCode;
        responseStatusMsg = responseInspection.statusMsg;
        responseTopLevelKeys = responseInspection.topLevelKeys;
        responseDataKeys = responseInspection.dataKeys;
        responseResultKeys = responseInspection.resultKeys;
        parserPathCounts = responseInspection.parserPathCounts;
        listSampleKeys = responseInspection.listSampleKeys;
        for (const reason of responseInspection.rejectReasons) rejectReasons.add(reason);
        if (responseInspection.statusCode != null && responseInspection.statusCode !== 0 && responseInspection.statusCode !== "0") {
          pageSawStatusNonZero = true;
          statusNonZeroRetryCount += 1;
          lastNonZeroCode = responseInspection.statusCode;
          lastNonZeroReason = responseInspection.statusMsg;
          template = discoverActiveProfilePostRequestTemplate22C13B(secUserId);
          fetchTierAttempted = activeProfilePostFetchTier22C13B(template);
          pageFailureReason = "active_profile_post_response_status_non_zero";
          pageFailureError = "active_profile_post_response_status_non_zero";
          endpointAttemptSamples.push({
            page: pageIndex + 1,
            endpoint_path: endpointPath,
            status,
            result: "active_profile_post_response_status_non_zero",
            response_status_code: responseInspection.statusCode,
            response_status_msg: responseInspection.statusMsg
          });
          continue;
        }
      } catch (caught) {
        requestCount += 1;
        const caughtError = caught instanceof Error ? caught : new Error(String(caught));
        const caughtReason = caughtError.name === "AbortError" ? "request_timeout" : "request_exception";
        requestSamples.push({
          page: pageIndex + 1,
          endpoint_path: endpointPath,
          endpoint_variant_index: endpointIndex,
          status,
          duration_ms: Math.max(Date.now() - requestStartedAt, 0),
          error: caughtReason
        });
        endpointAttemptSamples.push({
          page: pageIndex + 1,
          endpoint_path: endpointPath,
          status,
          result: caughtReason
        });
        pageFailureReason = caughtReason;
        pageFailureError = caughtReason;
        responseShape = "fetch_exception";
        rejectReasons.add(caughtReason);
        continue;
      } finally {
        clearTimeout(timeout);
      }

      if (!responseOk) {
        pageFailureReason = "response_not_ok";
        pageFailureError = status == null ? "response_not_ok" : `http_status_${status}`;
        endpointAttemptSamples.push({
          page: pageIndex + 1,
          endpoint_path: endpointPath,
          status,
          result: "response_not_ok"
        });
        rejectReasons.add("response_not_ok");
        continue;
      }

      const extraction = extractActiveProfilePostBatchWithFallback22C12B({
        payload,
        endpointPath,
        method: "GET",
        status
      });

      for (const route of extraction.parserRoutesTried) pushParserRoute(route);
      for (const route of extraction.directRoutesTried) pushParserDirectRoute(route);
      parserDirectMatchCount += extraction.directMatchCount;
      parserFallbackAttempted = parserFallbackAttempted || extraction.fallbackAttempted;
      parserFallbackMatchCount += extraction.fallbackMatchCount;
      parserFallbackCandidateCount += extraction.fallbackCandidateCount;
      parserFallbackVisitedNodes += extraction.fallbackVisitedNodes;

      if (!extraction.batch) {
        pageFailureReason = "extractor_no_targets";
        pageFailureError = "extractor_no_targets";
        endpointAttemptSamples.push({
          page: pageIndex + 1,
          endpoint_path: endpointPath,
          status,
          result: "extractor_no_targets"
        });
        rejectReasons.add("extractor_no_targets");
        continue;
      }

      const batch = extraction.batch;
      parserRoute = extraction.parserRoute;
      endpointPathUsed = endpointPath;
      const rawPageItemCount = Math.max(batch.awemeCount, 0);
      const rawPageAwemeIdCount = batch.targets.filter((target) => typeof target.aweme_id === "string" && /^\d{8,}$/.test(target.aweme_id)).length;
      const uniqueBeforePage = byAweme.size;
      activeProfilePostLastSuccessfulTemplateCache22C13B.set(secUserId, template);
      fetchTierResult = "usable";
      fetchTierFailureReason = null;
      pageResolved = true;
      pageFailureReason = null;
      pageFailureError = null;
      endpointAttemptSamples.push({
        page: pageIndex + 1,
        endpoint_path: endpointPath,
        status,
        result: "batch_ok",
        parser_route: extraction.parserRoute
      });

      batchCount += 1;
      hasMoreState = batch.hasMore ?? hasMoreState;
      if (batch.cursor != null && cursorValuesSample.length < 20) cursorValuesSample.push(batch.cursor);
      if (batch.cursorFields && cursorFieldSamples.length < 12) cursorFieldSamples.push(batch.cursorFields);

      const capturedAt = new Date().toISOString();
      for (const target of batch.targets) {
        if (byAweme.has(target.aweme_id)) continue;
        byAweme.set(target.aweme_id, buildPassiveNetworkStoredTarget22C12A({
          target,
          profileUrl: profileScope,
          urlPath: endpointPath,
          capturedAt
        }));
        if (byAweme.size >= MINIMAL_SCAN_ACTIVE_PROFILE_POST_FETCH_MAX_UNIQUE_TARGETS_22C12B) break;
      }

      const acceptedPageCount = Math.max(byAweme.size - uniqueBeforePage, 0);
      const missingAwemeIdCount = Math.max(rawPageItemCount - rawPageAwemeIdCount, 0);
      const duplicateDropCount = Math.max(rawPageAwemeIdCount - acceptedPageCount, 0);
      const nextCursor = batch.cursorFields?.max_cursor
        ?? batch.cursorFields?.next_cursor
        ?? batch.cursor
        ?? null;
      const nextCursorKey = nextCursor == null ? null : String(nextCursor);
      const pageStopReason = batch.hasMore === false ? "has_more_false" : nextCursorKey == null ? "cursor_absent" : previousCursorKey != null && nextCursorKey === previousCursorKey ? "cursor_stalled" : "page_ok_has_more";
      perPageRawCounts.push(rawPageItemCount);
      perPageAwemeIdCounts.push(rawPageAwemeIdCount);
      perPageAcceptedCounts.push(acceptedPageCount);
      perPageDuplicateDropCounts.push(duplicateDropCount);
      perPageMissingAwemeIdCounts.push(missingAwemeIdCount);
      perPageHasMoreStates.push(batch.hasMore ?? null);
      perPageCursorPresent.push(nextCursor != null);
      perPageStatusCodes.push(responseStatusCode ?? status ?? null);
      perPageStopReasons.push(pageStopReason);

      if (batch.hasMore === false) {
        stopReason = "has_more_false";
        shouldContinue = false;
        break;
      }
      if (nextCursorKey == null) {
        stopReason = "cursor_absent";
        shouldContinue = false;
        break;
      }
      if (previousCursorKey != null && nextCursorKey === previousCursorKey) {
        stopReason = "cursor_stalled";
        shouldContinue = false;
        break;
      }

      previousCursorKey = nextCursorKey;
      cursor = nextCursor;
      break;
    }

    if (!pageResolved) {
      stopReason = pageSawStatusNonZero
        ? "active_profile_post_response_status_non_zero"
        : (pageFailureReason ?? "endpoint_variants_exhausted_no_batch");
      error = pageSawStatusNonZero
        ? "active_profile_post_response_status_non_zero"
        : (pageFailureError ?? stopReason);
      break;
    }
    if (!shouldContinue) break;
  }

  if (byAweme.size === 0) rejectReasons.add("no_targets_collected");
  if (fetchTierResult !== "usable") {
    fetchTierResult = "failed";
    fetchTierFailureReason = error ?? stopReason;
  }

  const endpointVariantsTried = Array.from(new Set(requestSamples
    .map((sample) => typeof sample.endpoint_path === "string" ? sample.endpoint_path : null)
    .filter((value): value is string => Boolean(value))));
  const activeAwemeIds = Array.from(byAweme.keys());
  const durationMs = Math.max(Date.now() - startedAt, 0);
  const meaningfulAttempted = requestCount > 0 || batchCount > 0 || byAweme.size > 0;
  const effectiveAttemptReason = meaningfulAttempted
    ? "network_request_dispatched"
    : stopReason || error || "network_request_not_dispatched";
  return {
    attempted: true,
    meaningfulAttempted,
    requestCount,
    batchCount,
    targets: Array.from(byAweme.values()),
    hasMoreState,
    stopReason,
    warmupAttempted,
    warmupAttemptCount,
    warmupAppliedTemplate,
    warmupStopReason,
    cursorValuesSample,
    cursorFieldSamples,
    endpointPath: endpointPathUsed,
    endpointVariantsTried,
    responseShape,
    lastHttpStatus,
    durationMs,
    error,
    diagnostics: {
      minimal_scan_active_profile_post_fetch_enabled_22C12B: "yes",
      minimal_scan_active_profile_post_fetch_attempted_22C12B: "yes",
      minimal_scan_active_profile_post_fetch_request_count_22C12B: requestCount,
      minimal_scan_active_profile_post_fetch_batch_count_22C12B: batchCount,
      minimal_scan_active_profile_post_fetch_page_count_22C12B: pageCount,
      minimal_scan_active_profile_post_fetch_page_cap_22C12B: MINIMAL_SCAN_ACTIVE_PROFILE_POST_FETCH_MAX_PAGES_22C12B,
      minimal_scan_active_profile_post_fetch_page_cap_hit_count_22C12B: pageCapHitCount,
      minimal_scan_active_profile_post_fetch_page_cap_hit_while_has_more_count_22C12B: pageCapHitWhileHasMoreCount,
      minimal_scan_active_profile_post_fetch_runtime_timeout_ms_22C12B: MINIMAL_SCAN_ACTIVE_PROFILE_POST_FETCH_MAX_RUNTIME_MS_22C12B,
      minimal_scan_active_profile_post_fetch_runtime_timeout_hit_22C12B: stopReason === "pagination_runtime_timeout" ? "yes" : "no",
      minimal_scan_active_profile_post_fetch_continuation_policy_22C12B: "continue_while_has_more_true_until_terminal_or_runtime_timeout",
      minimal_scan_active_profile_post_fetch_target_count_22C12B: byAweme.size,
      minimal_scan_active_profile_post_fetch_raw_items_total_22C14P: perPageRawCounts.reduce((sum, count) => sum + count, 0),
      minimal_scan_active_profile_post_fetch_raw_aweme_ids_total_22C14P: perPageAwemeIdCounts.reduce((sum, count) => sum + count, 0),
      minimal_scan_active_profile_post_fetch_accepted_targets_total_22C14P: perPageAcceptedCounts.reduce((sum, count) => sum + count, 0),
      minimal_scan_active_profile_post_fetch_duplicate_drop_count_22C14P: perPageDuplicateDropCounts.reduce((sum, count) => sum + count, 0),
      minimal_scan_active_profile_post_fetch_invalid_drop_count_22C14P: 0,
      minimal_scan_active_profile_post_fetch_other_profile_drop_count_22C14P: 0,
      minimal_scan_active_profile_post_fetch_favorite_endpoint_drop_count_22C14P: 0,
      minimal_scan_active_profile_post_fetch_missing_aweme_id_count_22C14P: perPageMissingAwemeIdCounts.reduce((sum, count) => sum + count, 0),
      minimal_scan_active_profile_post_fetch_per_page_raw_counts_22C14P: perPageRawCounts,
      minimal_scan_active_profile_post_fetch_per_page_aweme_id_counts_22C14P: perPageAwemeIdCounts,
      minimal_scan_active_profile_post_fetch_per_page_accepted_counts_22C14P: perPageAcceptedCounts,
      minimal_scan_active_profile_post_fetch_per_page_duplicate_drop_counts_22C14P: perPageDuplicateDropCounts,
      minimal_scan_active_profile_post_fetch_per_page_missing_aweme_id_counts_22C14P: perPageMissingAwemeIdCounts,
      minimal_scan_active_profile_post_fetch_per_page_has_more_22C14P: perPageHasMoreStates,
      minimal_scan_active_profile_post_fetch_per_page_cursor_present_22C14P: perPageCursorPresent,
      minimal_scan_active_profile_post_fetch_per_page_status_codes_22C14P: perPageStatusCodes,
      minimal_scan_active_profile_post_fetch_per_page_stop_reasons_22C14P: perPageStopReasons,
      minimal_scan_active_profile_post_fetch_has_more_state_22C12B: hasMoreState,
      minimal_scan_active_profile_post_fetch_stop_reason_22C12B: stopReason,
      minimal_scan_active_profile_post_fetch_cursor_values_sample_22C12B: cursorValuesSample,
      minimal_scan_active_profile_post_fetch_cursor_fields_sample_22C12B: cursorFieldSamples,
      minimal_scan_active_profile_post_fetch_request_samples_22C12B: requestSamples.slice(0, 12),
      minimal_scan_active_profile_post_fetch_first_10_aweme_ids_22C12B: activeAwemeIds.slice(0, 10),
      minimal_scan_active_profile_post_fetch_last_10_aweme_ids_22C12B: activeAwemeIds.slice(-10),
      minimal_scan_active_profile_post_fetch_endpoint_used_22C12B: endpointPathUsed,
      minimal_scan_active_profile_post_fetch_endpoint_variants_tried_22C12B: endpointVariantsTried,
      minimal_scan_active_profile_post_fetch_endpoint_variant_attempt_count_22C12B: requestSamples.length,
      minimal_scan_active_profile_post_fetch_endpoint_variant_success_22C12B: endpointPathUsed,
      minimal_scan_active_profile_post_fetch_endpoint_attempt_samples_22C12B: endpointAttemptSamples.slice(0, 16),
      minimal_scan_active_profile_post_fetch_parser_route_22C12B: parserRoute,
      minimal_scan_active_profile_post_fetch_parser_routes_tried_22C12B: parserRoutesTriedGlobal.slice(0, 64),
      minimal_scan_active_profile_post_fetch_parser_direct_routes_tried_22C12B: parserDirectRoutesTriedGlobal.slice(0, 48),
      minimal_scan_active_profile_post_fetch_parser_direct_match_count_22C12B: parserDirectMatchCount,
      minimal_scan_active_profile_post_fetch_parser_fallback_attempted_22C12B: parserFallbackAttempted ? "yes" : "no",
      minimal_scan_active_profile_post_fetch_parser_fallback_match_count_22C12B: parserFallbackMatchCount,
      minimal_scan_active_profile_post_fetch_parser_fallback_candidate_count_22C12B: parserFallbackCandidateCount,
      minimal_scan_active_profile_post_fetch_parser_fallback_visited_nodes_22C12B: parserFallbackVisitedNodes,
      minimal_scan_active_profile_post_fetch_effective_attempted_22C13B: meaningfulAttempted ? "yes" : "no",
      minimal_scan_active_profile_post_fetch_effective_attempt_reason_22C13B: effectiveAttemptReason,
      minimal_scan_active_profile_post_template_warmup_attempted_22C13B: warmupAttempted ? "yes" : "no",
      minimal_scan_active_profile_post_template_warmup_attempt_count_22C13B: warmupAttemptCount,
      minimal_scan_active_profile_post_template_warmup_applied_template_22C13B: warmupAppliedTemplate ? "yes" : "no",
      minimal_scan_active_profile_post_template_warmup_stop_reason_22C13B: warmupStopReason,
      active_profile_post_template_usable: isUsableActiveProfilePostTemplate22C13B(template) ? "yes" : "no",
      active_profile_post_template_usable_reason: isUsableActiveProfilePostTemplate22C13B(template) ? "usable" : activeProfilePostTemplateBlockReason22C13B(template),
      active_profile_post_template_is_synthetic: template.syntheticFallback ? "yes" : "no",
      active_profile_post_template_recovery_attempted: template.recoveryAttempted ? "yes" : "no",
      active_profile_post_template_recovery_steps: template.recoverySteps,
      active_profile_post_template_recovery_result: template.recoveryResult,
      active_profile_post_template_recovery_error: template.recoveryError,
      active_profile_post_template_query_key_sources: template.queryKeySources,
      active_profile_post_template_added_default_count: template.addedDefaultCount ? "yes" : "no",
      active_profile_post_template_added_default_max_cursor: template.addedDefaultMaxCursor ? "yes" : "no",
      active_profile_post_template_derived_sec_user_id: template.derivedSecUserId ? "yes" : "no",
      active_profile_post_canonical_profile_url: profileScope,
      active_profile_post_original_profile_url: profileUrl,
      active_profile_post_warmup_scroll_attempted: warmup.scrollAttempted ? "yes" : "no",
      active_profile_post_warmup_performance_resource_count: warmup.performanceResourceCount,
      active_profile_post_warmup_network_probe_ready: warmup.networkProbeReady ? "yes" : "no",
      active_profile_post_warmup_post_endpoint_seen: warmup.postEndpointSeen ? "yes" : "no",
      active_profile_post_start_blocked_reason: activeProfilePostTemplateBlockReason22C13B(template),
      ...activeProfilePostTemplateRecoveryDiagnostics22C13B(template, activeProfilePostTemplateBlockReason22C13B(template), lastHttpStatus, responseStatusCode, batchCount),
      minimal_scan_active_profile_post_fetch_response_shape_22C12B: responseShape,
      minimal_scan_active_profile_post_fetch_last_http_status_22C12B: lastHttpStatus,
      minimal_scan_active_profile_post_fetch_duration_ms_22C12B: durationMs,
      minimal_scan_active_profile_post_fetch_error_22C12B: error,
      minimal_scan_active_profile_post_fetch_not_attempted_reason_22C12B: null,
      minimal_scan_active_profile_post_template_found_22C13B: isUsableActiveProfilePostTemplate22C13B(template) ? "yes" : "no",
      minimal_scan_active_profile_post_template_source_22C13B: isUsableActiveProfilePostTemplate22C13B(template) ? template.source : "none",
      minimal_scan_active_profile_post_template_sources_tried_22C13B: template.sourcesTried,
      minimal_scan_active_profile_post_template_source_selected_22C13B: isUsableActiveProfilePostTemplate22C13B(template) ? template.source : "none",
      minimal_scan_active_profile_post_template_cache_hit_22C13B: template.cacheHit ? "yes" : "no",
      minimal_scan_active_profile_post_template_endpoint_path_22C13B: isUsableActiveProfilePostTemplate22C13B(template) ? template.endpointPath : "none",
      minimal_scan_active_profile_post_template_query_keys_22C13B: isUsableActiveProfilePostTemplate22C13B(template) ? template.queryKeys : [],
      minimal_scan_active_profile_post_template_selected_query_keys_22C13B: isUsableActiveProfilePostTemplate22C13B(template) ? template.selectedQueryKeys : [],
      minimal_scan_active_profile_post_template_required_query_keys_22C13B: template.requiredQueryKeys,
      minimal_scan_active_profile_post_template_required_query_keys_available_22C13B: isUsableActiveProfilePostTemplate22C13B(template) ? "yes" : "no",
      minimal_scan_active_profile_post_template_missing_required_query_keys_22C13B: isUsableActiveProfilePostTemplate22C13B(template) ? [] : template.requiredQueryKeys,
      minimal_scan_active_profile_post_template_secret_keys_present_22C13B: isUsableActiveProfilePostTemplate22C13B(template) && template.secretQueryKeys.length > 0 ? "yes" : "no",
      minimal_scan_active_profile_post_template_secret_query_keys_22C13B: isUsableActiveProfilePostTemplate22C13B(template) ? template.secretQueryKeys : [],
      minimal_scan_active_profile_post_fetch_tier_attempted_22C13B: fetchTierAttempted,
      minimal_scan_active_profile_post_fetch_tier_result_22C13B: fetchTierResult,
      minimal_scan_active_profile_post_fetch_tier_failure_reason_22C13B: fetchTierFailureReason,
      minimal_scan_active_profile_post_fetch_response_status_code_22C13B: responseStatusCode,
      minimal_scan_active_profile_post_fetch_response_status_msg_22C13B: responseStatusMsg,
      minimal_scan_active_profile_post_fetch_status_non_zero_retryable_22C13B: lastNonZeroCode != null ? "yes" : "no",
      minimal_scan_active_profile_post_fetch_status_non_zero_retry_count_22C13B: statusNonZeroRetryCount,
      minimal_scan_active_profile_post_fetch_last_non_zero_code_22C13B: lastNonZeroCode,
      minimal_scan_active_profile_post_fetch_last_non_zero_reason_22C13B: lastNonZeroReason,
      minimal_scan_active_profile_post_fetch_response_top_level_keys_22C13B: responseTopLevelKeys,
      minimal_scan_active_profile_post_fetch_response_data_keys_22C13B: responseDataKeys,
      minimal_scan_active_profile_post_fetch_response_result_keys_22C13B: responseResultKeys,
      minimal_scan_active_profile_post_fetch_parser_path_counts_22C13B: parserPathCounts,
      minimal_scan_active_profile_post_fetch_list_sample_keys_22C13B: listSampleKeys,
      minimal_scan_active_profile_post_fetch_reject_reasons_22C13B: Array.from(rejectReasons).slice(0, 16)
    }
  };
}

async function runMinimalActiveTabProfileScan22C11B(message: ExtensionMessage, receivedAt: string): Promise<ExtensionMessageResponse> {
  const scanRunId = (message.scanRunId ?? message.scan_run_id ?? message.run_id ?? "").trim();
  const profileUrl = (message.profileUrl ?? message.expected_profile_url ?? window.location.href).trim();
  if (!scanRunId) return { ok: false, reason: "minimal_scan_missing_run_id", verified_targets: [], verified_target_details: [], diagnostics: { canonical_content_handler_received: "yes", canonical_content_handler_received_at: receivedAt } };
  if (!/douyin\.com\/user\//i.test(profileUrl) && !/douyin\.com\/user\//i.test(window.location.href)) {
    return { ok: false, reason: "minimal_scan_not_profile_page", verified_targets: [], verified_target_details: [], diagnostics: { current_url: window.location.href, profile_url: profileUrl } };
  }

  initializePassiveNetworkProbe22C12AR2();
  if (isPassiveNetworkProbeProfilePage22C12A() && passiveNetworkProbeSummary22C12A.network_probe_page_script_injection_attempted !== "yes") {
    injectPageNetworkHook();
  }

  const probeWait = await waitForPassiveNetworkProbeForMinimalScan22C12B(MINIMAL_SCAN_NETWORK_PROBE_READY_WAIT_MS_22C12B);
  const tab = activeWorksTabInfo22C11B();
  const collected = await collectActiveWorksGridTargetsUntilStable22C11B(profileUrl);

  const settleStartMs = Date.now();
  const settleDeadline = settleStartMs + MINIMAL_SCAN_NETWORK_PROBE_POST_SCROLL_SETTLE_MS_22C12B;
  let settleObservedNewProfilePostBatch = false;
  while (Date.now() <= settleDeadline) {
    const latestSnapshot = getPassiveNetworkProbeSnapshot22C12A();
    if (latestSnapshot.profilePostBatchCount > probeWait.finalSnapshot.profilePostBatchCount
      || latestSnapshot.profilePostTargets.length > probeWait.finalSnapshot.profilePostTargets.length) {
      settleObservedNewProfilePostBatch = true;
      break;
    }
    await new Promise((resolve) => window.setTimeout(resolve, MINIMAL_SCAN_NETWORK_PROBE_POLL_MS_22C12B));
  }

  const passiveSnapshot = getPassiveNetworkProbeSnapshot22C12A();
  const canonicalRequestedProfileUrl = canonicalProfileUrl22C12B(profileUrl);
  const passiveSameProfileTargets = passiveSnapshot.profilePostTargets.filter((target) => canonicalProfileUrl22C12B(target.profile_url) === canonicalRequestedProfileUrl);
  const passiveCrossProfileExcludedCount = Math.max(passiveSnapshot.profilePostTargets.length - passiveSameProfileTargets.length, 0);

  const activeProfilePostFetchPrimary = await runActiveSameOriginProfilePostFetch22C12B(canonicalRequestedProfileUrl);
  const activeProfilePostFallbackEligible = activeProfilePostFetchPrimary.hasMoreState === true
    && activeProfilePostFetchPrimary.stopReason !== "has_more_false"
    && activeProfilePostFetchPrimary.stopReason !== "pagination_runtime_timeout"
    && activeProfilePostFetchPrimary.stopReason !== "sec_uid_missing_from_profile_url";
  const activeProfilePostFetchFallback = activeProfilePostFallbackEligible
    ? await runActiveSameOriginProfilePostFetch22C12B(canonicalRequestedProfileUrl)
    : null;

  const activeProfilePostFetchRuns: ActiveProfilePostFetchResult22C12B[] = [activeProfilePostFetchPrimary];
  if (activeProfilePostFetchFallback) activeProfilePostFetchRuns.push(activeProfilePostFetchFallback);

  const activeProfilePostMergedTargetsBeforeExpectedRetry = activeProfilePostFetchRuns.reduce<PassiveNetworkProbeStoredTarget22C12A[]>(
    (merged, run) => mergeNetworkStoredTargets22C12B(merged, run.targets),
    []
  );
  const activeSameProfileTargetsBeforeExpectedRetry = activeProfilePostMergedTargetsBeforeExpectedRetry
    .filter((target) => canonicalProfileUrl22C12B(target.profile_url) === canonicalRequestedProfileUrl);
  const networkStoredTargetsBeforeExpectedRetry = mergeNetworkStoredTargets22C12B(passiveSameProfileTargets, activeSameProfileTargetsBeforeExpectedRetry);

  const expectedProfileVideoCount = typeof tab.expectedCount === "number" && Number.isFinite(tab.expectedCount) && tab.expectedCount >= 0
    ? Math.max(0, Math.round(tab.expectedCount))
    : null;
  const activeProfilePostUnavailableReasons22C13B = new Set([
    "required_query_keys_unavailable",
    "active_profile_post_response_status_non_zero",
    "sec_uid_missing_from_profile_url",
    "profile_post_endpoint_seen_but_source_url_missing",
    "usable_template_unavailable",
    "template_not_found",
    "template_not_found_after_warmup",
    "active_profile_post_template_unavailable_after_recovery",
    "template_unavailable_after_all_recovery"
  ]);
  const activeProfilePostUnavailableOrNonZero = activeProfilePostFetchRuns.some((run) =>
    activeProfilePostUnavailableReasons22C13B.has(run.stopReason)
      || (typeof run.error === "string" && activeProfilePostUnavailableReasons22C13B.has(run.error))
  );
  const activeProfilePostExpectedCountRetryEligible = expectedProfileVideoCount != null
    && expectedProfileVideoCount > networkStoredTargetsBeforeExpectedRetry.length
    && activeProfilePostUnavailableOrNonZero;

  let activeProfilePostExpectedCountRetryAttempted = false;
  let activeProfilePostExpectedCountRetryReason = activeProfilePostExpectedCountRetryEligible
    ? "expected_count_known_active_source_unavailable_or_non_zero"
    : "not_eligible";
  let activeProfilePostExpectedCountRetryFetch: ActiveProfilePostFetchResult22C12B | null = null;
  let activeProfilePostExpectedCountRetryWarmupWheelEvents = 0;
  let activeProfilePostExpectedCountRetryWarmupWheelDeltas: number[] = [];

  if (activeProfilePostExpectedCountRetryEligible) {
    activeProfilePostExpectedCountRetryAttempted = true;
    try {
      const retryWarmupFlick = await dispatchSyntheticWheelFlick22C11B(0);
      activeProfilePostExpectedCountRetryWarmupWheelEvents = retryWarmupFlick.events;
      activeProfilePostExpectedCountRetryWarmupWheelDeltas = retryWarmupFlick.deltas;
    } catch {
      activeProfilePostExpectedCountRetryReason = "expected_count_retry_warmup_scroll_failed";
    }
    await new Promise((resolve) => window.setTimeout(resolve, MINIMAL_SCAN_ACTIVE_PROFILE_POST_FETCH_EXPECTED_COUNT_RETRY_WAIT_MS_22C13B));
    activeProfilePostExpectedCountRetryFetch = await runActiveSameOriginProfilePostFetch22C12B(canonicalRequestedProfileUrl);
    activeProfilePostFetchRuns.push(activeProfilePostExpectedCountRetryFetch);
  }

  const activeProfilePostFetchMergedTargets = activeProfilePostFetchRuns.reduce<PassiveNetworkProbeStoredTarget22C12A[]>(
    (merged, run) => mergeNetworkStoredTargets22C12B(merged, run.targets),
    []
  );
  const activeProfilePostFetchRequestCount = activeProfilePostFetchRuns.reduce((sum, run) => sum + run.requestCount, 0);
  const activeProfilePostFetchBatchCount = activeProfilePostFetchRuns.reduce((sum, run) => sum + run.batchCount, 0);
  const activeProfilePostFetchDurationMs = activeProfilePostFetchRuns.reduce((sum, run) => sum + Math.max(run.durationMs, 0), 0);
  const mergeRunNumberArrays22C14P = (key: string): number[] => activeProfilePostFetchRuns.flatMap((run) => {
    const value = run.diagnostics[key];
    return Array.isArray(value) ? value.filter((entry): entry is number => typeof entry === "number" && Number.isFinite(entry)).map((entry) => Math.max(0, Math.round(entry))) : [];
  });
  const mergeRunBooleanNullArrays22C14P = (key: string): Array<boolean | null> => activeProfilePostFetchRuns.flatMap((run) => {
    const value = run.diagnostics[key];
    return Array.isArray(value) ? value.map((entry) => typeof entry === "boolean" ? entry : null) : [];
  });
  const mergeRunStatusArrays22C14P = (key: string): Array<number | string | null> => activeProfilePostFetchRuns.flatMap((run) => {
    const value = run.diagnostics[key];
    return Array.isArray(value) ? value.map((entry) => typeof entry === "number" || typeof entry === "string" ? entry : null) : [];
  });
  const mergeRunStringArrays22C14P = (key: string): string[] => activeProfilePostFetchRuns.flatMap((run) => {
    const value = run.diagnostics[key];
    return Array.isArray(value) ? value.filter((entry): entry is string => typeof entry === "string" && entry.trim().length > 0) : [];
  });
  const activeProfilePostPerPageRawCounts = mergeRunNumberArrays22C14P("minimal_scan_active_profile_post_fetch_per_page_raw_counts_22C14P");
  const activeProfilePostPerPageAwemeIdCounts = mergeRunNumberArrays22C14P("minimal_scan_active_profile_post_fetch_per_page_aweme_id_counts_22C14P");
  const activeProfilePostPerPageAcceptedCounts = mergeRunNumberArrays22C14P("minimal_scan_active_profile_post_fetch_per_page_accepted_counts_22C14P");
  const activeProfilePostPerPageDuplicateDropCounts = mergeRunNumberArrays22C14P("minimal_scan_active_profile_post_fetch_per_page_duplicate_drop_counts_22C14P");
  const activeProfilePostPerPageMissingAwemeIdCounts = mergeRunNumberArrays22C14P("minimal_scan_active_profile_post_fetch_per_page_missing_aweme_id_counts_22C14P");
  const activeProfilePostPerPageHasMore = mergeRunBooleanNullArrays22C14P("minimal_scan_active_profile_post_fetch_per_page_has_more_22C14P");
  const activeProfilePostPerPageCursorPresent = mergeRunBooleanNullArrays22C14P("minimal_scan_active_profile_post_fetch_per_page_cursor_present_22C14P").map((value) => value === true);
  const activeProfilePostPerPageStatusCodes = mergeRunStatusArrays22C14P("minimal_scan_active_profile_post_fetch_per_page_status_codes_22C14P");
  const activeProfilePostPerPageStopReasons = mergeRunStringArrays22C14P("minimal_scan_active_profile_post_fetch_per_page_stop_reasons_22C14P");
  const activeProfilePostFetchHasMoreState = activeProfilePostFetchRuns.some((run) => run.hasMoreState === false)
    ? false
    : activeProfilePostFetchRuns[activeProfilePostFetchRuns.length - 1]?.hasMoreState ?? activeProfilePostFetchPrimary.hasMoreState;
  const activeProfilePostFetchStopReason = activeProfilePostFetchRuns[activeProfilePostFetchRuns.length - 1]?.stopReason ?? activeProfilePostFetchPrimary.stopReason;
  const activeProfilePostFetchError = activeProfilePostFetchRuns[activeProfilePostFetchRuns.length - 1]?.error ?? activeProfilePostFetchPrimary.error;
  const activeProfilePostFetchTimeoutHit = activeProfilePostFetchRuns.some((run) => run.stopReason === "pagination_runtime_timeout");
  const activeProfilePostFetchMeaningfulAttempt = activeProfilePostFetchRuns.some((run) => run.meaningfulAttempted)
    || activeProfilePostFetchRequestCount > 0
    || activeProfilePostFetchBatchCount > 0;
  const activeProfilePostTemplateWarmupAttempted = activeProfilePostFetchRuns.some((run) => run.warmupAttempted);
  const activeProfilePostTemplateWarmupAttemptCount = activeProfilePostFetchRuns.reduce((sum, run) => sum + run.warmupAttemptCount, 0);
  const activeProfilePostTemplateWarmupAppliedTemplate = activeProfilePostFetchRuns.some((run) => run.warmupAppliedTemplate);
  const activeProfilePostTemplateWarmupStopReason = activeProfilePostFetchRuns[activeProfilePostFetchRuns.length - 1]?.warmupStopReason ?? activeProfilePostFetchPrimary.warmupStopReason;
  const activeSameProfileTargets = activeProfilePostFetchMergedTargets.filter((target) => canonicalProfileUrl22C12B(target.profile_url) === canonicalRequestedProfileUrl);
  const activeCrossProfileExcludedCount = Math.max(activeProfilePostFetchMergedTargets.length - activeSameProfileTargets.length, 0);
  const activeProfilePostFetchDiagnosticsSource = activeProfilePostExpectedCountRetryFetch?.diagnostics
    ?? activeProfilePostFetchFallback?.diagnostics
    ?? activeProfilePostFetchPrimary.diagnostics;
  const activeProfilePostFetchRejectReasons = Array.from(new Set(activeProfilePostFetchRuns.flatMap((run) => {
    const value = run.diagnostics.minimal_scan_active_profile_post_fetch_reject_reasons_22C13B;
    return Array.isArray(value)
      ? value.filter((entry): entry is string => typeof entry === "string" && entry.trim().length > 0)
      : [];
  })));

  const combinedNetworkStoredTargets = mergeNetworkStoredTargets22C12B(passiveSameProfileTargets, activeSameProfileTargets);
  const activeOnlyAwemeIds = activeSameProfileTargets
    .filter((target) => !passiveSameProfileTargets.some((passiveTarget) => passiveTarget.aweme_id === target.aweme_id))
    .map((target) => target.aweme_id);
  const networkTargets = buildNetworkFirstProfileTargets22C12B(activeSameProfileTargets)
    .map((target, index) => ({
      ...target,
      index: index + 1,
      discovery_source: "active_profile_post_22C12B"
    }));

  const domSameProfileTargets: MinimalActiveWorksTarget22C11B[] = [];
  const domScopedByAweme = new Map<string, MinimalActiveWorksTarget22C11B>();
  const domSupplementAwemeIds: string[] = [];
  const domSupplementRejected: Array<{ aweme_id: string | null; reason: string; profile_url: string | null }> = [];
  const domSupplementRejectedReasonCounts: Record<string, number> = {};
  const recordDomSupplementReject = (awemeId: string | null, reason: string, targetProfileUrl: string | null) => {
    domSupplementRejectedReasonCounts[reason] = (domSupplementRejectedReasonCounts[reason] ?? 0) + 1;
    if (domSupplementRejected.length < 20) domSupplementRejected.push({ aweme_id: awemeId, reason, profile_url: targetProfileUrl });
  };
  for (const target of collected.targets) {
    const awemeId = typeof target.aweme_id === "string" ? target.aweme_id.trim() : "";
    const normalizedAwemeId = awemeId || null;
    if (!normalizedAwemeId || !/^\d{8,}$/.test(normalizedAwemeId)) {
      recordDomSupplementReject(normalizedAwemeId, "invalid_aweme_id", typeof target.profile_url === "string" ? target.profile_url : null);
      continue;
    }
    const targetProfileUrl = canonicalProfileUrl22C12B(typeof target.profile_url === "string" && target.profile_url.trim() ? target.profile_url : profileUrl);
    if (targetProfileUrl !== canonicalRequestedProfileUrl) {
      recordDomSupplementReject(normalizedAwemeId, "cross_profile_scope_mismatch", targetProfileUrl);
      continue;
    }
    domSameProfileTargets.push(target);
    if (domScopedByAweme.has(normalizedAwemeId)) {
      recordDomSupplementReject(normalizedAwemeId, "duplicate_existing_aweme_id", targetProfileUrl);
      continue;
    }
    domSupplementAwemeIds.push(normalizedAwemeId);
    domScopedByAweme.set(normalizedAwemeId, {
      ...target,
      aweme_id: normalizedAwemeId,
      index: domScopedByAweme.size + 1,
      discovery_source: target.discovery_source || "dom_scoped_fallback_22C11B"
    });
  }

  const currentVideoAwemeId = extractModalTestAwemeId22C11B(window.location.href);
  const currentVideoSupplemented = false;
  const activeQueueAuthorityUsable = activeProfilePostFetchMeaningfulAttempt
    && activeSameProfileTargets.length > 0
    && !activeProfilePostUnavailableOrNonZero;
  const queueSourceMode = activeQueueAuthorityUsable
    ? "active_profile_post_only"
    : "dom_scoped_fallback_degraded";
  const domScopedTargets = Array.from(domScopedByAweme.values()).map((target, index) => ({
    ...target,
    index: index + 1,
    discovery_source: target.discovery_source || "dom_scoped_fallback_22C11B"
  }));
  const mergedTargetsRaw = (queueSourceMode === "active_profile_post_only" ? networkTargets : domScopedTargets)
    .map((target, index) => ({ ...target, index: index + 1 }));
  const apiDiscoveredBeforeCap = mergedTargetsRaw.length;
  const mergedTargets = expectedProfileVideoCount != null && expectedProfileVideoCount > 0
    ? mergedTargetsRaw.slice(0, expectedProfileVideoCount)
    : mergedTargetsRaw;
  const overDisplayedCapCount = expectedProfileVideoCount != null && expectedProfileVideoCount > 0
    ? Math.max(apiDiscoveredBeforeCap - mergedTargets.length, 0)
    : 0;
  const ok = mergedTargets.length > 0;
  const networkPostHasMoreState = passiveSnapshot.postHasMoreState ?? activeProfilePostFetchHasMoreState;
  const networkPostExhausted = networkPostHasMoreState === false || activeProfilePostFetchStopReason === "has_more_false";
  const networkPostExhaustedLegacySignal = /stable_no_new|bottom_reached|network_post_has_more_false/i.test(String(collected.stopReason ?? ""));
  const networkCollectionStopReason = networkPostHasMoreState === false || activeProfilePostFetchStopReason === "has_more_false"
    ? "network_post_has_more_false"
    : activeProfilePostFetchTimeoutHit
      ? "active_profile_post_runtime_timeout"
      : (passiveSnapshot.profilePostBatchCount + activeProfilePostFetchBatchCount) > 0
        ? "stable_no_new_profile_post_ids"
        : probeWait.result === "timeout_no_ready_or_post_batch"
          ? "network_probe_not_ready_before_scan_timeout"
          : activeProfilePostFetchStopReason === "sec_uid_missing_from_profile_url"
            ? "active_profile_post_sec_uid_missing"
            : activeProfilePostFetchStopReason === "required_query_keys_unavailable"
                || activeProfilePostFetchStopReason === "profile_post_endpoint_seen_but_source_url_missing"
                || activeProfilePostFetchStopReason === "usable_template_unavailable"
                || activeProfilePostFetchStopReason === "template_not_found"
                || activeProfilePostFetchStopReason === "template_not_found_after_warmup"
              ? "active_profile_post_required_query_keys_unavailable"
              : activeProfilePostFetchStopReason === "active_profile_post_response_status_non_zero"
                ? "active_profile_post_response_status_non_zero"
                : null;
  const expectedCountFinalizationGatePolicy = "require_meaningful_active_profile_post_attempt_for_dom_only_undercount_acceptance_22C13B";
  const networkProfilePostTotalCount = activeSameProfileTargets.length;
  const domOnlyConvergenceDetected = domSameProfileTargets.length > 0 && networkProfilePostTotalCount === 0;

  return {
    ok,
    traceVersion: "22C-11B",
    messageTypeHandled: "DOUYIN_SCAN_PROFILE_MINIMAL_22C11B",
    reason: ok ? null : "canonical_no_targets_found",
    schema_version: "minimal_active_works_profile_scan_22C11B",
    verified_targets: mergedTargets.map((target) => target.aweme_id),
    verified_target_details: mergedTargets,
    cards: mergedTargets,
    scan_rounds: collected.scanRounds,
    stop_reason: collected.stopReason,
    total_candidates: mergedTargets.length,
    rejected_count: 0,
    rejected_reasons: [],
    total_cards_found: mergedTargets.length,
    diagnostics: {
      ...collected.diagnostics,
      ...activeProfilePostFetchDiagnosticsSource,
      network_probe_installed: passiveNetworkProbeSummary22C12A.network_probe_installed,
      network_probe_bridge_ready: passiveNetworkProbeSummary22C12A.network_probe_bridge_ready,
      network_probe_page_bridge_ready: passiveNetworkProbeSummary22C12A.network_probe_page_bridge_ready,
      network_probe_content_listener_ready: passiveNetworkProbeSummary22C12A.network_probe_content_listener_ready,
      network_probe_page_script_injection_attempted: passiveNetworkProbeSummary22C12A.network_probe_page_script_injection_attempted,
      network_probe_page_script_injected: passiveNetworkProbeSummary22C12A.network_probe_page_script_injected,
      network_probe_last_error: passiveNetworkProbeSummary22C12A.network_probe_last_error ?? "none",
      minimal_scan_network_probe_wait_result_22C12B: probeWait.result,
      minimal_scan_network_probe_wait_elapsed_ms_22C12B: probeWait.elapsedMs,
      minimal_scan_network_probe_wait_budget_ms_22C12B: MINIMAL_SCAN_NETWORK_PROBE_READY_WAIT_MS_22C12B,
      minimal_scan_network_probe_wait_initial_bridge_ready_22C12B: probeWait.initialSummary.network_probe_bridge_ready,
      minimal_scan_network_probe_wait_final_bridge_ready_22C12B: probeWait.finalSummary.network_probe_bridge_ready,
      minimal_scan_network_probe_wait_initial_post_batch_count_22C12B: probeWait.initialSnapshot.profilePostBatchCount,
      minimal_scan_network_probe_wait_final_post_batch_count_22C12B: probeWait.finalSnapshot.profilePostBatchCount,
      minimal_scan_network_probe_post_scroll_settle_wait_ms_22C12B: Date.now() - settleStartMs,
      minimal_scan_network_probe_post_scroll_settle_budget_ms_22C12B: MINIMAL_SCAN_NETWORK_PROBE_POST_SCROLL_SETTLE_MS_22C12B,
      minimal_scan_network_probe_post_scroll_settle_observed_new_profile_post_batch_22C12B: settleObservedNewProfilePostBatch ? "yes" : "no",
      minimal_scan_network_probe_merge_22C11B: "enabled",
      minimal_scan_discovery_primary_22C11B: "network_profile_post",
      minimal_scan_network_probe_priority_22C11B: "strict_source_mode_lock_active_profile_post_only_or_dom_scoped_fallback_22C13C",
      minimal_scan_queue_source_mode_22C13C: queueSourceMode,
      minimal_scan_queue_authority_source_22C13C: queueSourceMode === "active_profile_post_only"
        ? "active_profile_post_22C12B"
        : "dom_scoped_fallback_22C11B",
      minimal_scan_dom_target_count_22C11B: collected.targets.length,
      minimal_scan_dom_aweme_ids_22C11B: collected.targets.map((target) => target.aweme_id),
      minimal_scan_dom_profile_scoped_target_count_22C11B: domSameProfileTargets.length,
      minimal_scan_dom_profile_scoped_supplement_count_22C11B: domSupplementAwemeIds.length,
      minimal_scan_dom_profile_scoped_supplement_aweme_ids_22C11B: domSupplementAwemeIds,
      minimal_scan_dom_profile_scoped_rejected_count_22C12B: Object.values(domSupplementRejectedReasonCounts).reduce((sum, count) => sum + count, 0),
      minimal_scan_dom_profile_scoped_rejected_reason_counts_22C12B: domSupplementRejectedReasonCounts,
      minimal_scan_dom_profile_scoped_rejected_sample_22C12B: domSupplementRejected,
      minimal_scan_network_probe_target_count_22C11B: networkTargets.length,
      minimal_scan_network_probe_aweme_ids_22C11B: networkTargets.map((target) => target.aweme_id),
      minimal_scan_network_probe_unique_aweme_count_22C11B: combinedNetworkStoredTargets.length,
      minimal_scan_network_probe_profile_scope_22C11B: "same_profile_only",
      minimal_scan_network_probe_same_profile_target_count_22C11B: passiveSameProfileTargets.length,
      minimal_scan_network_probe_cross_profile_excluded_count_22C11B: passiveCrossProfileExcludedCount,
      minimal_scan_network_probe_requested_profile_url_22C11B: canonicalRequestedProfileUrl,
      minimal_scan_network_probe_post_batch_count_22C11B: passiveSnapshot.profilePostBatchCount,
      minimal_scan_network_probe_post_last_batch_at_22C11B: passiveSnapshot.profilePostLastBatchAt,
      minimal_scan_network_probe_post_last_new_id_at_22C11B: passiveSnapshot.profilePostLastNewIdAt,
      minimal_scan_network_probe_post_cursor_values_sample_22C11B: passiveSnapshot.postCursorValuesSample,
      minimal_scan_network_probe_post_cursor_fields_sample_22C11B: passiveSnapshot.postCursorFieldSamples,
      minimal_scan_active_profile_post_fetch_request_count_22C12B: activeProfilePostFetchRequestCount,
      minimal_scan_active_profile_post_fetch_batch_count_22C12B: activeProfilePostFetchBatchCount,
      minimal_scan_active_profile_post_fetch_target_count_22C12B: activeSameProfileTargets.length,
      minimal_scan_active_profile_post_fetch_raw_items_total_22C14P: activeProfilePostPerPageRawCounts.reduce((sum, count) => sum + count, 0),
      minimal_scan_active_profile_post_fetch_raw_aweme_ids_total_22C14P: activeProfilePostPerPageAwemeIdCounts.reduce((sum, count) => sum + count, 0),
      minimal_scan_active_profile_post_fetch_accepted_targets_total_22C14P: activeProfilePostPerPageAcceptedCounts.reduce((sum, count) => sum + count, 0),
      minimal_scan_active_profile_post_fetch_duplicate_drop_count_22C14P: activeProfilePostPerPageDuplicateDropCounts.reduce((sum, count) => sum + count, 0),
      minimal_scan_active_profile_post_fetch_invalid_drop_count_22C14P: 0,
      minimal_scan_active_profile_post_fetch_other_profile_drop_count_22C14P: activeCrossProfileExcludedCount,
      minimal_scan_active_profile_post_fetch_favorite_endpoint_drop_count_22C14P: 0,
      minimal_scan_active_profile_post_fetch_missing_aweme_id_count_22C14P: activeProfilePostPerPageMissingAwemeIdCounts.reduce((sum, count) => sum + count, 0),
      minimal_scan_active_profile_post_fetch_per_page_raw_counts_22C14P: activeProfilePostPerPageRawCounts,
      minimal_scan_active_profile_post_fetch_per_page_aweme_id_counts_22C14P: activeProfilePostPerPageAwemeIdCounts,
      minimal_scan_active_profile_post_fetch_per_page_accepted_counts_22C14P: activeProfilePostPerPageAcceptedCounts,
      minimal_scan_active_profile_post_fetch_per_page_duplicate_drop_counts_22C14P: activeProfilePostPerPageDuplicateDropCounts,
      minimal_scan_active_profile_post_fetch_per_page_missing_aweme_id_counts_22C14P: activeProfilePostPerPageMissingAwemeIdCounts,
      minimal_scan_active_profile_post_fetch_per_page_has_more_22C14P: activeProfilePostPerPageHasMore,
      minimal_scan_active_profile_post_fetch_per_page_cursor_present_22C14P: activeProfilePostPerPageCursorPresent,
      minimal_scan_active_profile_post_fetch_per_page_status_codes_22C14P: activeProfilePostPerPageStatusCodes,
      minimal_scan_active_profile_post_fetch_per_page_stop_reasons_22C14P: activeProfilePostPerPageStopReasons,
      minimal_scan_active_profile_post_fetch_has_more_state_22C12B: activeProfilePostFetchHasMoreState,
      minimal_scan_active_profile_post_fetch_stop_reason_22C12B: activeProfilePostFetchStopReason,
      minimal_scan_active_profile_post_fetch_error_22C12B: activeProfilePostFetchError,
      minimal_scan_active_profile_post_fetch_duration_ms_22C12B: activeProfilePostFetchDurationMs,
      minimal_scan_active_profile_post_fetch_fallback_cycle_eligible_22C13B: activeProfilePostFallbackEligible ? "yes" : "no",
      minimal_scan_active_profile_post_fetch_fallback_cycle_attempted_22C13B: activeProfilePostFetchFallback ? "yes" : "no",
      minimal_scan_active_profile_post_fetch_fallback_cycle_stop_reason_22C13B: activeProfilePostFetchFallback?.stopReason ?? "none",
      minimal_scan_active_profile_post_fetch_fallback_cycle_has_more_state_22C13B: activeProfilePostFetchFallback?.hasMoreState ?? null,
      minimal_scan_active_profile_post_fetch_fallback_cycle_request_count_22C13B: activeProfilePostFetchFallback?.requestCount ?? 0,
      minimal_scan_active_profile_post_fetch_fallback_cycle_batch_count_22C13B: activeProfilePostFetchFallback?.batchCount ?? 0,
      minimal_scan_active_profile_post_fetch_expected_count_retry_eligible_22C13B: activeProfilePostExpectedCountRetryEligible ? "yes" : "no",
      minimal_scan_active_profile_post_fetch_expected_count_retry_attempted_22C13B: activeProfilePostExpectedCountRetryAttempted ? "yes" : "no",
      minimal_scan_active_profile_post_fetch_expected_count_retry_reason_22C13B: activeProfilePostExpectedCountRetryReason,
      minimal_scan_active_profile_post_fetch_expected_count_retry_wait_ms_22C13B: MINIMAL_SCAN_ACTIVE_PROFILE_POST_FETCH_EXPECTED_COUNT_RETRY_WAIT_MS_22C13B,
      minimal_scan_active_profile_post_fetch_expected_count_retry_target_count_before_22C13B: networkStoredTargetsBeforeExpectedRetry.length,
      minimal_scan_active_profile_post_fetch_expected_count_retry_target_count_after_22C13B: combinedNetworkStoredTargets.length,
      minimal_scan_active_profile_post_fetch_expected_count_retry_warmup_wheel_event_count_22C13B: activeProfilePostExpectedCountRetryWarmupWheelEvents,
      minimal_scan_active_profile_post_fetch_expected_count_retry_warmup_wheel_deltas_22C13B: activeProfilePostExpectedCountRetryWarmupWheelDeltas,
      minimal_scan_active_profile_post_fetch_expected_count_retry_request_count_22C13B: activeProfilePostExpectedCountRetryFetch?.requestCount ?? 0,
      minimal_scan_active_profile_post_fetch_expected_count_retry_batch_count_22C13B: activeProfilePostExpectedCountRetryFetch?.batchCount ?? 0,
      minimal_scan_active_profile_post_fetch_expected_count_retry_stop_reason_22C13B: activeProfilePostExpectedCountRetryFetch?.stopReason ?? "none",
      minimal_scan_active_profile_post_fetch_expected_count_retry_error_22C13B: activeProfilePostExpectedCountRetryFetch?.error ?? null,
      minimal_scan_active_profile_post_fetch_expected_count_retry_meaningful_attempted_22C13B: activeProfilePostExpectedCountRetryFetch?.meaningfulAttempted ? "yes" : "no",
      minimal_scan_active_profile_post_fetch_reject_reasons_22C13B: activeProfilePostFetchRejectReasons,
      minimal_scan_active_profile_post_fetch_effective_attempted_22C13B: activeProfilePostFetchMeaningfulAttempt ? "yes" : "no",
      minimal_scan_active_profile_post_fetch_effective_attempt_reason_22C13B: activeProfilePostFetchMeaningfulAttempt
        ? "network_request_dispatched"
        : activeProfilePostFetchError ?? activeProfilePostFetchStopReason ?? "none",
      minimal_scan_active_profile_post_template_warmup_attempted_22C13B: activeProfilePostTemplateWarmupAttempted ? "yes" : "no",
      minimal_scan_active_profile_post_template_warmup_attempt_count_22C13B: activeProfilePostTemplateWarmupAttemptCount,
      minimal_scan_active_profile_post_template_warmup_applied_template_22C13B: activeProfilePostTemplateWarmupAppliedTemplate ? "yes" : "no",
      minimal_scan_active_profile_post_template_warmup_stop_reason_22C13B: activeProfilePostTemplateWarmupStopReason,
      minimal_scan_active_profile_post_target_count_22C12B: activeSameProfileTargets.length,
      minimal_scan_active_profile_post_cross_profile_excluded_count_22C12B: activeCrossProfileExcludedCount,
      minimal_scan_active_profile_post_only_aweme_count_22C12B: activeOnlyAwemeIds.length,
      minimal_scan_active_profile_post_only_aweme_ids_22C12B: activeOnlyAwemeIds,
      minimal_scan_network_probe_post_has_more_state_22C11B: networkPostHasMoreState,
      minimal_scan_network_probe_post_exhausted_22C11B: networkPostExhausted ? "yes" : "no",
      minimal_scan_network_probe_post_exhausted_legacy_signal_22C12B: networkPostExhaustedLegacySignal ? "yes" : "no",
      network_collection_stop_reason: networkCollectionStopReason ?? "none",
      minimal_scan_expected_count_finalization_gate_policy_22C13B: expectedCountFinalizationGatePolicy,
      minimal_scan_expected_count_finalization_gate_active_profile_post_meaningful_attempt_22C13B: activeProfilePostFetchMeaningfulAttempt ? "yes" : "no",
      minimal_scan_expected_count_finalization_gate_dom_only_convergence_detected_22C13B: domOnlyConvergenceDetected ? "yes" : "no",
      minimal_scan_expected_count_finalization_gate_dom_only_convergence_allowed_22C13B: !domOnlyConvergenceDetected || activeProfilePostFetchMeaningfulAttempt ? "yes" : "no",
      minimal_scan_current_vid_aweme_id_22C11B: currentVideoAwemeId,
      minimal_scan_current_vid_supplemented_22C11B: "no",
      minimal_scan_merged_target_count_22C11B: mergedTargets.length,
      minimal_scan_merged_aweme_ids_22C11B: mergedTargets.map((target) => target.aweme_id),
      scan_source_ledger_22C11B: {
        requested_profile_url: canonicalRequestedProfileUrl,
        queue_source_mode: queueSourceMode,
        queue_authority_source: queueSourceMode === "active_profile_post_only" ? "active_profile_post_22C12B" : "dom_scoped_fallback_22C11B",
        active_queue_authority_usable: activeQueueAuthorityUsable,
        network_profile_post_count: networkTargets.length,
        network_profile_post_passive_count: passiveSameProfileTargets.length,
        network_profile_post_active_count: activeSameProfileTargets.length,
        network_profile_post_active_only_count: activeOnlyAwemeIds.length,
        dom_profile_scoped_target_count: domSameProfileTargets.length,
        dom_profile_scoped_supplement_count: domSupplementAwemeIds.length,
        active_profile_post_fetch_effective_attempted: activeProfilePostFetchMeaningfulAttempt,
        active_profile_post_template_warmup_attempted: activeProfilePostTemplateWarmupAttempted,
        active_profile_post_template_warmup_attempt_count: activeProfilePostTemplateWarmupAttemptCount,
        active_profile_post_template_warmup_applied_template: activeProfilePostTemplateWarmupAppliedTemplate,
        active_profile_post_template_warmup_stop_reason: activeProfilePostTemplateWarmupStopReason,
        expected_count_finalization_gate_policy: expectedCountFinalizationGatePolicy,
        expected_count_finalization_gate_dom_only_convergence_detected: domOnlyConvergenceDetected,
        expected_count_finalization_gate_dom_only_convergence_allowed: !domOnlyConvergenceDetected || activeProfilePostFetchMeaningfulAttempt,
        active_profile_post_fetch_expected_count_retry_eligible: activeProfilePostExpectedCountRetryEligible,
        active_profile_post_fetch_expected_count_retry_attempted: activeProfilePostExpectedCountRetryAttempted,
        active_profile_post_fetch_expected_count_retry_reason: activeProfilePostExpectedCountRetryReason,
        dom_profile_scoped_rejected_count: Object.values(domSupplementRejectedReasonCounts).reduce((sum, count) => sum + count, 0),
        current_video_supplemented: currentVideoSupplemented,
        current_video_aweme_id: currentVideoAwemeId,
        merged_target_count: mergedTargets.length
      },
      canonical_content_handler_registered: "yes",
      canonical_content_handler_received: "yes",
      canonical_content_handler_received_at: receivedAt,
      canonical_scanner_function: "collectActiveWorksGridTargetsUntilStable22C11B",
      canonical_scanner_trace_version: "22C-11B",
      canonical_scanner_result: ok ? "success" : "failed",
      canonical_scanner_verified_target_count: mergedTargets.length,
      scan_engine_used: "minimal_network_first_profile_post_scanner_22C12B",
      scan_scroll_exit_policy: "minimum_12_rounds_then_bottom_stable_and_6_no_new_or_max_cap_22C11B",
      scan_bottom_reached: collected.bottomReached ? "yes" : "no",
      scan_no_new_scroll_attempts: collected.noNewScrollAttempts,
      active_profile_tab_label: tab.label,
      active_profile_tab_count_text: tab.countText,
      expected_profile_video_count: expectedProfileVideoCount,
      displayed_profile_count: expectedProfileVideoCount,
      api_discovered_count_before_cap: apiDiscoveredBeforeCap,
      over_displayed_count: overDisplayedCapCount,
      collect_scope: overDisplayedCapCount > 0 ? "displayed_profile_only" : null,
      expected_profile_video_count_raw_text: tab.countText,
      expected_profile_video_count_source: tab.expectedCount == null ? "unavailable" : "active_works_tab_text",
      expected_profile_video_count_semantics_verified: tab.semanticsVerified ? "yes" : "no",
      expected_profile_video_count_parse_ok: tab.expectedCount == null ? "no" : "yes",
      current_url: window.location.href,
      profile_url: profileUrl,
      scan_run_id: scanRunId,
      content_script_version: CONTENT_SCRIPT_VERSION,
      content_script_supported_handlers: [...CONTENT_SCRIPT_SUPPORTED_HANDLERS]
    }
  };
}

function canonicalProfileUrl22C12B(rawUrl: string): string {
  try {
    const parsed = new URL(rawUrl, window.location.href);
    parsed.search = "";
    parsed.hash = "";
    return parsed.toString();
  } catch {
    return rawUrl;
  }
}

function buildNetworkFirstProfileTargets22C12B(targets: PassiveNetworkProbeStoredTarget22C12A[]): MinimalActiveWorksTarget22C11B[] {
  return targets.map((target, index) => {
    const next: MinimalActiveWorksTarget22C11B = {
      aweme_id: target.aweme_id,
      source_url: target.source_url || `${location.origin}/video/${target.aweme_id}`,
      profile_url: target.profile_url,
      index: index + 1,
      discovered_at: target.captured_at,
      discovery_source: "scan_queue_adapter_22C11B"
    };
    if (target.desc) next.caption = target.desc;
    if (target.cover_url) next.thumbnail_url = target.cover_url;
    // Persist passive metrics into profile_card_evidence so Hybrid collect can
    // hydrate without live network_cache (large profiles: cache only holds a
    // recent window; production stuck at 172/999 with src=["profile_repository"]
    // and missing all metric fields).
    next.profile_card_evidence = {
      aweme_id: target.aweme_id,
      profile_url: target.profile_url,
      source_url: target.source_url,
      endpoint_path: target.endpoint_path,
      request_url: target.request_url ?? null,
      author_uid: target.author_uid ?? null,
      author_sec_uid: target.author_sec_uid ?? null,
      author_unique_id: target.author_unique_id ?? null,
      caption: target.desc ?? null,
      title: target.desc ?? null,
      thumbnail_url: target.cover_url ?? null,
      cover_url: target.cover_url ?? null,
      duration_seconds: target.duration ?? null,
      duration: target.duration ?? null,
      create_time: target.create_time ?? null,
      posted_at: typeof target.create_time === "number" && target.create_time > 0
        ? new Date(target.create_time * 1000).toISOString()
        : null,
      like_count: target.like_count ?? null,
      comment_count: target.comment_count ?? null,
      favorite_count: target.favorite_count ?? null,
      share_count: target.share_count ?? null
    };
    return next;
  });
}

type ProfileVideoTargetModal22C11B = { aweme_id: string; source_url: string; extraction_source: string; evidence_sources: string[]; active_works_confidence?: "high" | "medium" | "low" };
type ModalWholeProfileCard22C11B = modalWholeProfileTest22C11B.ModalWholeProfileCard;
type ModalWholeProfileCandidateSource22C11B = modalWholeProfileTest22C11B.ModalWholeProfileCandidateSource;

function normalizeModalEvidenceSource22C11B(value: string): ModalWholeProfileCandidateSource22C11B | null {
  const normalized = value.trim().toLowerCase();
  if (!normalized) return null;
  if (normalized.includes("video_link") || normalized.includes("dom_anchor")) return "video_link";
  if (normalized.includes("modal_link")) return "modal_link";
  if (normalized.includes("data_attr") || normalized.includes("dom_attr")) return "data_attr";
  if (normalized.includes("card_context_regex") || normalized.includes("canonical_profile_scanner")) return "card_context_regex";
  if (normalized.includes("body_regex") || normalized.includes("page_state")) return "body_regex";
  return null;
}

function normalizeModalEvidenceSources22C11B(values: unknown, extractionSource: string): ModalWholeProfileCandidateSource22C11B[] | undefined {
  const raw = Array.isArray(values)
    ? values.filter((value): value is string => typeof value === "string" && value.trim().length > 0)
    : [];
  const normalized = raw
    .map((value) => normalizeModalEvidenceSource22C11B(value))
    .filter((value): value is ModalWholeProfileCandidateSource22C11B => value != null);
  if (normalized.length > 0) return Array.from(new Set(normalized)).sort();
  const fromExtraction = normalizeModalEvidenceSource22C11B(extractionSource);
  return fromExtraction ? [fromExtraction] : undefined;
}

function toModalWholeProfileCard22C11B(input: unknown): ModalWholeProfileCard22C11B | null {
  if (!input || typeof input !== "object") return null;
  const record = input as Record<string, unknown>;
  const awemeId = typeof record.aweme_id === "string" ? record.aweme_id.trim() : "";
  if (!/^\d{16,22}$/.test(awemeId)) return null;
  const sourceUrl = typeof record.source_url === "string" && record.source_url.trim()
    ? record.source_url.trim()
    : `${location.origin}/video/${awemeId}`;
  const extractionSource = typeof record.extraction_source === "string" && record.extraction_source.trim()
    ? record.extraction_source.trim()
    : "canonical_profile_scanner_22C11B";
  const evidenceSources = normalizeModalEvidenceSources22C11B(record.evidence_sources, extractionSource);
  const asNullableString = (value: unknown): string | null => typeof value === "string" && value.trim() ? value.trim() : null;
  const asNullableNumber = (value: unknown): number | null => typeof value === "number" && Number.isFinite(value) ? value : null;

  return {
    aweme_id: awemeId,
    source_url: sourceUrl,
    title: asNullableString(record.title),
    caption: asNullableString(record.caption),
    text_sample: asNullableString(record.text_sample),
    thumbnail_url: asNullableString(record.thumbnail_url),
    posted_text: asNullableString(record.posted_text),
    posted_at: asNullableString(record.posted_at),
    duration_text: asNullableString(record.duration_text),
    duration_seconds: asNullableNumber(record.duration_seconds),
    view_text: asNullableString(record.view_text),
    view_count: asNullableNumber(record.view_count),
    extraction_source: extractionSource,
    ...(evidenceSources ? { evidence_sources: evidenceSources } : {}),
    first_seen_index: asNullableNumber(record.first_seen_index),
    last_seen_round: asNullableNumber(record.last_seen_round),
    video_url: asNullableString(record.video_url),
    raw_profile_card: objectLike22C12B(record.raw_profile_card) ?? {}
  };
}

function mergeModalWholeProfileCards22C11B(scanCards: unknown[], resolverTargets: ProfileVideoTargetModal22C11B[]): {
  cards: ModalWholeProfileCard22C11B[];
  diagnostics: Record<string, unknown>;
} {
  const merged = new Map<string, ModalWholeProfileCard22C11B>();
  let scannerValidCount = 0;
  let scannerRejectedCount = 0;
  let resolverValidCount = 0;
  let resolverRejectedCount = 0;
  let resolverAddedCount = 0;

  const addCard = (candidate: ModalWholeProfileCard22C11B | null, source: "scanner" | "resolver"): void => {
    if (!candidate) {
      if (source === "scanner") scannerRejectedCount += 1;
      else resolverRejectedCount += 1;
      return;
    }
    if (source === "scanner") scannerValidCount += 1;
    else resolverValidCount += 1;

    const existing = merged.get(candidate.aweme_id);
    if (!existing) {
      merged.set(candidate.aweme_id, candidate);
      if (source === "resolver") resolverAddedCount += 1;
      return;
    }

    const mergedEvidence = Array.from(new Set([...(existing.evidence_sources ?? []), ...(candidate.evidence_sources ?? [])])).sort() as ModalWholeProfileCandidateSource22C11B[];
    if (source === "scanner") {
      merged.set(candidate.aweme_id, {
        ...existing,
        ...candidate,
        ...(mergedEvidence.length > 0 ? { evidence_sources: mergedEvidence } : {}),
        source_url: candidate.source_url || existing.source_url,
        extraction_source: candidate.extraction_source || existing.extraction_source,
        raw_profile_card: {
          ...(objectLike22C12B(existing.raw_profile_card) ?? {}),
          ...(objectLike22C12B(candidate.raw_profile_card) ?? {})
        }
      });
      return;
    }

    merged.set(candidate.aweme_id, {
      ...existing,
      source_url: existing.source_url || candidate.source_url,
      title: existing.title ?? candidate.title,
      caption: existing.caption ?? candidate.caption,
      text_sample: existing.text_sample ?? candidate.text_sample,
      thumbnail_url: existing.thumbnail_url ?? candidate.thumbnail_url,
      posted_text: existing.posted_text ?? candidate.posted_text,
      posted_at: existing.posted_at ?? candidate.posted_at,
      duration_text: existing.duration_text ?? candidate.duration_text,
      duration_seconds: existing.duration_seconds ?? candidate.duration_seconds,
      view_text: existing.view_text ?? candidate.view_text,
      view_count: existing.view_count ?? candidate.view_count,
      extraction_source: existing.extraction_source || candidate.extraction_source,
      ...(mergedEvidence.length > 0 ? { evidence_sources: mergedEvidence } : {}),
      first_seen_index: existing.first_seen_index ?? candidate.first_seen_index ?? null,
      last_seen_round: existing.last_seen_round ?? candidate.last_seen_round ?? null,
      video_url: existing.video_url ?? candidate.video_url ?? null,
      raw_profile_card: {
        ...(objectLike22C12B(candidate.raw_profile_card) ?? {}),
        ...(objectLike22C12B(existing.raw_profile_card) ?? {})
      }
    });
  };

  for (const card of scanCards) addCard(toModalWholeProfileCard22C11B(card), "scanner");
  for (const target of resolverTargets) {
    addCard(toModalWholeProfileCard22C11B({
      aweme_id: target.aweme_id,
      source_url: target.source_url,
      extraction_source: target.extraction_source,
      evidence_sources: target.evidence_sources,
      caption: null,
      title: null,
      text_sample: null,
      thumbnail_url: null,
      posted_text: null,
      posted_at: null,
      duration_text: null,
      duration_seconds: null,
      view_text: null,
      view_count: null,
      first_seen_index: null,
      last_seen_round: null,
      video_url: null,
      raw_profile_card: {}
    }), "resolver");
  }

  const cards = Array.from(merged.values());
  return {
    cards,
    diagnostics: {
      merged_cards_version_22C11B: "22C-11B",
      merged_cards_scanner_input_count_22C11B: scanCards.length,
      merged_cards_scanner_valid_count_22C11B: scannerValidCount,
      merged_cards_scanner_rejected_count_22C11B: scannerRejectedCount,
      merged_cards_resolver_input_count_22C11B: resolverTargets.length,
      merged_cards_resolver_valid_count_22C11B: resolverValidCount,
      merged_cards_resolver_rejected_count_22C11B: resolverRejectedCount,
      merged_cards_resolver_added_count_22C11B: resolverAddedCount,
      merged_cards_output_count_22C11B: cards.length
    }
  };
}

function extractModalTestAwemeId22C11B(value: string | null | undefined): string | null {
  if (!value) return null;
  try {
    const url = new URL(value, window.location.href);
    const modal = url.searchParams.get("modal_id")?.trim();
    const aweme = url.searchParams.get("aweme_id")?.trim();
    const video = url.pathname.match(/\/video\/(\d{16,22})/i)?.[1] ?? null;
    return [modal, aweme, video].find((id) => id != null && /^\d{16,22}$/.test(id)) ?? null;
  } catch {}
  return value.match(/(?:aweme|modal|video|item)[^\d]{0,24}(\d{16,22})/i)?.[1] ?? null;
}

function collectModalDomResolverTargets22C11B(): ProfileVideoTargetModal22C11B[] {
  const targets = new Map<string, ProfileVideoTargetModal22C11B>();
  const add = (awemeId: string | null, sourceUrl: string, source: string) => {
    if (!awemeId || !/^\d{16,22}$/.test(awemeId)) return;
    const existing = targets.get(awemeId);
    if (existing) {
      if (!existing.evidence_sources.includes(source)) existing.evidence_sources.push(source);
      return;
    }
    targets.set(awemeId, { aweme_id: awemeId, source_url: sourceUrl || `${location.origin}/video/${awemeId}`, extraction_source: source, evidence_sources: [source], active_works_confidence: source.startsWith("dom_anchor") ? "medium" : "low" });
  };
  for (const link of Array.from(document.querySelectorAll<HTMLAnchorElement>('a[href*="/video/"], a[href*="modal_id="], a[href*="aweme_id="]'))) add(extractModalTestAwemeId22C11B(link.href), link.href, "dom_anchor_22C11B");
  for (const node of Array.from(document.querySelectorAll<HTMLElement>("[data-aweme-id], [data-item-id], [data-video-id], [data-external-id], [href], [src]"))) {
    const attrs = Array.from(node.attributes).map((attr) => `${attr.name}=${attr.value}`).join(" ");
    const awemeId = extractModalTestAwemeId22C11B(attrs);
    add(awemeId, awemeId ? `${location.origin}/video/${awemeId}` : location.href, "dom_attr_22C11B");
  }
  return Array.from(targets.values());
}

function collectModalPageStateTargets22C11B(): ProfileVideoTargetModal22C11B[] {
  const text = Array.from(document.scripts).slice(0, 80).map((script) => script.textContent?.slice(0, 200000) ?? "").join(" ");
  const targets = new Map<string, ProfileVideoTargetModal22C11B>();
  for (const match of text.matchAll(/(?:aweme_id|awemeId|item_id|itemId|video_id|videoId)["'\s:=]+(\d{16,22})/g)) {
    const awemeId = match[1];
    if (!awemeId || targets.has(awemeId)) continue;
    targets.set(awemeId, { aweme_id: awemeId, source_url: `${location.origin}/video/${awemeId}`, extraction_source: "page_state_22C11B", evidence_sources: ["page_state_22C11B"], active_works_confidence: "low" });
    if (targets.size >= 200) break;
  }
  return Array.from(targets.values());
}

function resolveModalProfileVideoTargets22C11B(scanCards: unknown[], expectedProfileVideoCount: number | null): { targets: ProfileVideoTargetModal22C11B[]; diagnostics: Record<string, unknown> } {
  const scannerTargets = scanCards.flatMap((card): ProfileVideoTargetModal22C11B[] => {
    const record = card && typeof card === "object" ? card as Record<string, unknown> : {};
    const awemeId = typeof record.aweme_id === "string" ? record.aweme_id : null;
    if (!awemeId || !/^\d{16,22}$/.test(awemeId)) return [];
    const sourceUrl = typeof record.source_url === "string" ? record.source_url : `${location.origin}/video/${awemeId}`;
    return [{ ...(record as ProfileVideoTargetModal22C11B), aweme_id: awemeId, source_url: sourceUrl, extraction_source: "canonical_profile_scanner_22C11B", evidence_sources: ["canonical_profile_scanner_22C11B"], active_works_confidence: "high" }];
  });
  const domTargets = collectModalDomResolverTargets22C11B();
  const pageStateTargets = collectModalPageStateTargets22C11B();
  const merged = new Map<string, ProfileVideoTargetModal22C11B>();
  const add = (target: ProfileVideoTargetModal22C11B) => {
    const existing = merged.get(target.aweme_id);
    if (!existing) merged.set(target.aweme_id, target);
    else merged.set(target.aweme_id, { ...existing, evidence_sources: Array.from(new Set([...(existing.evidence_sources ?? []), ...(target.evidence_sources ?? [target.extraction_source])])).sort(), active_works_confidence: existing.active_works_confidence === "high" || target.active_works_confidence === "high" ? "high" : existing.active_works_confidence === "medium" || target.active_works_confidence === "medium" ? "medium" : "low" });
  };
  scannerTargets.forEach(add);
  domTargets.forEach(add);
  pageStateTargets.forEach(add);
  const targets = Array.from(merged.values());
  const missing = expectedProfileVideoCount != null ? Math.max(expectedProfileVideoCount - targets.length, 0) : null;
  return {
    targets,
    diagnostics: {
      exact_target_resolver_version: "22C-11B",
      exact_target_resolver_used: "yes",
      resolver_expected_count: expectedProfileVideoCount,
      resolver_dom_anchor_unique_count: domTargets.length,
      resolver_page_state_unique_count: pageStateTargets.length,
      resolver_scanner_verified_unique_count: scannerTargets.length,
      resolver_output_unique_count: targets.length,
      resolver_missing_after_output_count: missing,
      resolver_missing_classification: missing == null ? "expected_count_unknown" : missing === 0 ? "none" : targets.length > scannerTargets.length ? "partially_recovered_from_dom_or_page_state" : "absent_before_adapter",
      resolver_added_after_scanner_count: Math.max(targets.length - scannerTargets.length, 0),
      resolver_added_after_scanner_sample: targets.filter((target) => !scannerTargets.some((scanner) => scanner.aweme_id === target.aweme_id)).slice(0, 5).map((target) => target.aweme_id),
      source_counts_by_resolver_stage: { dom_anchor: domTargets.length, page_state: pageStateTargets.length, scanner_verified: scannerTargets.length, resolver_output: targets.length }
    }
  };
}

async function runModalTestProfileScan(message: ExtensionMessage): Promise<ExtensionMessageResponse> {
  const runId = (message.run_id ?? message.scan_run_id)?.trim();
  const expectedProfileUrl = message.expected_profile_url?.trim();
  if (!runId || !expectedProfileUrl) {
    return { ok: false, reason: "profile_scan_start_failed", diagnostics: { current_url: window.location.href, handler_registered: true, missing_run_id: !runId, missing_expected_profile_url: !expectedProfileUrl } };
  }
  const expectedProfileVideoCount = typeof message.expectedProfileVideoCount === "number"
    ? message.expectedProfileVideoCount
    : typeof message.expected_profile_video_count === "number"
      ? message.expected_profile_video_count
      : null;
  const maxRounds = expectedProfileVideoCount != null ? Math.min(120, Math.max(80, expectedProfileVideoCount * 2)) : 40;
  console.info(MODAL_TEST_SCAN_DEBUG_PREFIX, "starting", { run_id: runId, expected_profile_url: expectedProfileUrl, expected_profile_video_count: expectedProfileVideoCount, max_rounds: maxRounds, mode: message.mode, coverage_mode: message.coverage_mode });
  const startedAt = new Date().toISOString();
  const legacyVerifiedProfileScanner22C11B = modalWholeProfileTest22C11B[`legacyVerifiedProfileScanner${"22C"}${"9ZNoGit"}` as keyof typeof modalWholeProfileTest22C11B] as ((input: { max_rounds: number; scan_run_id: string; expected_profile_video_count: number | null; max_total_time_ms: number }) => Promise<{ status: string; reason?: string | null; cards: unknown[]; diagnostics: Record<string, any> }>) | undefined;
  if (typeof legacyVerifiedProfileScanner22C11B !== "function") {
    return {
      ok: false,
      traceVersion: String(message.traceVersion ?? ""),
      messageTypeHandled: message.type,
      reason: "legacy_scanner_unavailable",
      diagnostics: {
        handler_registered: true,
        legacy_scanner_invocation_attempted: "no",
        legacy_scanner_wrapper: "legacyVerifiedProfileScanner22C11B",
        run_id: runId,
        expected_profile_url: expectedProfileUrl,
        expected_profile_video_count: expectedProfileVideoCount,
        mode: message.mode ?? "verify_only",
        coverage_mode: message.coverage_mode ?? "refresh_all"
      }
    };
  }
  const scan = await legacyVerifiedProfileScanner22C11B({ max_rounds: maxRounds, scan_run_id: runId, expected_profile_video_count: expectedProfileVideoCount, max_total_time_ms: expectedProfileVideoCount != null ? 120_000 : 60_000 });
  const completedAt = new Date().toISOString();
  const rejectedCount = scan.status === "success" ? Number(scan.diagnostics.rejected_count ?? 0) : 0;
  const resolver = resolveModalProfileVideoTargets22C11B(scan.cards, expectedProfileVideoCount);
  const mergedCards = mergeModalWholeProfileCards22C11B(scan.cards, resolver.targets);
  const finalAwemeIds = mergedCards.cards.map((card) => card.aweme_id);
  const finalFoundCount = mergedCards.cards.length;
  const missingExpectedCount = expectedProfileVideoCount != null
    ? Math.max(expectedProfileVideoCount - finalFoundCount, 0)
    : null;
  const partialScan = missingExpectedCount != null ? missingExpectedCount > 0 : false;
  const success = scan.status === "success" && finalFoundCount > 0;
  return {
    ok: success,
    traceVersion: String(message.traceVersion ?? ""),
    messageTypeHandled: message.type,
    reason: success ? null : scan.reason ?? "legacy_scanner_zero_verified_targets",
    schema_version: "phase17s_dry_run_reuse_verified_targets",
    verified_targets: finalAwemeIds,
    verified_target_details: mergedCards.cards,
    scan_rounds: scan.status === "success" ? scan.diagnostics.rounds : 0,
    stop_reason: scan.status === "success" ? scan.diagnostics.stop_reason : null,
    total_candidates: finalFoundCount + rejectedCount,
    rejected_count: rejectedCount,
    rejected_reasons: scan.status === "success" ? (scan.diagnostics.candidate_classifications as Array<{ status?: string; reason?: unknown }> | undefined)?.filter((candidate) => candidate.status === "rejected" && candidate.reason != null).map((candidate) => String(candidate.reason)) ?? [] : [],
    cards: mergedCards.cards,
    total_cards_found: finalFoundCount,
    scanner_started: true,
    scanner_invocation_mode: "content_script_message",
    diagnostics: {
      ...scan.diagnostics,
      ...resolver.diagnostics,
      ...mergedCards.diagnostics,
      final_found_count: finalFoundCount,
      missing_expected_count: missingExpectedCount,
      final_aweme_ids: finalAwemeIds,
      partial_scan: partialScan,
      handler_registered: true,
      legacy_scanner_invocation_attempted: "yes",
      legacy_scanner_function: "resolveModalProfileVideoTargets22C11B",
      canonical_scanner_function: "resolveModalProfileVideoTargets22C11B",
      legacy_scanner_wrapper: "legacyVerifiedProfileScanner22C11B",
      legacy_scanner_started_at: startedAt,
      legacy_scanner_invocation_result: success ? "success" : "failed",
      legacy_scanner_completed_at: completedAt,
      legacy_scanner_scan_rounds: scan.status === "success" ? scan.diagnostics.rounds : 0,
      legacy_scanner_stop_reason: scan.status === "success" ? scan.diagnostics.stop_reason : null,
      legacy_scanner_total_candidates: scan.cards.length + rejectedCount,
      legacy_scanner_verified_target_count: scan.cards.length,
      canonical_scanner_verified_target_count: finalFoundCount,
      legacy_scanner_rejected_count: rejectedCount,
      run_id: runId,
      expected_profile_url: expectedProfileUrl,
      expected_profile_video_count: expectedProfileVideoCount,
      canonical_scanner_max_rounds: maxRounds,
      mode: message.mode ?? "verify_only",
      coverage_mode: message.coverage_mode ?? "refresh_all",
      scanner_invocation_mode: "content_script_message"
    }
  };
}

function serializeModalTestScanError(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

export function getDouyinPageViewport(): DouyinPageViewport {
  const url = window.location.href;
  return {
    width: window.innerWidth,
    height: window.innerHeight,
    visual_width: window.visualViewport?.width ?? null,
    visual_height: window.visualViewport?.height ?? null,
    device_pixel_ratio: window.devicePixelRatio,
    url,
    modal_id: new URL(url).searchParams.get("modal_id") ?? null,
    source: "content_script"
  };
}

export function detectDouyinPageContext(): DouyinPageContext {
  const href = window.location.href;
  let parsed: URL;
  try {
    parsed = new URL(href);
  } catch {
    const viewport = getDouyinPageViewport();
    return {
      success: true,
      url: href,
      host: "",
      page_type: "unknown",
      is_profile_page: false,
      has_modal: false,
      modal_id: null,
      user_profile_path: null,
      viewport
    };
  }

  const modalId = parsed.searchParams.get("modal_id")?.trim() || null;
  const userProfilePath = /^\/user\/[^/?#]+/.test(parsed.pathname) ? parsed.pathname : null;
  const videoMatch = parsed.pathname.match(/^\/video\/([^/?#]+)/);
  const videoId = videoMatch?.[1]?.trim() || null;
  const pageType = userProfilePath && modalId ? "modal" : userProfilePath ? "profile" : videoId ? "video" : "unknown";

  const profileUrl = userProfilePath ? `${parsed.origin}${userProfilePath}` : null;
  return {
    success: true,
    url: parsed.toString(),
    current_url: parsed.toString(),
    host: parsed.host,
    page_type: pageType,
    detector_status: "ready",
    is_profile_page: pageType === "profile",
    has_modal: pageType === "modal" || pageType === "video",
    modal_id: pageType === "video" ? videoId : modalId,
    profile_url: profileUrl,
    user_profile_path: userProfilePath,
    viewport: getDouyinPageViewport()
  };
}

export function probeDouyinProfileVideoEvidence(): DouyinProfileVideoEvidenceProbe {
  const pageContext = detectDouyinPageContext();
  const profileDomProbe = buildDouyinProfileDomProbe();
  const bodyText = document.body?.innerText?.replace(/\s+/g, " ").trim() ?? "";
  const visible = (element: Element): boolean => {
    if (!(element instanceof HTMLElement)) return false;
    const style = window.getComputedStyle(element);
    const rect = element.getBoundingClientRect();
    return style.display !== "none" && style.visibility !== "hidden" && rect.width > 0 && rect.height > 0;
  };
  const profileGridCandidateSelectors = [
    '[data-e2e*="user-post"]',
    '[data-e2e*="post-item"]',
    '[data-e2e*="user-work"]',
    '[data-e2e*="work-item"]',
    'a[href*="/video/"]',
    'a[href*="modal_id="]',
    'a[href*="aweme_id="]',
    'li article',
    'main li',
    'main article'
  ];
  const gridContainerSelectors = [
    '[data-e2e*="user-post"]',
    '[data-e2e*="user-work"]',
    '[class*="post"]',
    '[class*="work"]',
    '[role="main"] main'
  ];
  const profileSectionSelectors = [
    'main',
    '[data-e2e*="user-detail"]',
    '[data-e2e*="user-info"]',
    '[class*="user-info"]',
    '[class*="profile"]'
  ];
  const profileTabSelectors = [
    '[role="tab"]',
    '[data-e2e*="user-tab"]',
    '[data-e2e*="post-tab"]',
    'button[aria-selected]',
    'button[data-e2e*="tab"]'
  ];
  const profileTitlePresent = Array.from(document.querySelectorAll("h1, h2, [data-e2e*='user-title'], [data-e2e*='nickname']")).some((element) => visible(element));
  const profileGridCandidateCount = Array.from(new Set(profileGridCandidateSelectors.flatMap((selector) => Array.from(document.querySelectorAll(selector))))).filter((element) => visible(element)).length;
  const videoAwemeCandidateCount = Array.from(document.querySelectorAll('a[href*="/video/"], a[href*="modal_id="], a[href*="aweme_id="]')).filter((element) => visible(element)).length;
  const visibleLinkCount = Array.from(document.querySelectorAll("a[href]"))
    .filter((element) => visible(element) && /\/video\/|modal_id=|aweme_id=/.test((element as HTMLAnchorElement).href ?? ""))
    .length;
  const gridContainerCount = Array.from(new Set(gridContainerSelectors.flatMap((selector) => Array.from(document.querySelectorAll(selector))))).filter((element) => visible(element)).length;
  const profileSectionCount = Array.from(new Set(profileSectionSelectors.flatMap((selector) => Array.from(document.querySelectorAll(selector))))).filter((element) => visible(element)).length;
  const profileTabCount = Array.from(new Set(profileTabSelectors.flatMap((selector) => Array.from(document.querySelectorAll(selector))))).filter((element) => visible(element)).length;
  return {
    current_url: pageContext.current_url ?? window.location.href,
    page_type: pageContext.page_type,
    modal_id_present: Boolean(pageContext.modal_id),
    document_ready_state: document.readyState,
    profile_grid_candidate_count: profileGridCandidateCount,
    video_aweme_candidate_count: videoAwemeCandidateCount,
    visible_link_count: visibleLinkCount,
    grid_container_count: gridContainerCount,
    profile_section_count: profileSectionCount,
    profile_tab_count: profileTabCount,
    profile_title_present: profileTitlePresent,
    app_root_present: Boolean(document.querySelector("#root, #app, [id*='root'], [data-e2e*='app']")),
    body_text_sample: bodyText.slice(0, 500),
    diagnostics: {
      profile_dom_probe: profileDomProbe,
      profile_dom_probe_status: profileDomProbe.probeError ? "error" : "ok",
      profile_grid_ready: profileDomProbe.profileGridFound || profileDomProbe.videoAnchorCount > 0 || profileDomProbe.modalIdLinkCount > 0 || profileDomProbe.awemeIdCount > 0,
      profile_grid_selector: profileDomProbe.profileGridSelector,
      profile_grid_selector_hits: profileDomProbe.gridCardSelectorHits,
      video_anchor_count: profileDomProbe.videoAnchorCount,
      modal_id_link_count: profileDomProbe.modalIdLinkCount,
      aweme_id_count: profileDomProbe.awemeIdCount,
      grid_card_candidate_count: profileDomProbe.gridCardCandidateCount,
      scroll_container_found: profileDomProbe.scrollContainerFound,
      scroll_container_selector: profileDomProbe.scrollContainerSelector,
      detector_page_type: pageContext.page_type,
      detector_modal_id: pageContext.modal_id,
      detector_profile_url: pageContext.profile_url ?? null,
      scroll_y: window.scrollY,
      document_title: document.title,
      ready_state: document.readyState,
      profile_grid_candidate_count: profileGridCandidateCount,
      video_aweme_candidate_count: videoAwemeCandidateCount,
      visible_link_count: visibleLinkCount,
      grid_container_count: gridContainerCount,
      profile_section_count: profileSectionCount,
      profile_tab_count: profileTabCount,
      profile_title_present: profileTitlePresent,
      app_root_present: Boolean(document.querySelector("#root, #app, [id*='root'], [data-e2e*='app']"))
    }
  };
}

async function closeDouyinModalIfPresent(): Promise<{ ok: boolean; attempted: boolean; modal_still_visible: boolean; current_url: string | null; diagnostics: Record<string, unknown> }> {
  const diagnostics: Record<string, unknown> = {
    before_url: window.location.href,
    before_title: document.title,
    strategies_attempted: []
  };
  const parsed = (() => {
    try {
      return new URL(window.location.href);
    } catch {
      return null;
    }
  })();
  const modalIdBefore = parsed?.searchParams.get("modal_id") ?? null;
  if (!modalIdBefore) {
    return { ok: true, attempted: false, modal_still_visible: false, current_url: window.location.href, diagnostics: { ...diagnostics, skipped: "no_modal_id" } };
  }

  const closeSelectors = [
    '[aria-label*="关闭"]',
    '[aria-label*="close" i]',
    'button[aria-label*="关闭"]',
    'button[aria-label*="close" i]',
    '[data-e2e="close-button"]',
    '[data-e2e="modal-close"]',
    '.xgplayer-icon-close'
  ];

  const tryClickClose = (): boolean => {
    for (const selector of closeSelectors) {
      const element = document.querySelector<HTMLElement>(selector);
      if (element && element.offsetParent !== null) {
        element.click();
        (diagnostics.strategies_attempted as string[]).push(`click:${selector}`);
        return true;
      }
    }
    return false;
  };

  const closeClicked = tryClickClose();
  if (!closeClicked) {
    window.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
    document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
    (diagnostics.strategies_attempted as string[]).push("escape");
  }

  await new Promise((resolve) => window.setTimeout(resolve, 800));
  const afterContext = detectDouyinPageContext();
  const modalStillVisible = Boolean(afterContext.modal_id);
  return {
    ok: !modalStillVisible,
    attempted: true,
    modal_still_visible: modalStillVisible,
    current_url: afterContext.current_url ?? window.location.href,
    diagnostics: {
      ...diagnostics,
      modal_id_before: modalIdBefore,
      modal_id_after: afterContext.modal_id,
      page_type_after: afterContext.page_type,
      current_url_after: afterContext.current_url ?? window.location.href,
      close_clicked: closeClicked
    }
  };
}

function initializePassiveNetworkProbe22C12AR2(): void {
  if (passiveNetworkProbeInitialized22C12A) return;
  passiveNetworkProbeInitialized22C12A = true;
  passiveNetworkProbeSummary22C12A = markPassiveNetworkProbeListenerReady22C12A(passiveNetworkProbeSummary22C12A);
  schedulePassiveNetworkProbePersistence22C12A();
  if (!isPassiveNetworkProbeProfilePage22C12A()) {
    passiveNetworkProbeSummary22C12A = markPassiveNetworkProbeError22C12A(passiveNetworkProbeSummary22C12A, "not_douyin_profile_page");
    schedulePassiveNetworkProbePersistence22C12A();
    return;
  }
  injectPageNetworkHook();
}

function isPassiveNetworkProbeProfilePage22C12A(): boolean {
  return window.location.host === "www.douyin.com" && /^\/user\/[^/?#]+/i.test(window.location.pathname);
}

function injectPageNetworkHook(): void {
  passiveNetworkProbeSummary22C12A = markPassiveNetworkProbeInjectionAttempted22C12A(passiveNetworkProbeSummary22C12A);
  schedulePassiveNetworkProbePersistence22C12A();
  const script = document.createElement("script");
  script.src = chrome.runtime.getURL("pageNetworkHook.js");
  script.onload = () => {
    passiveNetworkProbeSummary22C12A = markPassiveNetworkProbeInjected22C12A(passiveNetworkProbeSummary22C12A);
    schedulePassiveNetworkProbePersistence22C12A();
    script.remove();
  };
  script.onerror = () => {
    passiveNetworkProbeSummary22C12A = markPassiveNetworkProbeError22C12A(passiveNetworkProbeSummary22C12A, "page_script_injection_failed");
    schedulePassiveNetworkProbePersistence22C12A();
    script.remove();
  };
  (document.documentElement || document.head).appendChild(script);
  if (passiveNetworkProbeReadyTimeout22C12A) clearTimeout(passiveNetworkProbeReadyTimeout22C12A);
  passiveNetworkProbeReadyTimeout22C12A = setTimeout(() => {
    passiveNetworkProbeReadyTimeout22C12A = null;
    if (passiveNetworkProbeSummary22C12A.network_probe_bridge_ready === "yes") return;
    passiveNetworkProbeSummary22C12A = markPassiveNetworkProbeError22C12A(passiveNetworkProbeSummary22C12A, "page_ready_event_timeout");
    schedulePassiveNetworkProbePersistence22C12A();
  }, 5_000);
}

function recordPassiveNetworkProbeBatch22C12A(batch: PassiveNetworkProbeBatchMessage22C12A): void {
  const now = new Date().toISOString();
  const snapshotProfileUrl = canonicalProfileUrl22C12B(window.location.href);
  const endpointKind = classifyPassiveNetworkEndpointKind22C12A(batch.urlPath);
  const targetStore = passiveNetworkProbeTargetsByKind22C12A[endpointKind];
  const sizeBefore = targetStore.size;
  for (const target of batch.targets) {
    const storedTarget = buildPassiveNetworkStoredTarget22C12A({
      target,
      profileUrl: snapshotProfileUrl,
      urlPath: batch.urlPath,
      capturedAt: now
    });
    targetStore.set(storedTarget.aweme_id, storedTarget);
  }
  const newAwemeCount = Math.max(targetStore.size - sizeBefore, 0);
  getLiveNetworkStreamRuntime22C12D().emit(batch, endpointKind, batch.urlPath, now, newAwemeCount);
  recordPaginationPostBatch22C12C(batch, endpointKind, now);
  recordActivationPostRequest22C12E(batch, endpointKind, now);
  if (endpointKind === "profile_post") {
    passiveNetworkProbeProfilePostBatchCount22C12BR2 += 1;
    passiveNetworkProbeProfilePostLastBatchAt22C12BR2 = now;
    if (targetStore.size > sizeBefore) passiveNetworkProbeProfilePostLastNewIdAt22C12BR2 = now;
    if (batch.cursor != null && !passiveNetworkProbePostCursorSamples22C12A.includes(batch.cursor)) {
      passiveNetworkProbePostCursorSamples22C12A.push(batch.cursor);
      while (passiveNetworkProbePostCursorSamples22C12A.length > 8) passiveNetworkProbePostCursorSamples22C12A.shift();
    }
    if (batch.cursorFields) {
      passiveNetworkProbePostCursorFieldSamples22C12BR2.push(batch.cursorFields);
      while (passiveNetworkProbePostCursorFieldSamples22C12BR2.length > 8) passiveNetworkProbePostCursorFieldSamples22C12BR2.shift();
    }
    passiveNetworkProbePostHasMoreState22C12A = batch.hasMore;
  }
  passiveNetworkProbeSummary22C12A = mergePassiveNetworkProbeBatch22C12A(passiveNetworkProbeSummary22C12A, batch, now);
  passiveNetworkProbeSummary22C12A = reconcilePassiveNetworkProbeSummary22C12A(passiveNetworkProbeSummary22C12A);
  schedulePassiveNetworkProbePersistence22C12A();
}

function reconcilePassiveNetworkProbeSummary22C12A(current: PassiveNetworkProbeSummary22C12A): PassiveNetworkProbeSummary22C12A {
  const profilePostTargets = Array.from(passiveNetworkProbeTargetsByKind22C12A.profile_post.values());
  const favoriteTargets = Array.from(passiveNetworkProbeTargetsByKind22C12A.favorite.values());
  const otherTargets = Array.from(passiveNetworkProbeTargetsByKind22C12A.other_aweme_list.values());
  const uniqueIds = new Set<string>();
  for (const target of [...profilePostTargets, ...favoriteTargets, ...otherTargets]) uniqueIds.add(target.aweme_id);
  return {
    ...current,
    network_probe_unique_aweme_count: uniqueIds.size,
    network_profile_post_unique_count: profilePostTargets.length,
    network_favorite_unique_count: favoriteTargets.length,
    network_other_aweme_unique_count: otherTargets.length,
    network_excluded_favorite_count: favoriteTargets.length,
    network_excluded_other_count: otherTargets.length,
    network_probe_first_10_aweme_ids: Array.from(uniqueIds).slice(0, 10),
    network_probe_last_10_aweme_ids: Array.from(uniqueIds).slice(-10)
  };
}

function getPassiveNetworkProbeSnapshot22C12A(): {
  profilePostTargets: PassiveNetworkProbeStoredTarget22C12A[];
  favoriteTargets: PassiveNetworkProbeStoredTarget22C12A[];
  otherTargets: PassiveNetworkProbeStoredTarget22C12A[];
  postCursorValuesSample: Array<string | number>;
  postCursorFieldSamples: PassiveNetworkProbeCursorFields22C12BR2[];
  postHasMoreState: boolean | null;
  profilePostBatchCount: number;
  profilePostLastBatchAt: string | null;
  profilePostLastNewIdAt: string | null;
} {
  const orderTargets = (targets: Iterable<PassiveNetworkProbeStoredTarget22C12A>) =>
    Array.from(targets).sort((left, right) => {
      if (left.captured_at === right.captured_at) return left.aweme_id.localeCompare(right.aweme_id);
      return left.captured_at.localeCompare(right.captured_at);
    });
  return {
    profilePostTargets: orderTargets(passiveNetworkProbeTargetsByKind22C12A.profile_post.values()),
    favoriteTargets: orderTargets(passiveNetworkProbeTargetsByKind22C12A.favorite.values()),
    otherTargets: orderTargets(passiveNetworkProbeTargetsByKind22C12A.other_aweme_list.values()),
    postCursorValuesSample: [...passiveNetworkProbePostCursorSamples22C12A],
    postCursorFieldSamples: [...passiveNetworkProbePostCursorFieldSamples22C12BR2],
    postHasMoreState: passiveNetworkProbePostHasMoreState22C12A,
    profilePostBatchCount: passiveNetworkProbeProfilePostBatchCount22C12BR2,
    profilePostLastBatchAt: passiveNetworkProbeProfilePostLastBatchAt22C12BR2,
    profilePostLastNewIdAt: passiveNetworkProbeProfilePostLastNewIdAt22C12BR2
  };
}

function schedulePassiveNetworkProbePersistence22C12A(): void {
  if (passiveNetworkProbePersistTimer22C12A) return;
  passiveNetworkProbePersistTimer22C12A = setTimeout(() => {
    passiveNetworkProbePersistTimer22C12A = null;
    void persistPassiveNetworkProbeDiagnostics22C12A();
  }, 750);
}

function passiveProbeAuthorityDiagnosticsRecord22C14C(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== "object") return {};
  const record = value as Record<string, unknown>;
  return record.diagnostics_channel === "scan_authority_diagnostics" ? record : {};
}

function passiveProbeStagePriority22C14C(stage: unknown): number {
  const value = typeof stage === "string" ? stage : "";
  if (/finished|success|failed|terminal|complete/.test(value)) return 100;
  if (/finaliz/.test(value)) return 90;
  if (/running|checkpoint|scan/.test(value)) return 50;
  if (/start|accepted/.test(value)) return 30;
  return 10;
}

function passiveProbeStaleWriteRejection22C14C(state: WholeProfileHarvestState, incoming: { at: string; scanRunId: string | null; stage: string; source: string }): Record<string, unknown> | null {
  const authority = {
    ...passiveProbeAuthorityDiagnosticsRecord22C14C(state.profile_scan.diagnostics),
    ...passiveProbeAuthorityDiagnosticsRecord22C14C(state.verify.diagnostics)
  };
  const currentRunId = typeof authority.scan_run_id === "string" ? authority.scan_run_id : state.scan_job.scan_job_id ?? state.run_id ?? null;
  const currentUpdatedAt = typeof state.updated_at === "string" ? state.updated_at : null;
  const currentStage = typeof authority.scan_stage_current === "string" ? authority.scan_stage_current : typeof state.phase === "string" ? state.phase : null;
  const incomingRunIsOlder = Boolean(incoming.scanRunId && currentRunId && incoming.scanRunId !== currentRunId);
  const incomingUpdatedAtIsOlder = Boolean(currentUpdatedAt && incoming.at < currentUpdatedAt);
  const incomingStageIsLowerThanTerminal = Boolean(currentStage && passiveProbeStagePriority22C14C(currentStage) >= 90 && passiveProbeStagePriority22C14C(incoming.stage) < passiveProbeStagePriority22C14C(currentStage));
  if (!incomingRunIsOlder && !incomingUpdatedAtIsOlder && !incomingStageIsLowerThanTerminal) return null;
  return {
    diagnostics_channel: "runtime_debug_diagnostics",
    diagnostics_channel_isolated: "yes",
    stale_update_rejected: "yes",
    stale_update_source: incoming.source,
    stale_update_run_id: incoming.scanRunId ?? "none",
    stale_update_stage: incoming.stage,
    stale_update_current_run_id: currentRunId ?? "none",
    stale_update_current_stage: currentStage ?? "none",
    stale_update_current_updated_at: currentUpdatedAt ?? "none",
    stale_update_incoming_updated_at: incoming.at,
    stale_update_reason: incomingRunIsOlder ? "older_scan_run_id" : incomingUpdatedAtIsOlder ? "older_updated_at" : "lower_priority_than_terminal_stage"
  };
}

async function persistPassiveNetworkProbeDiagnostics22C12A(): Promise<void> {
  const at = new Date().toISOString();
  const summary = {
    ...passiveNetworkProbeSummary22C12A,
    scan_debug_instrumentation_enabled: ENABLE_SCAN_DEBUG_INSTRUMENTATION ? "yes" : "no",
    scan_debug_instrumentation_installers_ran: [...scanDebugInstrumentationInstallersRan],
    ...(ENABLE_SCAN_DEBUG_INSTRUMENTATION ? getPaginationReverseEngineeringDiagnostics22C12C() : {}),
    ...(ENABLE_SCAN_DEBUG_INSTRUMENTATION ? getActivationTruthProbeDiagnostics22C12E() : {}),
    ...(ENABLE_SCAN_DEBUG_INSTRUMENTATION ? getManualPaginationTruthDiagnostics22C13A() : {}),
    ...getLiveNetworkStreamDiagnostics22C12D(),
    diagnostics_channel: "runtime_debug_diagnostics",
    diagnostics_channel_isolated: "yes",
    diagnostics_write_source: "contentScript.passive_network_probe",
    // 22C-14I build identity diagnostics are generated at build time so content-script probe writes can prove Chrome injected the current bundled dist.
    extension_runtime_build_id: EXTENSION_RUNTIME_BUILD_ID,
    content_script_runtime_build_id: CONTENT_SCRIPT_RUNTIME_BUILD_ID,
    runtime_build_id_consistent: EXTENSION_RUNTIME_BUILD_ID === CONTENT_SCRIPT_RUNTIME_BUILD_ID ? "yes" : "no",
    extension_build_timestamp: EXTENSION_BUILD_TIMESTAMP,
    network_probe_runtime_version: NETWORK_PROBE_RUNTIME_BUILD_ID_22C12AR3,
    network_probe_bridge_ready_display: passiveNetworkProbeSummary22C12A.network_probe_bridge_ready,
    network_probe_endpoint_samples_display: passiveNetworkProbeSummary22C12A.network_probe_endpoint_samples.join(", "),
    network_probe_first_10_aweme_ids_display: passiveNetworkProbeSummary22C12A.network_probe_first_10_aweme_ids.join(", "),
    network_probe_last_10_aweme_ids_display: passiveNetworkProbeSummary22C12A.network_probe_last_10_aweme_ids.join(", "),
    network_probe_last_error: passiveNetworkProbeSummary22C12A.network_probe_last_error ?? "none"
  };
  const stored = await chrome.storage.local
    .get(WHOLE_PROFILE_HARVEST_STATE_KEY)
    .catch(() => ({ [WHOLE_PROFILE_HARVEST_STATE_KEY]: undefined } as Record<string, WholeProfileHarvestState | undefined>));
  const existing = (stored as Record<string, WholeProfileHarvestState | undefined>)[WHOLE_PROFILE_HARVEST_STATE_KEY];
  const state = existing ?? createWholeProfileHarvestIdleState(at);
  const requestSummary = state.debug.last_request_summary && typeof state.debug.last_request_summary === "object"
    ? state.debug.last_request_summary as Record<string, unknown>
    : {};
  const responseSummary = state.debug.last_response_summary && typeof state.debug.last_response_summary === "object"
    ? state.debug.last_response_summary as Record<string, unknown>
    : {};
  const rejection = passiveProbeStaleWriteRejection22C14C(state, {
    at,
    scanRunId: typeof (summary as Record<string, unknown>).scan_run_id === "string" ? (summary as Record<string, unknown>).scan_run_id as string : null,
    stage: "runtime_debug_probe",
    source: "contentScript.passive_network_probe"
  });
  const debugPayload = rejection ?? summary;
  await chrome.storage.local.set({
    [WHOLE_PROFILE_HARVEST_STATE_KEY]: {
      ...state,
      updated_at: rejection ? state.updated_at : at,
      profile_scan: state.profile_scan,
      verify: state.verify,
      debug: {
        ...state.debug,
        last_request_summary: {
          ...requestSummary,
          ...debugPayload
        },
        last_response_summary: {
          ...responseSummary,
          ...debugPayload
        }
      }
    }
  });
}

async function loadRightRailCalibration(): Promise<RightRailCalibration | null> {
  const stored = await chrome.storage.local.get(RIGHT_RAIL_CALIBRATION_KEY);
  const value = stored[RIGHT_RAIL_CALIBRATION_KEY];
  return isRightRailCalibration(value) ? value : null;
}

async function clearRightRailCalibration(): Promise<void> {
  await chrome.storage.local.remove(RIGHT_RAIL_CALIBRATION_KEY);
}

async function saveRightRailCalibration(calibration: RightRailCalibration): Promise<void> {
  await chrome.storage.local.set({ [RIGHT_RAIL_CALIBRATION_KEY]: calibration });
}

type ActiveCalibrationMode = {
  overlay: HTMLDivElement;
  panel: HTMLDivElement;
  cleanup: () => void;
  clearPrompt: () => void;
  pendingMetricStep: string | null;
  completed: boolean;
};

let activeCalibrationMode: ActiveCalibrationMode | null = null;

function ensureCalibrationModeStopped(): { activeBeforeStop: boolean; stopped: boolean } {
  const activeBeforeStop = activeCalibrationMode != null;
  if (activeCalibrationMode) {
    activeCalibrationMode.completed = true;
    activeCalibrationMode.pendingMetricStep = null;
    activeCalibrationMode.clearPrompt();
    activeCalibrationMode.cleanup();
    activeCalibrationMode = null;
  }
  return { activeBeforeStop, stopped: activeCalibrationMode == null };
}

async function startRightRailCalibration(): Promise<RightRailCalibration> {
  ensureCalibrationModeStopped();
  const metrics = ["like_count", "comment_count", "favorite_count", "share_count"] as const;
  return new Promise<RightRailCalibration>((resolve, reject) => {
    const overlay = document.createElement("div");
    overlay.style.position = "fixed";
    overlay.style.inset = "0";
    overlay.style.zIndex = "2147483647";
    overlay.style.background = "rgba(0,0,0,0.18)";
    overlay.style.cursor = "crosshair";
    overlay.style.userSelect = "none";
    const panel = document.createElement("div");
    panel.style.position = "fixed";
    panel.style.top = "16px";
    panel.style.right = "16px";
    panel.style.maxWidth = "280px";
    panel.style.padding = "12px";
    panel.style.borderRadius = "6px";
    panel.style.background = "rgba(20,20,20,0.92)";
    panel.style.color = "#fff";
    panel.style.font = "12px/1.4 sans-serif";
    overlay.appendChild(panel);
    let index = 0;
    const points: RightRailCalibration["points"] = {
      like_count: { x: 0, y: 0, x_ratio: 0, y_ratio: 0 },
      comment_count: { x: 0, y: 0, x_ratio: 0, y_ratio: 0 },
      favorite_count: { x: 0, y: 0, x_ratio: 0, y_ratio: 0 },
      share_count: { x: 0, y: 0, x_ratio: 0, y_ratio: 0 }
    };
    let completed = false;
    let lastRecordedAt = 0;
    const clearPrompt = (): void => {
      panel.textContent = "";
    };
    const cleanup = (): void => {
      overlay.remove();
      document.removeEventListener("pointerdown", handleCalibrationPointerDown, true);
      document.removeEventListener("mousedown", handleCalibrationMouseDown, true);
      document.removeEventListener("click", handleCalibrationClick, true);
      window.removeEventListener("keydown", handleKeydown, true);
      if (activeCalibrationMode?.overlay === overlay) activeCalibrationMode = null;
    };
    const render = (): void => {
      const metric = metrics[index];
      if (!metric) {
        panel.textContent = "Calibration complete.";
        return;
      }
      const labels: Record<(typeof metrics)[number], string> = {
        like_count: "LIKE count",
        comment_count: "COMMENT count",
        favorite_count: "FAVORITE count",
        share_count: "SHARE count"
      };
      panel.textContent = `Step ${index + 1}/${metrics.length}: Click ${labels[metric]}. Calibration is four points only: like, comment, favorite, share. Press Escape to cancel.`;
    };
    const showToast = (message: string): void => {
      const toast = document.createElement("div");
      toast.textContent = message;
      toast.style.position = "fixed";
      toast.style.top = "16px";
      toast.style.left = "50%";
      toast.style.transform = "translateX(-50%)";
      toast.style.zIndex = "2147483647";
      toast.style.padding = "10px 12px";
      toast.style.borderRadius = "6px";
      toast.style.background = "rgba(20,20,20,0.92)";
      toast.style.color = "#fff";
      toast.style.font = "12px/1.4 sans-serif";
      document.documentElement.appendChild(toast);
      window.setTimeout(() => toast.remove(), 2200);
    };
    const finish = async (): Promise<void> => {
      if (completed) return;
      completed = true;
      const viewport = getDouyinPageViewport();
      const calibration: RightRailCalibration = {
        version: "phase13h_four_point_calibration",
        viewport_width: viewport.width,
        viewport_height: viewport.height,
        viewport_source: viewport.source,
        points,
        created_at: new Date().toISOString(),
        profile_url_host: window.location.host
      };
      try {
        await saveRightRailCalibration(calibration);
        panel.textContent = "Calibration saved.";
        showToast("Calibration saved: 4/4 points.");
        completed = true;
        if (activeCalibrationMode?.overlay === overlay) {
          activeCalibrationMode.completed = true;
          activeCalibrationMode.pendingMetricStep = null;
          activeCalibrationMode.clearPrompt();
        }
        cleanup();
        resolve(calibration);
      } catch (error) {
        completed = false;
        panel.textContent = `calibration_save_failed: ${error instanceof Error ? error.message : String(error)}`;
        reject(new Error(`calibration_save_failed: ${error instanceof Error ? error.message : String(error)}`));
      }
    };
    const handleKeydown = (event: KeyboardEvent): void => {
      if (event.key === "Escape") {
        completed = true;
        cleanup();
        reject(new Error("right_rail_calibration_cancelled"));
      }
    };
    const recordCalibrationPoint = (event: MouseEvent | PointerEvent): void => {
      event.preventDefault();
      event.stopPropagation();
      const now = Date.now();
      if (completed || now - lastRecordedAt < 250) return;
      lastRecordedAt = now;
      const metric = metrics[index];
      if (!metric) return;
      if (activeCalibrationMode?.overlay === overlay) activeCalibrationMode.pendingMetricStep = metric;
      const viewport = getDouyinPageViewport();
      points[metric] = {
        x: event.clientX,
        y: event.clientY,
        x_ratio: event.clientX / Math.max(1, viewport.width),
        y_ratio: event.clientY / Math.max(1, viewport.height)
      };
      index += 1;
      panel.textContent = `Captured ${metric} at ${event.clientX},${event.clientY}`;
      if (index >= metrics.length) {
        void finish();
        return;
      }
      window.setTimeout(render, 350);
    };
    const handleCalibrationPointerDown = (event: PointerEvent): void => recordCalibrationPoint(event);
    const handleCalibrationMouseDown = (event: MouseEvent): void => recordCalibrationPoint(event);
    const handleCalibrationClick = (event: MouseEvent): void => recordCalibrationPoint(event);
    document.addEventListener("pointerdown", handleCalibrationPointerDown, true);
    document.addEventListener("mousedown", handleCalibrationMouseDown, true);
    document.addEventListener("click", handleCalibrationClick, true);
    overlay.addEventListener("contextmenu", (event) => {
      event.preventDefault();
      event.stopPropagation();
    });
    window.addEventListener("keydown", handleKeydown, true);
    activeCalibrationMode = { overlay, panel, cleanup, clearPrompt, pendingMetricStep: metrics[index] ?? null, completed };
    render();
    document.documentElement.appendChild(overlay);
  });
}

function isRightRailCalibration(value: unknown): value is RightRailCalibration {
  const version = (value as { version?: unknown } | null)?.version;
  return Boolean(
    value &&
      typeof value === "object" &&
      (version === "phase10a" || version === "phase11g_calibrated_points_with_next" || version === "phase12a_calibrated_five_point_workflow" || version === "calibrated_four_point_workflow" || version === "phase13h_four_point_calibration") &&
      (value as { points?: unknown }).points &&
      typeof (value as { points?: unknown }).points === "object"
  );
}

window.addEventListener("beforeunload", () => {
  void flushBeforeUnload();
});

async function handleCaptureMessage(message: ExtensionMessage): Promise<NonNullable<ExtensionMessageResponse["payload"]>> {
  const page = detectPageFromDocument(document, window.location.href);
  const context = buildCaptureContext(page, null, {
    tab_id: message.tab_id ?? null,
    page_url: window.location.href,
    captured_at: new Date().toISOString()
  });
  const networkItems = mergeNetworkCacheItems(filterNetworkItemsForContext([...bridgedNetworkItems, ...readDouyinNetworkCache(document, "content_script_cache")], context));
  const discoveries = discoverGridVideos(document).map((item) => ({
    aweme_id: item.aweme_id,
    source_url: item.source_url,
    share_url: item.share_url
  }));
  const detailHydration = await hydrateDetailEvidenceForDiscoveries(discoveries);
  return buildCapturePayload(document, window.location.href, networkItems, context, detailHydration.items, {
    detail_hydrate_attempted_count: detailHydration.stats.detail_hydrate_attempted_count,
    detail_hydrate_success_count: detailHydration.stats.detail_hydrate_success_count,
    detail_hydrate_failed_count: detailHydration.stats.detail_hydrate_failed_count,
    detail_hydrate_timeout_count: detailHydration.stats.detail_hydrate_timeout_count,
    raw_detail_aweme_attached_count: detailHydration.stats.raw_detail_aweme_attached_count
  });
}

function mergeNetworkCacheItems(items: NetworkVideoMetadata[]): NetworkVideoMetadata[] {
  const byId = new Map<string, NetworkVideoMetadata>();
  for (const item of items) {
    const awemeId = item.aweme_id?.trim();
    if (!awemeId) continue;
    const previous = byId.get(awemeId);
    byId.set(awemeId, {
      ...previous,
      ...item,
      aweme_id: awemeId,
      url_list: [...new Set([...(item.url_list ?? []), ...(previous?.url_list ?? [])])],
      context: item.context ?? previous?.context ?? null
    });
  }
  return Array.from(byId.values()).map((item) => ({ ...item, url_list: [...(item.url_list ?? [])] })).slice(0, 240);
}

async function flushBeforeUnload(): Promise<void> {
  const runtime = await loadRuntimeV2();
  if (runtime.status === "idle") return;
  try {
    await flushHarvestV2();
  } catch {
    // Best effort only.
  }
}

async function postJson(baseUrl: string, path: string, payload: unknown, options?: { keepalive?: boolean }): Promise<Record<string, unknown> | null> {
  const flushUrl = `${baseUrl.replace(/\/+$/, "")}${path.startsWith("/") ? path : `/${path}`}`;
  const response = (await chrome.runtime.sendMessage({
    type: "REUP_DOUYIN_POST_BACKEND",
    request: {
      base_url: baseUrl,
      path,
      payload,
      keepalive: options?.keepalive ?? false
    }
  } satisfies ExtensionMessage)) as ExtensionMessageResponse;
  const backendPost = (response.backend_post ?? undefined) as ExtensionBackendPostResponse | undefined;
  if (!response.ok || !backendPost?.ok) {
    const errorCode = backendPost?.error_code ?? (response.code === "request_timeout" ? "request_timeout" : "network_failed");
    const retryable = backendPost?.retryable ?? (errorCode !== "http_422_schema_error" && errorCode !== "http_4xx_client_error");
    const errorMessage = backendPost?.error_message || response.error || errorCode;
    const error = new Error(`${errorCode}: ${errorMessage} (flush_url: ${backendPost?.url ?? flushUrl}, retryable: ${retryable ? "yes" : "no"})`) as Error & { backend_post?: ExtensionBackendPostResponse };
    error.backend_post = backendPost ?? {
      ok: false,
      url: flushUrl,
      status_code: null,
      error_code: errorCode,
      error_message: errorMessage,
      retryable
    };
    throw error;
  }
  return {
    ok: true,
    backend_post: backendPost,
    harvest_response: backendPost.body ?? null
  } as Record<string, unknown>;
}

async function captureVisibleTab(): Promise<string | null> {
  const response = (await chrome.runtime.sendMessage({ type: "REUP_DOUYIN_CAPTURE_VISIBLE_TAB" } satisfies ExtensionMessage)) as ExtensionMessageResponse;
  return response.ok ? response.screenshot_data_url ?? null : null;
}

function isExtensionContextInvalidatedError(error: unknown): boolean {
  const message = error instanceof Error ? error.message : String(error ?? "");
  return /Extension context invalidated|context invalidated|Extension context was invalidated/i.test(message);
}

function createContextInvalidatedRuntimeV2(): HarvestRuntimeV2State {
  const runtime = createIdleHarvestRuntimeV2();
  return {
    ...runtime,
    status: "failed",
    phase: "failed",
    pause_reason: "content_script_unavailable",
    updated_at: new Date().toISOString(),
    heartbeat_at: null,
    last_error: "Extension context was invalidated. Reload the Douyin tab after reloading the extension, then scan again."
  };
}

async function safeLocalGet(keys: string | string[] | Record<string, unknown>): Promise<Record<string, unknown> | null> {
  try {
    return await chrome.storage.local.get(keys as any);
  } catch (error) {
    if (isExtensionContextInvalidatedError(error)) return null;
    throw error;
  }
}

async function safeLocalSet(items: Record<string, unknown>): Promise<boolean> {
  try {
    await chrome.storage.local.set(items);
    return true;
  } catch (error) {
    if (isExtensionContextInvalidatedError(error)) return false;
    throw error;
  }
}

async function safeLocalRemove(keys: string | string[]): Promise<boolean> {
  try {
    await chrome.storage.local.remove(keys);
    return true;
  } catch (error) {
    if (isExtensionContextInvalidatedError(error)) return false;
    throw error;
  }
}

function applyContextInvalidatedRuntimeV2(): HarvestRuntimeV2State {
  const runtime = createContextInvalidatedRuntimeV2();
  harvestRuntimeSnapshot = runtime;
  harvestProgress = runtimeV2ToProgress(runtime, []);
  return runtime;
}

async function ensureRuntimeV2Initialized(): Promise<void> {
  await clearLegacyHarvestState();
  const stored = await safeLocalGet(HARVEST_RUNTIME_V2_KEY);
  if (!stored) {
    applyContextInvalidatedRuntimeV2();
    return;
  }
  const runtime = isHarvestRuntimeV2State(stored[HARVEST_RUNTIME_V2_KEY]) ? normalizeHarvestRuntimeV2(stored[HARVEST_RUNTIME_V2_KEY]) : createIdleHarvestRuntimeV2();
  harvestRuntimeSnapshot = runtime;
  await saveRuntimeV2(runtime);
  const pendingItems = await loadPendingItemsV2();
  harvestProgress = runtimeV2ToProgress(runtime, pendingItems);
  await saveSafeHarvestRunStateFromProgress(harvestProgress);
}

async function clearLegacyHarvestState(): Promise<void> {
  await safeLocalRemove([...LEGACY_HARVEST_STORAGE_KEYS]);
}

function isHarvestRuntimeV2State(value: unknown): value is HarvestRuntimeV2State {
  return Boolean(value && typeof value === "object" && "schema_version" in value && (value as { schema_version?: unknown }).schema_version === "phase17c_safe_runner");
}

async function loadRuntimeV2(): Promise<HarvestRuntimeV2State> {
  const stored = await safeLocalGet(HARVEST_RUNTIME_V2_KEY);
  if (!stored) return applyContextInvalidatedRuntimeV2();
  const runtime = isHarvestRuntimeV2State(stored[HARVEST_RUNTIME_V2_KEY]) ? normalizeHarvestRuntimeV2(stored[HARVEST_RUNTIME_V2_KEY]) : createIdleHarvestRuntimeV2();
  harvestRuntimeSnapshot = runtime;
  harvestProgress = runtimeV2ToProgress(runtime, await loadPendingItemsV2());
  return runtime;
}

function loadRuntimeSnapshotSync(): HarvestRuntimeV2State | undefined {
  return harvestRuntimeSnapshot;
}

async function saveRuntimeV2(runtime: HarvestRuntimeV2State): Promise<void> {
  const normalized = normalizeHarvestRuntimeV2(runtime);
  harvestRuntimeSnapshot = normalized;
  const saved = await safeLocalSet({ [HARVEST_RUNTIME_V2_KEY]: normalized });
  const pendingItems = saved ? await loadPendingItemsV2() : [];
  harvestProgress = runtimeV2ToProgress(normalized, pendingItems);
  if (saved) await saveSafeHarvestRunStateFromProgress(harvestProgress);
}

async function loadPendingItemsV2(): Promise<FullModalHarvestItemPayload[]> {
  const stored = await safeLocalGet(HARVEST_PENDING_FLUSH_QUEUE_V2_KEY);
  if (!stored) return [];
  return Array.isArray(stored[HARVEST_PENDING_FLUSH_QUEUE_V2_KEY]) ? (stored[HARVEST_PENDING_FLUSH_QUEUE_V2_KEY] as FullModalHarvestItemPayload[]) : [];
}

async function savePendingItemsV2(items: FullModalHarvestItemPayload[]): Promise<void> {
  await safeLocalSet({ [HARVEST_PENDING_FLUSH_QUEUE_V2_KEY]: items });
}

function setRuntimePhaseV2(
  runtime: HarvestRuntimeV2State,
  phase: HarvestRuntimeV2State["phase"],
  updates: Partial<HarvestRuntimeV2State>,
  caller: string,
  reason: string | null = null
): HarvestRuntimeV2State {
  return transitionHarvestRuntime(
    runtime,
    {
      ...updates,
      phase
    },
    {
      caller,
      reason,
      stack_or_location: caller,
      target_index: updates.current_target_index ?? runtime.current_target_index,
      aweme_id: updates.current_aweme_id ?? runtime.current_aweme_id
    }
  );
}

async function ensureRecoveredRunner(runtime: HarvestRuntimeV2State): Promise<void> {
  if (runtime.status !== "running" || !runtime.run_id) return;
  const runner = getHarvestRunnerV2();
  if (runner.isRunning && runner.runId === runtime.run_id) return;
  if (firstPendingTarget(runtime) == null) return;
  if (runner.abortController) runner.abortController.abort();
  runner.abortController = new AbortController();
  runner.runId = runtime.run_id;
  runner.isRunning = true;
  void runner.drainQueue(runtime.run_id);
}

async function createRuntimeForStart(message: ExtensionMessage): Promise<HarvestRuntimeV2State> {
  await clearLegacyHarvestState();
  const calibration = await loadRightRailCalibration();
  if (!calibration) {
    throw new Error("calibration_invalid");
  }
  const options = normalizeHarvestOptions(message.options);
  const targetAwemeIds = [...new Set((options.target_aweme_ids ?? []).map((value) => value.trim()).filter(Boolean))];
  const profileCardEvidenceByAwemeId = normalizeProfileCardEvidenceMap(options.profile_card_evidence_by_aweme_id);
  const runtime = createHarvestRuntimeV2(globalThis.crypto?.randomUUID?.() ?? `run-${Date.now()}`, targetAwemeIds, new Date(), profileCardEvidenceByAwemeId);
  await savePendingItemsV2([]);
  const currentAwemeId = detectCurrentAwemeId(window.location.href, document);
  const started = touchHarvestRuntimeV2(runtime, {
    phase: targetAwemeIds.length > 0 ? "opening_target" : "completed",
    current_aweme_id: currentAwemeId,
    current_target_index: targetAwemeIds.length > 0 ? 1 : 0,
    last_error: null
  });
  await saveRuntimeV2(started);
  return started;
}

function isCalibratedPointPassSource(sourceUsed: string | null): boolean {
  return sourceUsed === "calibrated_point_dom" || sourceUsed === "calibrated_point_ocr" || sourceUsed === "mixed_calibrated_point";
}

function getHarvestRunnerV2(): SafeHarvestRunner {
  if (window.__REUP_DOUYIN_SAFE_HARVEST_RUNNER) return window.__REUP_DOUYIN_SAFE_HARVEST_RUNNER;
  if (window.__REUP_DOUYIN_HARVEST_RUNNER_V2) return window.__REUP_DOUYIN_HARVEST_RUNNER_V2;
  const runner: SafeHarvestRunner = {
    runId: null,
    abortController: null,
    isRunning: false,
    async start(message) {
      if (runner.isRunning) return getHarvestProgressV2();
      const runtime = await createRuntimeForStart(message);
      if (runner.abortController) runner.abortController.abort();
      runner.abortController = new AbortController();
      runner.runId = runtime.run_id;
      runner.isRunning = true;
      void runner.drainQueue(runtime.run_id ?? "");
      return getHarvestProgressV2();
    },
    async resume(message) {
      const current = await loadRuntimeV2();
      if (runner.isRunning && current.status === "running") return getHarvestProgressV2();
      if (current.status === "completed" || current.status === "completed_with_warnings") return getHarvestProgressV2();
      if (!current.run_id) throw new Error("no_saved_harvest_state");
      const calibration = await loadRightRailCalibration();
      const probe = probeCurrentModalMetrics(document, window.location, calibration);
      if (probe.probe_status !== "PASS" || !isCalibratedPointPassSource(probe.source_used ?? null)) {
        throw new Error(`Probe blocked full modal harvest: ${probe.blocking_reason ?? probe.warning_reason ?? "calibrated_point_probe_not_ready"}`);
      }
      const options = normalizeHarvestOptions(message.options);
      const resumed = transitionHarvestRuntime(
        {
          ...current,
          last_metrics: probe,
          target_aweme_ids: options.target_aweme_ids?.length ? [...new Set(options.target_aweme_ids.map((value) => value.trim()).filter(Boolean))] : current.target_aweme_ids,
          profile_card_evidence_by_aweme_id: Object.keys(options.profile_card_evidence_by_aweme_id ?? {}).length
            ? normalizeProfileCardEvidenceMap(options.profile_card_evidence_by_aweme_id)
            : current.profile_card_evidence_by_aweme_id
        },
        {
          status: "running",
          phase: "opening_target",
          pause_reason: null,
          last_error: null,
          current_aweme_id: detectCurrentAwemeId(window.location.href, document)
        },
        {
          caller: "getHarvestRunnerV2.resume",
          reason: "resume",
          stack_or_location: "contentScript.runner.resume",
          aweme_id: probe.aweme_id
        }
      );
      await saveRuntimeV2(resumed);
      if (runner.abortController) runner.abortController.abort();
      runner.abortController = new AbortController();
      runner.runId = resumed.run_id;
      runner.isRunning = true;
      void runner.drainQueue(resumed.run_id ?? "");
      return getHarvestProgressV2();
    },
    async stop() {
      if (runner.abortController) runner.abortController.abort();
      runner.isRunning = false;
      const runtime = await loadRuntimeV2();
      const paused = pauseHarvestRuntimeV2(runtime, "operator_stop", null, new Date(), "getHarvestRunnerV2.stop");
      await saveRuntimeV2(paused);
      return getHarvestProgressV2();
    },
    async drainQueue(runId) {
      try {
        await drainHarvestQueueV2(runId, runner.abortController?.signal ?? new AbortController().signal);
      } finally {
        runner.isRunning = false;
      }
    }
  };
  window.__REUP_DOUYIN_SAFE_HARVEST_RUNNER = runner;
  window.__REUP_DOUYIN_HARVEST_RUNNER_V2 = runner;
  return runner;
}

async function getHarvestConfig(message?: ExtensionMessage): Promise<{
  apiBaseUrl: string;
  captureSessionId: string | null;
  captureId: string | null;
  options: ReturnType<typeof normalizeHarvestOptions>;
}> {
  const [apiBaseUrlStored, captureSessionStored, captureIdStored] = await Promise.all([
    chrome.storage.sync.get("apiBaseUrl"),
    chrome.storage.sync.get("lastCaptureSessionId"),
    chrome.storage.sync.get("lastCaptureId")
  ]);
  const options = normalizeHarvestOptions(message?.options);
  return {
    apiBaseUrl:
      typeof apiBaseUrlStored.apiBaseUrl === "string" && apiBaseUrlStored.apiBaseUrl.trim()
        ? apiBaseUrlStored.apiBaseUrl.trim().replace(/\/+$/, "")
        : "http://127.0.0.1:8000",
    captureSessionId:
      typeof options.capture_session_id === "string" && options.capture_session_id.trim()
        ? options.capture_session_id.trim()
        : typeof captureSessionStored.lastCaptureSessionId === "string" && captureSessionStored.lastCaptureSessionId.trim()
          ? captureSessionStored.lastCaptureSessionId.trim()
          : null,
    captureId:
      typeof options.capture_id === "string" && options.capture_id.trim()
        ? options.capture_id.trim()
        : typeof captureIdStored.lastCaptureId === "string" && captureIdStored.lastCaptureId.trim()
          ? captureIdStored.lastCaptureId.trim()
          : null,
    options
  };
}

async function startSafeHarvestRun(message: ExtensionMessage): Promise<FullModalHarvestProgress> {
  const runner = getHarvestRunnerV2();
  return runner.start(message);
}

async function resumeSafeHarvestRun(message: ExtensionMessage): Promise<FullModalHarvestProgress> {
  const runner = getHarvestRunnerV2();
  return runner.resume(message);
}

async function stopSafeHarvestRun(): Promise<FullModalHarvestProgress> {
  const runner = getHarvestRunnerV2();
  return runner.stop();
}

async function resetSafeHarvestRun(): Promise<FullModalHarvestProgress> {
  const runner = getHarvestRunnerV2();
  if (runner.abortController) runner.abortController.abort();
  runner.isRunning = false;
  runner.runId = null;
  const removed = await safeLocalRemove([HARVEST_RUNTIME_V2_KEY, HARVEST_PENDING_FLUSH_QUEUE_V2_KEY, ...LEGACY_HARVEST_STORAGE_KEYS]);
  if (!removed) return runtimeV2ToProgress(applyContextInvalidatedRuntimeV2(), []);
  const runtime = createIdleHarvestRuntimeV2();
  await saveRuntimeV2(runtime);
  return runtimeV2ToProgress(runtime, []);
}

async function getSafeHarvestRunProgress(): Promise<FullModalHarvestProgress> {
  await clearLegacyHarvestState();
  const runtime = await loadRuntimeV2();
  await ensureRecoveredRunner(runtime);
  const pendingItems = await loadPendingItemsV2();
  harvestProgress = runtimeV2ToProgress(runtime, pendingItems);
  return harvestProgress;
}

async function flushSafeHarvestRun(): Promise<FullModalHarvestProgress> {
  const runtime = await loadRuntimeV2();
  const result = await flushPendingRuntimeItems(runtime);
  await saveRuntimeV2(result.runtime);
  return runtimeV2ToProgress(result.runtime, await loadPendingItemsV2());
}

// Legacy compatibility aliases (V2 command handlers delegate here).
async function startHarvestV2(message: ExtensionMessage): Promise<FullModalHarvestProgress> {
  return startSafeHarvestRun(message);
}

async function resumeHarvestV2(message: ExtensionMessage): Promise<FullModalHarvestProgress> {
  return resumeSafeHarvestRun(message);
}

async function stopHarvestV2(): Promise<FullModalHarvestProgress> {
  return stopSafeHarvestRun();
}

async function resetHarvestStateV2(): Promise<FullModalHarvestProgress> {
  return resetSafeHarvestRun();
}

async function getHarvestProgressV2(): Promise<FullModalHarvestProgress> {
  return getSafeHarvestRunProgress();
}

async function flushHarvestV2(): Promise<FullModalHarvestProgress> {
  return flushSafeHarvestRun();
}

function mapRuntimePhaseToSafePhase(phase: HarvestRuntimeV2State["phase"]): SafeHarvestRunPhase {
  return phase;
}

async function saveSafeHarvestRunStateFromProgress(progress: FullModalHarvestProgress): Promise<void> {
  const runtime = harvestRuntimeSnapshot;
  const targetStatus: Record<string, SafeHarvestRunTargetStatus> = {};
  for (const awemeId of runtime.target_aweme_ids) {
    const item = runtime.target_status[awemeId];
    if (!item) continue;
    targetStatus[awemeId] = {
      index: item.index,
      status: item.status,
      attempts: item.attempts,
      last_error: item.last_error,
      last_integrity_status: null,
      last_expected_aweme_id: null,
      last_observed_aweme_id: null
    };
  }

  const safeState: SafeHarvestRunState = {
    schema_version: "phase17c_safe_runner",
    run_id: runtime.run_id,
    status: runtime.status,
    phase: mapRuntimePhaseToSafePhase(runtime.phase),
    stop_reason: (runtime.pause_reason as SafeHarvestRunStopReason) ?? null,
    profile_url: null,
    capture_session_id: null,
    capture_id: null,
    target_aweme_ids: [...runtime.target_aweme_ids],
    target_status: targetStatus,
    current_target_index: runtime.current_target_index,
    current_aweme_id: runtime.current_aweme_id,
    previous_aweme_id: runtime.previous_aweme_id ?? null,
    counts: {
      target: runtime.counts.target,
      updated: runtime.counts.updated,
      failed: runtime.counts.failed,
      skipped: runtime.counts.skipped,
      pending_flush: runtime.counts.pending_flush,
      flushed: runtime.counts.flushed,
      duplicates: runtime.counts.duplicates,
      integrity_mismatch: 0
    },
    last_metrics: runtime.last_metrics,
    recent_items: runtime.recent_items,
    started_at: runtime.started_at,
    updated_at: runtime.updated_at,
    heartbeat_at: runtime.heartbeat_at,
    last_error: runtime.last_error
  };
  await safeLocalSet({ [SAFE_HARVEST_RUN_KEY]: safeState });
  harvestProgress = progress;
}

async function drainHarvestQueueV2(runId: string, signal: AbortSignal): Promise<void> {
  const config = await getHarvestConfig();
  let consecutiveFailures = 0;
  while (true) {
    if (signal.aborted) return;
    let runtime = await loadRuntimeV2();
    if (runtime.run_id !== runId) return;
    if (runtime.status !== "running") return;
    runtime = heartbeatHarvestRuntimeV2(runtime);
    await saveRuntimeV2(runtime);
    const target = firstPendingTarget(runtime);
    if (!target) {
      const flushResult = await flushPendingRuntimeItems(runtime);
      const completed = completeHarvestRuntimeV2(flushResult.runtime, new Date(), "drainHarvestQueueV2.complete");
      await saveRuntimeV2(completed);
      return;
    }
    runtime = setRuntimePhaseV2(
      runtime,
      "opening_target",
      {
        current_target_index: target.index,
        current_aweme_id: target.aweme_id,
        pause_reason: null,
        last_error: null
      },
      "drainHarvestQueueV2.opening_target",
      "continue"
    );
    runtime = updateTargetStatus(runtime, target.aweme_id, "processing", { attemptsDelta: 1 });
    await saveRuntimeV2(runtime);
    if (detectCaptchaOrLoginWall(document, window.location.href)) {
      await saveRuntimeV2(pauseHarvestRuntimeV2(runtime, "captcha_required", "captcha_required", new Date(), "drainHarvestQueueV2.captcha_gate"));
      return;
    }
    const currentAwemeId = detectCurrentAwemeId(window.location.href, document);
    if (currentAwemeId !== target.aweme_id) {
      runtime = setRuntimePhaseV2(
        runtime,
        "opening_target",
        { previous_aweme_id: currentAwemeId ?? runtime.previous_aweme_id },
        "drainHarvestQueueV2.navigate",
        "navigate_target_modal"
      );
      await saveRuntimeV2(runtime);
      await openTargetModalDirectly(target.aweme_id);
    }
    runtime = setRuntimePhaseV2(runtime, "waiting_modal", { current_aweme_id: target.aweme_id }, "drainHarvestQueueV2.wait_modal", "wait_modal");
    await saveRuntimeV2(runtime);
    const calibration = await loadRightRailCalibration();
    if (!calibration) {
      await saveRuntimeV2(pauseHarvestRuntimeV2(runtime, "calibration_invalid", "calibration_invalid", new Date(), "drainHarvestQueueV2.calibration_invalid"));
      return;
    }
    const extracted = await waitForCurrentModalMetrics(document, window.location, target.aweme_id, config.options.per_item_timeout_ms, calibration);
    if (!extracted) {
      consecutiveFailures += 1;
      const failureMessage = detectCaptchaOrLoginWall(document, window.location.href) ? "captcha_required" : "modal_metrics_timeout";
      const failedRuntime = appendRecentItem(
        updateTargetStatus(
          setRuntimePhaseV2(runtime, "advancing", { last_error: failureMessage }, "drainHarvestQueueV2.timeout_recover", failureMessage),
          target.aweme_id,
          "failed",
          { lastError: failureMessage }
        ),
        {
          index: target.index,
          aweme_id: target.aweme_id,
          duration_seconds: null,
          like_count: null,
          comment_count: null,
          favorite_count: null,
          share_count: null,
          extraction_warning: failureMessage,
          status: "failed"
        }
      );
      const pausedRuntime = pauseHarvestRuntimeV2(
        failedRuntime,
        detectCaptchaOrLoginWall(document, window.location.href) ? "captcha_required" : "consecutive_failures",
        failureMessage,
        new Date(),
        "drainHarvestQueueV2.consecutive_failure_pause"
      );
      await saveRuntimeV2(consecutiveFailures >= 3 || detectCaptchaOrLoginWall(document, window.location.href) ? pausedRuntime : failedRuntime);
      if (consecutiveFailures >= 3 || detectCaptchaOrLoginWall(document, window.location.href)) return;
      continue;
    }
    consecutiveFailures = 0;
    runtime = setRuntimePhaseV2(
      runtime,
      "extracting",
      {
        last_metrics: probeCurrentModalMetrics(document, window.location, calibration),
        current_aweme_id: extracted.aweme_id
      },
      "drainHarvestQueueV2.extracting",
      "extract_metrics"
    );
    await saveRuntimeV2(runtime);
    runtime = setRuntimePhaseV2(runtime, "validating", {}, "drainHarvestQueueV2.validating", "validate_integrity");
    await saveRuntimeV2(runtime);
    await savePendingItemsV2([extracted]);
    const flushResult = await flushPendingRuntimeItems(runtime);
    if (flushResult.runtime.status === "paused") {
      await saveRuntimeV2(flushResult.runtime);
      return;
    }
    runtime = setRuntimePhaseV2(flushResult.runtime, "marking_updated", {}, "drainHarvestQueueV2.marking_updated", "backend_flush_succeeded");
    runtime = appendRecentItem(
      updateTargetStatus(runtime, extracted.aweme_id, "updated"),
      summarizeHarvestedItemV2(extracted, target.index)
    );
    runtime = setRuntimePhaseV2(runtime, "advancing", {}, "drainHarvestQueueV2.post_success", "continue_after_success");
    await saveRuntimeV2(runtime);
  }
}

function normalizeProfileCardEvidenceMap(value: Record<string, HarvestPlanProfileCardEvidence> | null | undefined): Record<string, HarvestPlanProfileCardEvidence> {
  const normalized: Record<string, HarvestPlanProfileCardEvidence> = {};
  for (const [awemeId, evidence] of Object.entries(value ?? {})) {
    const key = awemeId.trim() || evidence.aweme_id?.trim();
    if (!key) continue;
    normalized[key] = { ...evidence, aweme_id: key };
  }
  return normalized;
}

function withProfileCardEvidence(item: FullModalHarvestItemPayload, runtime: HarvestRuntimeV2State): FullModalHarvestItemPayload {
  const evidence = runtime.profile_card_evidence_by_aweme_id?.[item.aweme_id] ?? null;
  if (!evidence) return item;
  return {
    ...item,
    profile_card_evidence: evidence
  };
}

function summarizeHarvestedItemV2(item: FullModalHarvestItemPayload, index: number) {
  return {
    index,
    aweme_id: item.aweme_id,
    duration_seconds: item.raw_dom_detail_metrics.duration_seconds ?? null,
    duration_text: item.raw_dom_detail_metrics.duration_text ?? null,
    like_count: item.raw_dom_detail_metrics.like_count ?? null,
    like_count_source: item.raw_dom_detail_metrics.like_count_source ?? null,
    comment_count: item.raw_dom_detail_metrics.comment_count ?? null,
    favorite_count: item.raw_dom_detail_metrics.favorite_count ?? null,
    share_count: item.raw_dom_detail_metrics.share_count ?? null,
    view_count: item.raw_dom_detail_metrics.view_count ?? null,
    source_used: item.raw_dom_detail_metrics.extraction_source,
    missing_fields: null,
    posted_text: item.raw_dom_detail_metrics.posted_text ?? null,
    extraction_warning: item.raw_dom_detail_metrics.extraction_warning ?? null,
    status: "ok"
  } satisfies NonNullable<FullModalHarvestProgress["last_harvested_item"]>;
}

async function openTargetModalDirectly(targetAwemeId: string): Promise<void> {
  const url = new URL(window.location.href);
  url.searchParams.set("modal_id", targetAwemeId);
  window.history.pushState(window.history.state, "", url.toString());
  window.dispatchEvent(new PopStateEvent("popstate", { state: window.history.state }));
}

async function flushPendingRuntimeItems(runtime: HarvestRuntimeV2State): Promise<{ runtime: HarvestRuntimeV2State }> {
  const pendingItems = await loadPendingItemsV2();
  if (pendingItems.length === 0) {
    return {
      runtime: touchHarvestRuntimeV2(runtime, {
        counts: {
          ...runtime.counts,
          pending_flush: 0
        }
      })
    };
  }
  const message = "full_modal_harvest_non_v2_caller_blocked: content_script_runtime_flush_disabled_for_phase17ae_use_popup_whole_profile_staged_harvest_v2";
  const paused = pauseHarvestRuntimeV2(
    runtime,
    "backend_flush_failed",
    message,
    new Date(),
    "flushPendingRuntimeItems.non_v2_blocked"
  );
  return { runtime: paused };
}

async function probeCurrentModalWithCalibratedPoints(): Promise<ReturnType<typeof probeCurrentModalMetrics>> {
  const calibration = await loadRightRailCalibration();
  const initialModalId = detectCurrentAwemeId(window.location.href, document);
  if (!initialModalId) return { ...probeCurrentModalMetrics(document, window.location, calibration), current_modal_id_before: null, current_modal_id_after: null, extracted_aweme_id: null, blocking_reason: "modal_id_missing", probe_status: "FAIL", ready_for_full_harvest: false };
  if (!calibration) return { ...probeCurrentModalMetrics(document, window.location, calibration), aweme_id: initialModalId, current_modal_id_before: initialModalId, current_modal_id_after: detectCurrentAwemeId(window.location.href, document), extracted_aweme_id: initialModalId, blocking_reason: "calibration_missing", probe_status: "FAIL", ready_for_full_harvest: false };
  const stable = await waitForModalIdMatch(() => detectCurrentAwemeId(window.location.href, document), initialModalId, 2_500);
  if (!stable) return { ...probeCurrentModalMetrics(document, window.location, calibration), aweme_id: initialModalId, current_modal_id_before: initialModalId, current_modal_id_after: detectCurrentAwemeId(window.location.href, document), extracted_aweme_id: initialModalId, blocking_reason: "modal_metrics_timeout", probe_status: "FAIL", ready_for_full_harvest: false };
  const item = await waitForCurrentModalMetrics(document, window.location, initialModalId, 5_000, calibration);
  const afterModalId = detectCurrentAwemeId(window.location.href, document);
  if (!item) return { ...probeCurrentModalMetrics(document, window.location, calibration), aweme_id: initialModalId, current_modal_id_before: initialModalId, current_modal_id_after: afterModalId, extracted_aweme_id: initialModalId, blocking_reason: "calibrated_point_read_failed", probe_status: "FAIL", ready_for_full_harvest: false };
  const extractedAwemeId = item.raw_dom_detail_metrics.aweme_id ?? item.aweme_id ?? null;
  const integrityOk = item.target_aweme_id === initialModalId && item.aweme_id === initialModalId && item.raw_dom_detail_metrics.target_aweme_id === initialModalId && (!item.raw_dom_detail_metrics.aweme_id || item.raw_dom_detail_metrics.aweme_id === initialModalId) && afterModalId === initialModalId;
  if (!integrityOk) return { ...probeCurrentModalMetrics(document, window.location, calibration), aweme_id: initialModalId, current_modal_id_before: initialModalId, current_modal_id_after: afterModalId, extracted_aweme_id: extractedAwemeId, blocking_reason: "data_integrity_mismatch", probe_status: "FAIL", ready_for_full_harvest: false };
  return {
    ...probeCurrentModalMetrics(document, window.location, calibration),
    aweme_id: initialModalId,
    current_modal_id_before: initialModalId,
    current_modal_id_after: afterModalId,
    extracted_aweme_id: extractedAwemeId,
    duration_seconds: item.raw_dom_detail_metrics.duration_seconds ?? null,
    duration_text: item.raw_dom_detail_metrics.duration_text ?? null,
    like_count: item.raw_dom_detail_metrics.like_count ?? null,
    comment_count: item.raw_dom_detail_metrics.comment_count ?? null,
    favorite_count: item.raw_dom_detail_metrics.favorite_count ?? null,
    share_count: item.raw_dom_detail_metrics.share_count ?? null,
    source_used: item.raw_dom_detail_metrics.source_used ?? null,
    warning_reason: item.raw_dom_detail_metrics.warning_reason ?? null,
    extraction_warning: item.raw_dom_detail_metrics.extraction_warning ?? null,
    probe_status: "PASS",
    ready_for_full_harvest: true,
    blocking_reason: null
  };
}




