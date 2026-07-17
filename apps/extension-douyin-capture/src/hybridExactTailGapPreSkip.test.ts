import assert from "node:assert/strict";

import {
  filterQueueToDisplayedProfileCollectScope,
  resolveOverDisplayedExtraAwemeIdSet
} from "./wholeProfileHarvest/displayedProfileQueueCap.js";
import {
  reopenTailGapQueueItemForCollect,
  selectExactTailGapCollectTargets,
  shouldExactTailGapPreSkipFail
} from "./wholeProfileHarvest/hybridBackendGapAwemeIds.js";

function actionable(item: { aweme_id: string; status: string; capture_status?: string }): boolean {
  const captureStatus = String(item.capture_status ?? "");
  if (captureStatus === "skipped" || captureStatus === "complete") return false;
  return item.status === "pending" || item.status === "needs_metadata";
}

function stub(awemeId: string, index: number) {
  return reopenTailGapQueueItemForCollect({
    aweme_id: awemeId,
    status: "needs_metadata",
    capture_status: "new",
    index
  });
}

{
  const exactGapIds = ["7186174527959780640", "7184946675004230971"];
  const bloatedQueue = [
    { aweme_id: "7186174527959780640", status: "pending", capture_status: "skipped" },
    { aweme_id: "7184946675004230971", status: "skipped", capture_status: "skipped" }
  ];
  const selected = selectExactTailGapCollectTargets(bloatedQueue, exactGapIds, actionable, stub);
  assert.equal(selected.length, 2, "tail-gap select must reopen skipped capture_status rows");
  assert.equal(
    shouldExactTailGapPreSkipFail({
      hybridExactTailGapActive: true,
      exactGapIds,
      preSkipPending: 0,
      profileRemaining: 2
    }),
    true
  );
}

{
  const exactGapIds = ["7186174527959780640"];
  const diagnostics = {
    displayed_profile_count: 3304,
    over_displayed_extra_ids_exact: ["7186174527959780640"]
  };
  const queue = [{ aweme_id: "7186174527959780640", status: "pending", capture_status: "new" }];
  const scoped = filterQueueToDisplayedProfileCollectScope(queue, diagnostics);
  assert.equal(scoped.length, 0, "displayed scope may exclude tail-gap IDs marked as API extras");
  assert.equal(resolveOverDisplayedExtraAwemeIdSet(diagnostics).has("7186174527959780640"), true);
  const selected = selectExactTailGapCollectTargets(queue, exactGapIds, actionable, stub);
  assert.equal(selected.length, 1, "exact tail-gap select must bypass displayed-profile cap semantics");
  assert.equal(
    shouldExactTailGapPreSkipFail({
      hybridExactTailGapActive: true,
      exactGapIds,
      preSkipPending: selected.length,
      profileRemaining: 1
    }),
    false
  );
}

console.info("hybridExactTailGapPreSkip.test.ts: PASS");
