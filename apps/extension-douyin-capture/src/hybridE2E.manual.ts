// Manual end-to-end test for the Hybrid network-cache collection path.
// Bypasses the extension runtime (no Chrome, no flag, no heartbeat). Runs the
// SAME pure hydration + finalized builder the runner uses, then POSTs to the
// real backend and verifies the row. Run with:
//   npx tsx src/_hybridE2E.manual.ts
//
// Requires: backend running at API_BASE (default http://127.0.0.1:8000)
// and a dump file at repo-root _test_cache.json produced from a Douyin profile tab.

import { readFileSync } from "node:fs";
import {
  hydrateNonModalForAwemeId,
  buildFinalizedMetadataFromHybridHydration,
  type HybridHydrationSourceBundle
} from "./wholeProfileHarvest/hybridHydration.js";
import type { NetworkVideoMetadata } from "./types.js";

const API_BASE = process.env.API_BASE ?? "http://127.0.0.1:8000";
const CACHE_FILE = process.env.CACHE_FILE ?? "C:/Users/PC/Desktop/reup_douyin/_test_cache.json";
const ITEM_COUNT = Number(process.env.ITEM_COUNT ?? "5");

function line(tag: string, msg: string) {
  console.log(`${tag} ${msg}`);
}

async function main() {
  // ---- Load dump ----
  const raw = readFileSync(CACHE_FILE, "utf-8");
  const parsed = JSON.parse(raw) as { cache: NetworkVideoMetadata[]; profile_url: string };
  const cache = Array.isArray(parsed.cache) ? parsed.cache : [];
  const profileUrl = parsed.profile_url ?? null;
  line("[load]", `cache_items=${cache.length} profile_url=${profileUrl ?? "null"}`);
  if (!cache.length) {
    line("RESULT:", "FAIL — _test_cache.json has no cache items.");
    return;
  }

  // ---- Create a capture session against the real backend ----
  let captureSessionId: string | null = null;
  try {
    const sessionRes = await fetch(`${API_BASE}/douyin-extension/capture-session`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        schema_version: "douyin_extension_capture_session.v1",
        profile_url: profileUrl,
        capture_source: "whole_profile_harvest",
        detected_page_type: "profile_page"
      })
    });
    const sessionBody = await sessionRes.json().catch(() => ({}));
    captureSessionId = sessionBody?.session_id ?? null;
    line("[session]", `status=${sessionRes.status} session_id=${captureSessionId ?? "null"}`);
  } catch (e) {
    line("[session]", `ERROR creating session: ${String(e)} (continuing without session)`);
  }

  // ---- Iterate first N items ----
  const n = Math.min(ITEM_COUNT, cache.length);
  let hydrationOk = 0;
  let finalizedOk = 0;
  let writeOk = 0;
  let verifyOk = 0;
  const failures: string[] = [];

  for (let i = 0; i < n; i += 1) {
    const item = cache[i];
    if (!item) {
      failures.push(`index_${i}: item is undefined in cache`);
      line(`[${i + 1}/${n}]`, `INDEX_${i} item_undefined`);
      continue;
    }
    const awemeId = item.aweme_id;
    const bundle: HybridHydrationSourceBundle = {
      profile_repository: null,
      network_cache: item,
      passive_aweme: null,
      profile_post_api: null,
      calibrated_non_modal_dom: null
    };

    // 1) Hydration
    const hydration = hydrateNonModalForAwemeId(awemeId, bundle);
    if (!hydration.pending_reason) {
      hydrationOk += 1;
    } else {
      failures.push(`${awemeId}: hydration pending=${hydration.pending_reason} missing=[${hydration.missing_required_fields.join(",")}]`);
      line(`[${i + 1}/${n}]`, `aweme=${awemeId} HYDRATION_PENDING missing=[${hydration.missing_required_fields.join(",")}] sources_used=[${hydration.sources_used.join(",")}]`);
      continue;
    }

    // 2) Finalized payload
    const finalizedItem = buildFinalizedMetadataFromHybridHydration(hydration, { profile_url: profileUrl });
    if (!finalizedItem) {
      failures.push(`${awemeId}: finalized=null despite no pending_reason`);
      line(`[${i + 1}/${n}]`, `aweme=${awemeId} FINALIZED_NULL`);
      continue;
    }
    finalizedOk += 1;
    line(`[${i + 1}/${n}]`, `aweme=${awemeId} OK dur=${finalizedItem.raw_dom_detail_metrics?.duration_seconds} like=${finalizedItem.raw_dom_detail_metrics?.like_count} fav=${finalizedItem.raw_dom_detail_metrics?.favorite_count} share=${finalizedItem.raw_dom_detail_metrics?.share_count} view=${finalizedItem.view_count} est_views=${finalizedItem.estimated_views} sources=[${hydration.sources_used.join(",")}]`);

    // 3) Backend write
    const payload = {
      schema_version: "douyin_full_modal_harvest.v1",
      capture_session_id: captureSessionId,
      profile_url: profileUrl,
      commit_policy: "finalized_only",
      items: [finalizedItem],
      progress: { total: 1, completed: 1, failed: 0 }
    };
    try {
      const writeRes = await fetch(`${API_BASE}/douyin-extension/full-modal-harvest`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
      const writeBody = await writeRes.json().catch(() => ({}));
      if (writeRes.ok) {
        writeOk += 1;
        line(`     `, `WRITE ${writeRes.status} created=${writeBody?.created_count ?? "?"} updated=${writeBody?.updated_count ?? "?"} failed=${writeBody?.failed_count ?? "?"} effective=${writeBody?.beta_write_effective_status ?? "?"}`);
      } else {
        failures.push(`${awemeId}: write status=${writeRes.status} body=${JSON.stringify(writeBody).slice(0, 300)}`);
        line(`     `, `WRITE_FAIL ${writeRes.status} body=${JSON.stringify(writeBody).slice(0, 300)}`);
        continue;
      }
    } catch (e) {
      failures.push(`${awemeId}: write threw ${String(e)}`);
      line(`     `, `WRITE_THREW ${String(e)}`);
      continue;
    }

    // 4) Verify
    try {
      const verifyRes = await fetch(`${API_BASE}/douyin-extension/capture-inbox/items/verify`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ aweme_ids: [awemeId], capture_session_id: captureSessionId, limit: 10 })
      });
      const verifyBody = await verifyRes.json().catch(() => ({}));
      const found = (verifyBody?.found_count ?? 0) > 0;
      if (found) {
        verifyOk += 1;
        line(`     `, `VERIFY OK found=${verifyBody?.found_count} missing=${verifyBody?.missing_count}`);
      } else {
        failures.push(`${awemeId}: verify found_count=0`);
        line(`     `, `VERIFY_FAIL found=0 body=${JSON.stringify(verifyBody).slice(0, 200)}`);
      }
    } catch (e) {
      failures.push(`${awemeId}: verify threw ${String(e)}`);
      line(`     `, `VERIFY_THREW ${String(e)}`);
    }
  }

  console.log("\n===== SUMMARY =====");
  console.log(`items_tested:   ${n}`);
  console.log(`hydration_ok:   ${hydrationOk}/${n}`);
  console.log(`finalized_ok:   ${finalizedOk}/${n}`);
  console.log(`backend_write_ok: ${writeOk}/${n}`);
  console.log(`verify_ok:      ${verifyOk}/${n}`);
  if (failures.length) {
    console.log("\n--- failures ---");
    failures.forEach((f) => console.log("  " + f));
  }
  const pass = hydrationOk === n && finalizedOk === n && writeOk === n && verifyOk === n;
  console.log(`\nRESULT: ${pass ? "PASS — Hybrid end-to-end works for all tested items." : "PARTIAL/FAIL — see failures above."}`);
}

main().catch((e) => {
  console.error("FATAL:", e);
  process.exit(1);
});
