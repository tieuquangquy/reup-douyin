import type { ScannerControlPanelViewModel } from "./viewModel.js";
import { computeProfileCollectPercent } from "./collectLiveProgress.js";
import type { CollectLiveProgressPhase } from "./collectLiveProgress.js";
import type { WholeProfileHarvestState } from "./state.js";

const MAX_NUMERATOR_STEP = 1.25;
const MAX_ALREADY_STEP = 1.25;

type SmoothSession = {
  jobId: string | null;
  phase: CollectLiveProgressPhase | null;
  displayNumerator: number;
  targetNumerator: number;
  displayAlready: number;
  targetAlready: number;
  profileTotal: number;
  priorAlreadyBaseline: number;
};

let session: SmoothSession = {
  jobId: null,
  phase: null,
  displayNumerator: 0,
  targetNumerator: 0,
  displayAlready: 0,
  targetAlready: 0,
  profileTotal: 0,
  priorAlreadyBaseline: 0
};

let rafHandle: number | null = null;
let frameCallback: (() => void) | null = null;
let lastSourceViewModel: ScannerControlPanelViewModel | null = null;
let lastJobId: string | null = null;

function resetSession(): void {
  session = {
    jobId: null,
    phase: null,
    displayNumerator: 0,
    targetNumerator: 0,
    displayAlready: 0,
    targetAlready: 0,
    profileTotal: 0,
    priorAlreadyBaseline: 0
  };
}

export function resetCollectDisplaySmoothing(): void {
  resetSession();
  lastSourceViewModel = null;
  lastJobId = null;
  stopCollectDisplayAnimationLoop();
}

export function stopCollectDisplayAnimationLoop(): void {
  frameCallback = null;
  if (rafHandle !== null) {
    cancelAnimationFrame(rafHandle);
    rafHandle = null;
  }
}

function advanceToward(current: number, target: number, step: number): number {
  if (current >= target) return target;
  return Math.min(target, current + step);
}

/** Shared live-collect gate for presentation layers (avoids viewModel ↔ authoritative cycles). */
export function isHybridCollectJobLiveForPresentation(state: WholeProfileHarvestState, nowMs = Date.now()): boolean {
  const harvestPausedForAuthOrSafety = state.harvest.status === "paused"
    || state.harvest.paused_reason === "backend_auth_required"
    || state.harvest.paused_reason === "douyin_login_required";
  const collectJobTerminal = state.collect_job.state === "completed"
    || state.collect_job.state === "failed"
    || state.collect_job.state === "stuck"
    || state.collect_job.state === "aborted_by_user_fix_stuck";
  if (harvestPausedForAuthOrSafety || collectJobTerminal) return false;

  const step = String(state.collect_job.current_step ?? "");
  if (step.includes("flush") || step.includes("hydrat") || step.startsWith("hybrid_loop_") || step.startsWith("hybrid_runner_") || step === "hybrid_unattended_chain_continue") {
    const heartbeatAt = state.collect_job.heartbeat_at ?? state.collect_job.updated_at;
    const heartbeatMs = heartbeatAt ? Date.parse(heartbeatAt) : Number.NaN;
    if (Number.isFinite(heartbeatMs) && nowMs - heartbeatMs > 45_000) return false;
    return true;
  }

  const collectJobLive = state.collect_job.state === "running"
    || state.collect_job.state === "starting"
    || state.collect_job.state === "running_tab_inactive";
  const collecting = (state.workflow.collection.status === "running" || state.workflow.collection.status === "opening_target")
    && state.workflow.active_task === "collect_videos";
  if (state.collect_job.state === "starting" && !harvestPausedForAuthOrSafety && !collectJobTerminal) {
    return true;
  }
  const liveAttempted = typeof state.collect_job.attempted_count === "number" ? Math.max(0, state.collect_job.attempted_count) : 0;
  const liveSucceeded = typeof state.collect_job.succeeded_count === "number" ? Math.max(0, state.collect_job.succeeded_count) : 0;
  return collecting || (collectJobLive && (liveAttempted > 0 || liveSucceeded > 0 || step.startsWith("hybrid_loop_") || step.startsWith("hybrid_runner_")));
}

