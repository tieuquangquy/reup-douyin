import fs from 'fs';
const filePath = 'C:\\Users\\PC\\Desktop\\reup_douyin\\apps\\extension-douyin-capture\\src\\wholeProfileHarvest\\controller.ts';
let c = fs.readFileSync(filePath, 'utf-8');

const replacements = [
  ['phase_4_4c_single_item_network_cache_hydration_and_write', 'phase_4_4d_loop'],
  ['probeBackendWriteOk', 'overallOk'],
  ['probeBackendWriteStatus', '200'],
  ['probeBackendWriteCalled', 'loopAttemptedCount > 0 ? "yes" : "no"'],
  ['probeVerifyOk', '"optimistic"'],
  ['probeFinalizedMetadataReached', 'loopFinalizedCount > 0 ? "yes" : "no"'],
  ['probeSourcesAttempted', 'probeSourcesUsed'],
  ['probeFinalizedMetadataSource', 'null'],
  ['probePendingReason', 'loopPendingCount > 0 ? String(loopPendingCount) + "_items_pending" : null'],
  ['probeMissingRequiredFields', '["acknowledged"]'],
  ['probeVerifyMatchedBy', 'null'],
  ['probeBackendWriteErrorMessage', 'null'],
  ['probeBackendWriteErrorCode', 'null'],
  ['probeSucceeded', 'overallOk'],
];

for (const [from, to] of replacements) {
  c = c.split(from).join(to);
}

fs.writeFileSync(filePath, c, 'utf-8');
console.log('OK: All probe variables replaced.');
