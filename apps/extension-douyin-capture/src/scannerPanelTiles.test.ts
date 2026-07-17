import assert from "node:assert/strict";
import {
  resolveLargeProfileTileCounts,
  scanDiagnosticsLargeProfileMode,
  shouldApplyLargeProfilePersistedTileCounts
} from "./wholeProfileHarvest/scannerPanelTiles.js";
import type { WholeProfileHarvestState } from "./wholeProfileHarvest/state.js";

function baseState(): WholeProfileHarvestState {
  return {
    profile_scan: { diagnostics: { large_profile_mode: "yes", queue_total_persisted: 983 } },
    verify: { diagnostics: { large_profile_mode: "yes" } }
  } as unknown as WholeProfileHarvestState;
}

{
  assert.equal(scanDiagnosticsLargeProfileMode(baseState()), true);
  assert.equal(
    shouldApplyLargeProfilePersistedTileCounts({
      largeProfilePersistedTotal: 983,
      presentationBlocked: false,
      largeProfileMode: true,
      popupMetricsAuthoritative: true,
      persistedTotalHasNewerAuthority: false
    }),
    true,
    "large profile mode always applies persisted tile counts"
  );
  assert.equal(
    shouldApplyLargeProfilePersistedTileCounts({
      largeProfilePersistedTotal: 3320,
      presentationBlocked: false,
      largeProfileMode: true,
      popupMetricsAuthoritative: true,
      persistedTotalHasNewerAuthority: false,
      displayedProfileCollectLimit: 3304
    }),
    false,
    "displayed profile collect limit defers to PCC tiles"
  );
  const tiles = resolveLargeProfileTileCounts(983, 30, true);
  assert.equal(tiles.newCount, 983);
  assert.equal(tiles.queueCount, 983);
  const partial = resolveLargeProfileTileCounts(983, 30, false);
  assert.equal(partial.newCount, 983);
  assert.equal(partial.queueCount, 500);
}

console.log("scannerPanelTiles.test.ts: PASS");
