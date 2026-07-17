import fs from 'fs';
const filePath = 'C:\\Users\\PC\\Desktop\\reup_douyin\\apps\\extension-douyin-capture\\src\\wholeProfileHarvest\\controller.ts';
let content = fs.readFileSync(filePath, 'utf-8');

// Find the "const finishedAt = now();" right after "const probeSourcesUsed"
const probeSourcesUsedMarker = `const probeSourcesUsed = selectedAwemeIds.length > 0 ? ["profile_repository", "network_cache"] : [];`;
const finishedMarker = `const finishedAt = now();`;
const startIdx = content.indexOf(probeSourcesUsedMarker);
const finishedIdx = content.indexOf(finishedMarker, startIdx);

if (startIdx === -1 || finishedIdx === -1) {
  console.error('Markers not found');
  process.exit(1);
}

// Delete everything between probeSourcesUsed line end and the end of the garbage
// We want to keep: probeSourcesUsed... + finishedAt = now(); + the FOSSIL code after
// The garbage is all the scan_profile code that got appended

// Find the FOSSIL section that should follow
const fossilMarker = `// FOSSIL: final outcome`;
const fossilIdx = content.indexOf(fossilMarker, finishedIdx);

if (fossilIdx === -1) {
  console.error('FOSSIL marker not found - file may be corrupted');
  process.exit(1);
}

// Keep: everything up to finishedAt, then jump to fossilMarker
const before = content.substring(0, finishedIdx + finishedMarker.length);
const after = content.substring(fossilIdx);
content = before + '\n\n  ' + after;

const probeSucceededMarker = `  const probeSucceeded = probeBackendWriteOk === "yes";`;
const probeSucceededIdx = content.indexOf(probeSucceededMarker);
if (probeSucceededIdx !== -1) {
  // Replace from probeSucceededMarker to end with updated code
  // Actually we have overallOk now, not probeBackendWriteOk
  
  // Just delete the line since these variables are gone
  content = content.replace(`  const probeSucceeded = probeBackendWriteOk === "yes";\n`, '');
  
  // Fix the finishPersistentCollectJob call below
  content = content.replace(
    `  state = finishPersistentCollectJob(state, finishedAt, "completed", null, false, {
    attempted_count: probeBackendWriteCalled === "yes" ? 1 : 0,
    succeeded_count: probeVerifyOk === "yes" ? 1 : 0,
    failed_count: probeBackendWriteCalled === "yes" && probeVerifyOk !== "yes" ? 1 : 0,
    skipped_count: 0
  });`,
    `  state = finishPersistentCollectJob(state, finishedAt, "completed", null, false, {
    attempted_count: loopAttemptedCount,
    succeeded_count: loopWriteOkCount,
    failed_count: loopWriteFailCount,
    skipped_count: loopPendingCount
  });`
  );
  
  // Fix the completion line
  content = content.replace(
    `      completed_at: finishedAt,
        last_error: probeSucceeded ? null : (probeBackendWriteCalled === "yes" && probeVerifyOk !== "yes" ? "hybrid_runner_write_ok_verify_failed" : "hybrid_runner_no_target_processed")`,
    `      completed_at: finishedAt,
        last_error: overallOk ? null : (loopAttemptedCount > 0 ? "hybrid_runner_loop_failed" : "hybrid_runner_no_target_processed")`
  );
  
  content = content.replace(
    `      status: probeSucceeded ? ("completed" as const) : ("completed_with_warnings" as const),`,
    `      status: overallOk ? ("completed" as const) : ("completed_with_warnings" as const),`
  );
  
  content = content.replace(
    `        hybrid_runner_probe_sources_attempted: probeSourcesAttempted,`,
    `        hybrid_runner_probe_sources_attempted: probeSourcesUsed,`
  );
}

fs.writeFileSync(filePath, content, 'utf-8');
console.log('OK: Cleaned up and fixed references.');
