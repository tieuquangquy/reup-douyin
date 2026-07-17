import assert from "node:assert/strict";

import {
  buildScanProgressPresentationFields,
  computeScanProgressPercent,
  formatScanProgressFractionLabel
} from "./wholeProfileHarvest/scanProgressPresentation.js";
import { applyHybridNetworkCacheModeFlagToState } from "./wholeProfileHarvest/readiness.js";
import { createWholeProfileHarvestIdleState } from "./wholeProfileHarvest/state.js";
import { getScannerControlPanelViewModel } from "./wholeProfileHarvest/viewModel.js";

const at = new Date().toISOString();

{
  const presentation = buildScanProgressPresentationFields({
    discovered: 3380,
    expected: 3303,
    phaseLabel: "Finalizing scan"
  });
  assert.equal(presentation.fractionDiscovered, 3303);
  assert.equal(presentation.overDisplayExtra, 77);
  assert.equal(presentation.percent, 100);
  assert.equal(presentation.progressFractionLabel, "3303 / 3303");
}

{
  const presentation = buildScanProgressPresentationFields({
    discovered: 3380,
    expected: 3303,
    phaseLabel: "Scanning profile"
  });
  assert.equal(presentation.fractionDiscovered, 3303);
  assert.equal(presentation.percent, 100);
  assert.equal(presentation.progressFractionLabel, "3303 / 3303");
}

{
  const presentation = buildScanProgressPresentationFields({
    discovered: 2000,
    expected: 3303,
    phaseLabel: "Finalizing scan"
  });
  assert.equal(presentation.fractionDiscovered, 2000);
  assert.equal(presentation.overDisplayExtra, null);
  assert.equal(presentation.percent, 61);
  assert.equal(presentation.progressFractionLabel, "2000 / 3303");
}

assert.equal(
  formatScanProgressFractionLabel(3380, 3303, "Finalizing"),
  "3303 / 3303"
);
assert.equal(computeScanProgressPercent(3380, 3303), 100);

{
  const idle = createWholeProfileHarvestIdleState(at);
  const state = {
    ...idle,
    run_id: "scan_run_over_display",
    status: "scanning" as const,
    profile_url: "https://www.douyin.com/user/over-display-profile",
    workflow: {
      ...idle.workflow,
      active_task: "scan_profile" as const,
      action_lock: "scan_profile" as const,
      scan: { ...idle.workflow.scan, status: "running" as const, started_at: at, updated_at: at }
    },
    scan_job: {
      ...idle.scan_job,
      scan_job_id: "scan_run_over_display",
      status: "running" as const,
      expected_count: 3303,
      total_persisted: 3300,
      page_count: 169,
      request_count: 169
    },
    profile_scan: {
      ...idle.profile_scan,
      diagnostics: {
        diagnostics_channel: "scan_authority_diagnostics",
        displayed_profile_count: 3303,
        expected_profile_video_count: 3303,
        scan_run_id: "scan_run_over_display"
      }
    },
    debug: {
      ...idle.debug,
      last_response_summary: {
        diagnostics_channel: "runtime_debug_diagnostics",
        scan_run_id: "scan_run_over_display",
        scan_progress_discovered: 3380,
        scan_progress_expected: 3303,
        scan_progress_phase_label: "Finalizing scan",
        scan_progress_pages: 169,
        scan_progress_requests: 169,
        scan_progress_status_code: 0
      }
    }
  };
  const panel = getScannerControlPanelViewModel(state, { app_backend_logged_in: true });
  assert.equal(panel.scanProgress.active, true);
  assert.equal(panel.scanProgress.discovered, 3380);
  assert.equal(panel.scanProgress.expected, 3303);
  assert.equal(panel.scanProgress.fractionDiscovered, 3303);
  assert.equal(panel.scanProgress.overDisplayExtra, 77);
  assert.equal(panel.scanProgress.progressFractionLabel, "3303 / 3303");
  assert.equal(panel.scanProgress.percent, 100);
  assert.match(panel.headerStatus, /Finalizing 3303 \/ 3303/);
  assert.doesNotMatch(panel.scanProgress.detail, /beyond profile count/);
  assert.doesNotMatch(panel.primaryAction.description, /beyond profile count/);
}

console.info("scanProgressPresentation.test.ts: PASS");