function capProfileNumerator(value: number, profileTotal: number): number {
  if (profileTotal <= 0) return Math.max(0, value);
  return Math.max(0, Math.min(profileTotal, value));
}

export function syncCollectDisplayTargets(
  viewModel: ScannerControlPanelViewModel,
  jobId: string | null
): void {
  const progress = viewModel.collectProgress;
  if (!progress?.active) {
    resetCollectDisplaySmoothing();
    return;
  }

  lastSourceViewModel = viewModel;
  lastJobId = jobId;

  const phase = progress.phase;
  const profileTotal = progress.profileTotal;
  const targetNumerator = capProfileNumerator(
    Math.min(
      progress.profileTargetNumerator ?? progress.profileAlready,
      progress.tilesAlreadyTarget ?? progress.profileTargetNumerator ?? progress.profileAlready
    ),
    profileTotal
  );
  const targetAlready = capProfileNumerator(
    progress.tilesAlreadyTarget ?? progress.profileAlready,
    profileTotal
  );
  const priorBaseline = capProfileNumerator(progress.priorAlreadyBaseline ?? 0, profileTotal);

  if (jobId !== session.jobId) {
    session = {
      jobId,
      phase,
      profileTotal,
      targetNumerator: capProfileNumerator(Math.max(priorBaseline, targetNumerator), profileTotal),
      targetAlready: capProfileNumerator(Math.max(priorBaseline, targetAlready), profileTotal),
      priorAlreadyBaseline: priorBaseline,
      displayNumerator: priorBaseline,
      displayAlready: priorBaseline
    };
  } else if (phase !== session.phase) {
    session = {
      ...session,
      phase,
      profileTotal,
      targetNumerator: capProfileNumerator(Math.max(session.displayNumerator, targetNumerator), profileTotal),
      targetAlready: capProfileNumerator(Math.max(session.displayAlready, targetAlready), profileTotal),
      priorAlreadyBaseline: priorBaseline
    };
  } else if (profileTotal !== session.profileTotal) {
    session.profileTotal = profileTotal;
    session.targetNumerator = capProfileNumerator(Math.max(session.targetNumerator, targetNumerator), profileTotal);
    session.targetAlready = capProfileNumerator(Math.max(session.targetAlready, targetAlready), profileTotal);
  } else {
    session.targetNumerator = capProfileNumerator(Math.max(session.targetNumerator, targetNumerator), profileTotal);
    session.targetAlready = capProfileNumerator(Math.max(session.targetAlready, targetAlready), profileTotal);
    session.priorAlreadyBaseline = priorBaseline;
  }
}

export function tickCollectDisplaySession(): boolean {
  if (!lastSourceViewModel?.collectProgress?.active) return false;
  const profileTotal = session.profileTotal;
  session.displayNumerator = capProfileNumerator(
    advanceToward(session.displayNumerator, session.targetNumerator, MAX_NUMERATOR_STEP),
    profileTotal
  );
  session.displayAlready = capProfileNumerator(
    advanceToward(session.displayAlready, session.targetAlready, MAX_ALREADY_STEP),
    profileTotal
  );
  return session.displayNumerator < session.targetNumerator
    || session.displayAlready < session.targetAlready;
}

function displayCount(value: number): number {
  return Math.max(0, Math.floor(value));
}

/** Strip rAF smoothing decimals from collect progress labels shown in chrome. */
export function formatIntegerCollectLabel(label: string | null | undefined): string {
  if (!label) return "";
  return /\d+\.\d+/.test(label) ? label.replace(/(\d+)\.\d+/g, "$1") : label;
}

function buildHeaderLabel(
  progress: NonNullable<ScannerControlPanelViewModel["collectProgress"]>,
  displayNumerator: number,
  phase: CollectLiveProgressPhase
): string {
  const profileTotal = progress.profileTotal;
  const shown = displayCount(displayNumerator);
  if (progress.profileIndeterminate && shown === 0) {
    return phase === "preparing" ? "Preparing…" : "Checking…";
  }
  if (profileTotal > 0) {
    return phase === "saving"
      ? `Saving ${shown} / ${profileTotal}`
      : phase === "checking"
        ? "Recovering metrics…"
        : `Collecting ${shown} / ${profileTotal}`;
  }
  return phase === "preparing" ? "Preparing…" : phase === "checking" ? "Recovering metrics…" : "Checking…";
}

