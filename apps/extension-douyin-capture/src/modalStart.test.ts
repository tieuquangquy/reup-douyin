import assert from "node:assert/strict";
import { createSmartState } from "./popupWorkflow.js";
import {
  buildModalHarvestCoverage,
  formatHarvestMode,
  formatModalHarvestCoverage,
  getProfileUrlFromModalUrl,
  hasKnownTargetQueue,
  resolveProfileUrlFromModalUrl
} from "./modalStart.js";

assert.equal(getProfileUrlFromModalUrl("not-a-url"), null, "invalid URLs must return null");
assert.equal(
  getProfileUrlFromModalUrl("https://www.douyin.com/user/MS4wLjABAAAAfixture"),
  null,
  "profile URL without modal_id must not be treated as modal URL"
);

{
  const resolved = getProfileUrlFromModalUrl(
    "https://www.douyin.com/user/MS4wLjABAAAAfixture?foo=bar&modal_id=7634&tab=works#hash"
  );
  assert.ok(resolved, "modal URL must resolve to profile URL and current modal id");
  assert.equal(resolved?.current_modal_aweme_id, "7634");
  assert.equal(
    resolved?.profile_url_without_modal_id,
    "https://www.douyin.com/user/MS4wLjABAAAAfixture?foo=bar&tab=works"
  );
  assert.equal(
    resolved?.original_modal_url,
    "https://www.douyin.com/user/MS4wLjABAAAAfixture?foo=bar&modal_id=7634&tab=works#hash"
  );
}

assert.equal(hasKnownTargetQueue(null), false, "null smart state must not be treated as known queue");
assert.equal(
  hasKnownTargetQueue(createSmartState({ latest_capture_session_id: "session-1", target_aweme_ids: [] })),
  false,
  "empty target queue must not be treated as known"
);
assert.equal(
  hasKnownTargetQueue(createSmartState({ latest_capture_session_id: null, target_aweme_ids: ["7634"] })),
  true,
  "sessionless non-empty target queue must be treated as known"
);

{
  const coverage = buildModalHarvestCoverage({
    modalUrl: "https://www.douyin.com/user/MS4wLjABAAAAfixture?modal_id=7634",
    smartState: createSmartState({
      latest_capture_session_id: null,
      target_aweme_ids: [],
      captured_item_count: 53
    }),
    mode: "new_and_incomplete"
  });
  assert.equal(coverage.can_harvest_all, false);
  assert.equal(coverage.reason_if_no, "Target queue missing; resolve profile queue first.");
}

{
  const coverage = buildModalHarvestCoverage({
    modalUrl: "https://www.douyin.com/user/MS4wLjABAAAAfixture?modal_id=7634",
    smartState: createSmartState({
      latest_capture_session_id: "session-1",
      target_aweme_ids: [],
      captured_item_count: 53
    }),
    mode: "new_only"
  });
  assert.equal(coverage.can_harvest_all, false);
  assert.equal(coverage.reason_if_no, "Target queue missing; resolve profile queue first.");
}

{
  const coverage = buildModalHarvestCoverage({
    modalUrl: "https://www.douyin.com/user/MS4wLjABAAAAfixture?modal_id=7634",
    smartState: createSmartState({
      latest_capture_session_id: "session-1",
      target_aweme_ids: ["7639", "7640"],
      harvest_mode: "new_only",
      scan_summary: {
        harvest_mode: "new_only",
        total_found: 53,
        target_count: 2,
        new_count: 2,
        incomplete_count: 0,
        complete_count: 51,
        skipped_count: 51,
        target_aweme_ids: ["7639", "7640"],
        new_aweme_ids: ["7639", "7640"],
        incomplete_aweme_ids: [],
        complete_aweme_ids: ["7001"]
      }
    }),
    mode: "new_only"
  });
  assert.equal(coverage.can_harvest_all, false);
  assert.equal(coverage.current_modal_in_target_queue, false);
  assert.equal(coverage.reason_if_no, "Current modal is not in the target queue for the selected mode.");
}

{
  const coverage = buildModalHarvestCoverage({
    modalUrl: "https://www.douyin.com/user/MS4wLjABAAAAfixture?modal_id=7634",
    smartState: createSmartState({
      latest_capture_session_id: null,
      target_aweme_ids: ["7634", "7635", "7636"],
      harvest_mode: "new_and_incomplete",
      scan_summary: {
        harvest_mode: "new_and_incomplete",
        total_found: 53,
        target_count: 3,
        new_count: 2,
        incomplete_count: 1,
        complete_count: 50,
        skipped_count: 50,
        target_aweme_ids: ["7634", "7635", "7636"],
        new_aweme_ids: ["7635", "7636"],
        incomplete_aweme_ids: ["7634"],
        complete_aweme_ids: ["7001"]
      }
    }),
    mode: "refresh_all"
  });
  assert.equal(coverage.can_harvest_all, true);
  assert.equal(coverage.target_mode, "new_and_incomplete", "stored smart-state mode should be surfaced");
  assert.equal(coverage.remaining_targets_after_current, 2);
  const formatted = formatModalHarvestCoverage(coverage);
  assert.equal(formatted["Can harvest all"], "yes");
  assert.equal(formatted["Target mode"], "New + incomplete");
}

{
  const resolved = resolveProfileUrlFromModalUrl("https://www.douyin.com/user/MS4wLjABAAAAfixture?foo=bar&modal_id=7634#modal");
  assert.ok(resolved, "Phase 17E resolver must expose profile_url and original_modal_aweme_id aliases");
  assert.equal(resolved?.profile_url, "https://www.douyin.com/user/MS4wLjABAAAAfixture?foo=bar");
  assert.equal(resolved?.original_modal_aweme_id, "7634");
}

assert.equal(formatHarvestMode("refresh_all"), "Refresh all");
assert.equal(formatHarvestMode("new_only"), "New only");
assert.equal(formatHarvestMode("new_and_incomplete"), "New + incomplete");

console.log("modal start coverage tests passed");
