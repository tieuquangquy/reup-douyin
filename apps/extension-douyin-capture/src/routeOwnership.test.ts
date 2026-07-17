import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const popupSource = readFileSync(new URL("./popup.ts", import.meta.url), "utf8");
const backgroundSource = readFileSync(new URL("./background.ts", import.meta.url), "utf8");
const contentScriptSource = readFileSync(new URL("./contentScript.ts", import.meta.url), "utf8");
const resetTestSource = readFileSync(new URL("./extensionReset.test.ts", import.meta.url), "utf8");

assert.match(
  backgroundSource,
  /message\.type === "DOUYIN_SCANNER_START_SCAN_PROFILE_22C11B" \|\| message\.type === "DOUYIN_SCANNER_START_SCAN_PROFILE"/,
  "background must keep both Scan Profile route aliases accepted by the same route guard"
);
assert.match(
  backgroundSource,
  /void runScanProfile22C11B\(\{[\s\S]*source: message\.type[\s\S]*\}\)/,
  "background Scan Profile aliases must continue to forward into the canonical 22C11B scan implementation"
);
assert.match(
  backgroundSource,
  /CANONICAL_SCAN_PROFILE_MESSAGE_22C11B = "DOUYIN_SCAN_PROFILE_MINIMAL_22C11B"/,
  "background must dispatch the canonical minimal content scanner message"
);
assert.match(
  backgroundSource,
  /CANONICAL_SCAN_PROFILE_PING_22C11B = "DOUYIN_SCAN_PROFILE_MINIMAL_22C11B_PING"/,
  "background must keep the canonical minimal content scanner ping message"
);
assert.match(
  backgroundSource,
  /const queueBuilderName = "scan_queue_adapter_22C11B"/,
  "background queue adapter marker must remain stable"
);
assert.match(
  backgroundSource,
  /stopReason: "scroll_converged_queue_accepted_22C11B"/,
  "background stop reason compatibility string must remain stable"
);

assert.match(
  contentScriptSource,
  /"DOUYIN_SCAN_PROFILE_MINIMAL_22C11B_PING"[\s\S]*"DOUYIN_SCAN_PROFILE_MINIMAL_22C11B"/,
  "content script supported handler list must include the canonical minimal scanner ping and handler"
);
assert.match(
  contentScriptSource,
  /message\.type === "DOUYIN_SCAN_PROFILE_MINIMAL_22C11B"[\s\S]*runMinimalActiveTabProfileScan22C11B/,
  "content script must keep the canonical minimal scanner handler wired to its implementation"
);
assert.match(
  contentScriptSource,
  /collectActiveWorksGridTargetsUntilStable22C11B\(profileUrl\)/,
  "content canonical scanner must continue to use the active works grid stable-collection implementation"
);

assert.match(
  popupSource,
  /chrome\.runtime\.sendMessage\(\{ type: "DOUYIN_SCANNER_START_SCAN_PROFILE_22C11B"/,
  "popup Scan Profile primary action must dispatch the canonical background route"
);
assert.match(
  popupSource,
  /backgroundMessageType: "DOUYIN_SCANNER_START_SCAN_PROFILE_22C11B"/,
  "popup Scan Profile diagnostics must identify the canonical background route"
);
assert.doesNotMatch(
  popupSource,
  /chrome\.runtime\.sendMessage\(\{ type: "(?:REUP_DOUYIN_MODAL_TEST_SCAN_PROFILE|REUP_DOUYIN_START_FULL_MODAL_HARVEST|REUP_DOUYIN_START_SMART_CAPTURE|REUP_DOUYIN_CAPTURE)"/,
  "popup primary runtime messages must not dispatch legacy runner targets"
);

assert.match(
  resetTestSource,
  /Reset Harvest State preserves calibration/,
  "reset tests must continue to assert Reset Harvest preserves right rail calibration"
);
assert.match(
  resetTestSource,
  /Reset Harvest State preserves canonical scanner calibration/,
  "reset tests must continue to assert Reset Harvest preserves canonical scanner calibration"
);
assert.match(
  resetTestSource,
  /Reset Harvest State preserves canonical scanner root calibration bridge/,
  "reset tests must continue to assert Reset Harvest preserves the canonical scanner root calibration bridge"
);

console.log("route ownership safety rail tests passed");