/**
 * Resolve the phase actually shown to the user after smoothing.
 *
 * The runner can emit a transient `preparing` frame (succeeded/attempted momentarily 0 between
 * generations, before the backend snapshot refresh) while the monotonic smoothing session still
 * holds a high `displayNumerator`. Rendering "PREPARING"/"Checking" next to a 99% bar is
 * self-contradictory, so any visible progress forces "collecting" (saving is preserved).
 */
function resolveEffectiveSmoothedPhase(
  phase: CollectLiveProgressPhase,
  displayNumerator: number
): CollectLiveProgressPhase {
  if (phase === "saving") return "saving";
  return displayCount(displayNumerator) > 0 ? "collecting" : phase;
}

export function applyCollectDisplaySmoothing(
  viewModel: ScannerControlPanelViewModel,
  jobId: string | null
): ScannerControlPanelViewModel {
  syncCollectDisplayTargets(viewModel, jobId);
  tickCollectDisplaySession();
  return materializeSmoothedCollectViewModel(viewModel);
}

function materializeSmoothedCollectViewModel(viewModel: ScannerControlPanelViewModel): ScannerControlPanelViewModel {
  const progress = viewModel.collectProgress;
  if (!progress?.active) return viewModel;

  const profileTotal = progress.profileTotal;
  const skipped = progress.batchNeedData ?? 0;
  const showIndeterminate = Boolean(progress.profileIndeterminate) && session.displayNumerator === 0;
  const displayNumerator = showIndeterminate ? 0 : displayCount(session.displayNumerator);
  const displayAlready = displayCount(session.displayAlready);
  const phase = resolveEffectiveSmoothedPhase(progress.phase, displayNumerator);
  const remaining = Math.max(0, profileTotal - displayAlready - skipped);
  const profilePercent = showIndeterminate || profileTotal <= 0
    ? null
    : computeProfileCollectPercent(displayNumerator, profileTotal);

  const headerLabel = buildHeaderLabel(progress, displayNumerator, phase);
  const description = profileTotal > 0
    ? (showIndeterminate
      ? `Starting collection… ${profileTotal} videos in profile.`
      : skipped > 0
        ? `Collecting videos ${displayNumerator} / ${profileTotal} · ${skipped} need data.`
        : `Collecting videos ${displayNumerator} / ${profileTotal}.`)
    : "Collecting videos…";

  const tiles = phase === "saving"
    ? {
      alreadyCollectedCount: displayAlready,
      newCount: remaining,
      queueCount: remaining
    }
    : {
      alreadyCollectedCount: displayNumerator,
      newCount: Math.max(0, profileTotal - displayNumerator - skipped),
      queueCount: Math.max(0, profileTotal - displayNumerator - skipped)
    };

  return {
    ...viewModel,
    headerStatus: headerLabel,
    statsCompact: null,
    emptyState: null,
    counts: {
      ...viewModel.counts,
      ...tiles
    },
    primaryAction: viewModel.primaryAction
      ? { ...viewModel.primaryAction, label: headerLabel, description, enabled: false }
      : viewModel.primaryAction,
    action: viewModel.action
      ? { ...viewModel.action, buttonLabel: headerLabel, description, enabled: false }
      : viewModel.action,
    collectProgress: {
      ...progress,
      phase,
      profileAlready: displayNumerator,
      profilePercent,
      profileIndeterminate: showIndeterminate
    }
  };
}

export function startCollectDisplayAnimationLoop(onFrame: () => void): void {
  frameCallback = onFrame;
  if (rafHandle !== null) return;

  const step = (): void => {
    rafHandle = null;
    const onFrame = frameCallback;
    if (!onFrame) return;
    const needsMore = tickCollectDisplaySession();
    onFrame();
    if (needsMore && frameCallback) {
      rafHandle = requestAnimationFrame(step);
    }
  };
  rafHandle = requestAnimationFrame(step);
}

export function buildSmoothedCollectViewModelFromSession(): ScannerControlPanelViewModel | null {
  if (!lastSourceViewModel?.collectProgress?.active) return null;
  return materializeSmoothedCollectViewModel(lastSourceViewModel);
}
