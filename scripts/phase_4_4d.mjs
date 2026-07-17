import fs from 'fs';
const filePath = 'C:\\Users\\PC\\Desktop\\reup_douyin\\apps\\extension-douyin-capture\\src\\wholeProfileHarvest\\controller.ts';
let content = fs.readFileSync(filePath, 'utf-8');

const startMarker = 'let probeAwemeId: string | null = actionableTargets[0]?.aweme_id ?? null;';
const endMarker = 'const finishedAt = now();';

const startIdx = content.indexOf(startMarker);
const endIdx = content.indexOf(endMarker);

if (startIdx === -1 || endIdx === -1) {
  console.error('ERROR: markers not found');
  process.exit(1);
}

const endPos = endIdx + endMarker.length;
const before = content.substring(0, startIdx);

const replacement = `let probeAwemeId: string | null = actionableTargets[0]?.aweme_id ?? null;
  // Phase 4.4d: resolve caches ONCE, loop over all targets, batch flush.
  let tabId: number | null = null;
  try { const tab = await withTimeoutRace(runtime.getActiveTab(), 3_000, () => new Error("get_active_tab_timeout")); tabId = typeof tab.id === "number" ? tab.id : null; } catch {}
  hybridFossilUpdate({ hybrid_runner_tab_resolved: tabId != null ? "yes" : "no" });
  state = { ...state, debug: { ...state.debug, last_response_summary: { ...(typeof state.debug.last_response_summary === "object" ? state.debug.last_response_summary as Record<string, unknown> : {}), hybrid_runner_tab_resolved: tabId != null ? "yes" : "no" } } };
  await writeWholeProfileHarvestState(runtime.storage, state).catch(() => undefined);

  let rawNetworkCache: unknown[] = [];
  if (tabId !== null && runtime.readNetworkCacheFromTab) { rawNetworkCache = await withTimeoutRace(runtime.readNetworkCacheFromTab(tabId).catch(() => [] as unknown[]), 5_000, () => [] as unknown[]); }
  const networkCacheByAwemeId = new Map<string, unknown>();
  for (const item of rawNetworkCache) { if (item && typeof item === "object" && "aweme_id" in item && typeof (item as Record<string, unknown>).aweme_id === "string") { networkCacheByAwemeId.set((item as Record<string, unknown>).aweme_id as string, item); } }
  hybridFossilUpdate({ hybrid_runner_cache_read_ok: (tabId !== null && typeof runtime.readNetworkCacheFromTab === "function") ? "yes" : "not_attempted", hybrid_runner_cache_entries: rawNetworkCache.length });

  let passiveDiagnostics: Record<string, unknown> = {};
  if (tabId !== null && runtime.readPassiveProbeDiagnosticsFromTab) { passiveDiagnostics = await withTimeoutRace(runtime.readPassiveProbeDiagnosticsFromTab(tabId).catch(() => ({}) as Record<string, unknown>), 5_000, () => ({}) as Record<string, unknown>); }
  const probeRec = (passiveDiagnostics.probe && typeof passiveDiagnostics.probe === "object" ? passiveDiagnostics.probe : passiveDiagnostics) as Record<string, unknown>;
  const passiveByAwemeId = new Map<string, Record<string, unknown>>();
  for (const arr of [probeRec.network_profile_post_targets, probeRec.network_favorite_targets, probeRec.network_other_aweme_targets]) { if (Array.isArray(arr)) for (const t of arr as Array<{ aweme_id?: string }>) { if (typeof t.aweme_id === "string") passiveByAwemeId.set(t.aweme_id, t as Record<string, unknown>); } }

  const flushBatch: FullModalHarvestItemPayload[] = [];
  for (const target of actionableTargets) {
    loopAttemptedCount++;
    const sources: HybridHydrationSourceBundle = { profile_repository: target.profile_card_evidence ?? null, network_cache: (networkCacheByAwemeId.get(target.aweme_id) as unknown as import("../types.js").NetworkVideoMetadata | undefined) ?? null, passive_aweme: (passiveByAwemeId.get(target.aweme_id) as unknown as import("../types.js").PassiveNetworkProbeStoredTarget22C12A | undefined) ?? null, profile_post_api: null, calibrated_non_modal_dom: null };
    const hydration = hydrateNonModalForAwemeId(target.aweme_id, sources);
    if (hydration.pending_reason) { loopPendingCount++; continue; }
    const finalized = buildFinalizedMetadataFromHybridHydration(hydration, { profile_url: profileUrl });
    if (!finalized) continue;
    loopFinalizedCount++;
    flushBatch.push(finalized);
    if (flushBatch.length >= flushChunkSize && captureSessionId && runtime.flushCanonicalHarvestPayload) { const ok = await flushHybridBatch(runtime, flushBatch, captureSessionId, runId, profileUrl, startedAt); if (ok) loopWriteOkCount += flushBatch.length; else loopWriteFailCount += flushBatch.length; flushBatch.length = 0; }
  }
  if (flushBatch.length > 0 && captureSessionId && runtime.flushCanonicalHarvestPayload) { const ok = await flushHybridBatch(runtime, flushBatch, captureSessionId, runId, profileUrl, startedAt); if (ok) loopWriteOkCount += flushBatch.length; else loopWriteFailCount += flushBatch.length; flushBatch.length = 0; }

  const overallOk = loopWriteOkCount > 0;
  const probeSourcesUsed = selectedAwemeIds.length > 0 ? ["profile_repository", "network_cache"] : [];
  const finishedAt = now();`;

const after = content.substring(endPos);
content = before + replacement + after;

fs.writeFileSync(filePath, content, 'utf-8');
console.log('OK: Phase 4.4d loop code inserted.');
