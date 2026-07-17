import assert from "node:assert/strict";

import { createWholeProfileHarvestIdleState, type WholeProfileHarvestState } from "./wholeProfileHarvest/state.js";
import {
  applyScannerPresentationAuthority,
  clearScanSessionDiagnostics,
  deriveScannerPresentationAuthority,
  readScanAuthorityDiagnostics,
  resolveFinalizingStagePresentation
} from "./wholeProfileHarvest/scanAuthorityDiagnostics.js";
import { isActionAllowedForWorkflowPhase, resolveScannerWorkflowPhase } from "./wholeProfileHarvest/scannerWorkflowPhase.js";
import { getDouyinScannerWorkflowReadiness } from "./wholeProfileHarvest/readiness.js";

{
  const cleared = clearScanSessionDiagnostics({
    over_displayed_count: 2,
    count_semantics_status: "overcollected_needs_validation",
    hybrid_network_cache_mode_flag: "enabled",
    scan_progress_discovered: 50
  });
  assert.equal(cleared.over_displayed_count, null);
  assert.equal(cleared.hybrid_network_cache_mode_flag, "enabled");
  assert.equal(cleared.scan_progress_discovered, null);
}

{
  const stage = resolveFinalizingStagePresentation({ scan_finalization_stage: "inbox_sync" }, "fallback");
  assert.equal(stage.title, "Syncing Capture Inbox");
  assert.match(stage.detail, /Syncing scan results/);
}

{
  const idle = createWholeProfileHarvestIdleState("2026-07-11T01:00:00.000Z");
  const stale: WholeProfileHarvestState = {
    ...idle,
    debug: {
      ...idle.debug,
      last_response_summary: {
        diagnostics_channel: "runtime_debug_diagnostics",
        over_displayed_count: 1,
        count_semantics_status: "overcollected_needs_validation"
      }
    }
  };
  const authority = deriveScannerPresentationAuthority(stale, {
    primaryActionKey: "scan_profile",
    currentHeaderStatus: "Scan required",
    scanProgressActive: false,
    scanProgressAtFull: false,
    queueCount: 0,
    newCount: 0
  });
  assert.equal(authority.phase, "idle_scan_required");
  assert.equal(authority.diagnosticsTrusted, false);
  assert.equal(readScanAuthorityDiagnostics(stale).over_displayed_count, 1);
}

{
  const finalizingVm = applyScannerPresentationAuthority({
    headerStatus: "Finalizing 143 / 143",
    primaryAction: { key: "scan_profile", title: "Finalizing scan", label: "Finalizing...", description: "old" },
    action: { key: "scan_profile", title: "Finalizing scan", buttonLabel: "Finalizing...", description: "old" },
    emptyState: null,
    scanProgress: { active: true, phaseLabel: "Finalizing", detail: "old" }
  }, {
    phase: "scan_finalizing",
    headerStatus: "Finalizing 143 / 143",
    diagnosticsTrusted: true,
    finalizingStage: resolveFinalizingStagePresentation({ scan_finalization_stage: "classification" }, "fallback"),
    finalizingElapsedSeconds: 12
  });
  assert.match(finalizingVm.primaryAction.description, /Classifying new, incomplete/);
  assert.match(finalizingVm.primaryAction.description, /12s/);
}

{
  const readiness = getDouyinScannerWorkflowReadiness(createWholeProfileHarvestIdleState("2026-07-11T01:00:00.000Z"));
  const phase = resolveScannerWorkflowPhase("idle_scan_required", readiness);
  assert.equal(phase, "idle");
  assert.equal(isActionAllowedForWorkflowPhase(phase, "scan_profile"), true);
  assert.equal(isActionAllowedForWorkflowPhase(phase, "start_collecting"), false);
}

console.info("scanAuthorityDiagnostics tests passed");
