# Douyin Factor 0B Grid Scope Resume

## Scope-locked objective

Fix only active grid discovery scoping + count integrity for Douyin profile capture. Do not broaden into thumbnail/duration/stats/UI/pipeline redesign.

## Audit conclusions

- Current discovery overreach is caused by document-wide `/video/` link scanning in:
  - [`collectVideoLinks()`](apps/extension-douyin-capture/src/extractor.ts:163)
  - [`collectVideoLinks()`](apps/extension-douyin-capture/src/popupTransport.ts:410)
- Neither path first identifies the active profile works-grid root.
- Eligibility checks are too weak for hidden/inactive/modal/preload links.
- Dedupe exists by `aweme_id` but only after broad candidate collection, so stray unique IDs can still inflate count.

## Final implementation status

1. ✅ Added active works-grid root detection in [`findActiveWorksGridRoot()`](apps/extension-douyin-capture/src/extractor.ts:229) and mirrored in [`popupTransport.ts`](apps/extension-douyin-capture/src/popupTransport.ts:457).
2. ✅ Scoped candidate link collection through [`collectVideoLinks(root)`](apps/extension-douyin-capture/src/extractor.ts:206) and mirrored direct path [`collectVideoLinks(root)`](apps/extension-douyin-capture/src/popupTransport.ts:442).
3. ✅ Added strict tile eligibility/reject reasons in [`discoveryRejectReason()`](apps/extension-douyin-capture/src/extractor.ts:243) and direct mirror.
4. ✅ Added count-integrity diagnostics (`candidate`, `eligible`, `deduped`, `rejected`, reason counts) in extractor + direct fallback diagnostics payloads.
5. ✅ Mirrored scoped discovery behavior in direct execution fallback [`runDouyinActionInPage()`](apps/extension-douyin-capture/src/popupTransport.ts:167).
6. ✅ Updated focused tests:
   - signature parity assertion in [`extractor.test.ts`](apps/extension-douyin-capture/src/extractor.test.ts:68)
   - duplicate-anchor count-integrity diagnostics assertion in [`extractor.identity.test.ts`](apps/extension-douyin-capture/src/extractor.identity.test.ts:217)
7. ✅ Verification complete: `npm run test --workspace apps/extension-douyin-capture` passed fully.

## Success criteria result

- ✅ Discovery is no longer a broad acceptance pass over document links by default.
- ✅ Active-grid scoped behavior is enforced where root is identifiable.
- ✅ Stray/out-of-scope/non-eligible links are rejected with explicit reason accounting.
- ✅ Duplicate-anchor inflation is blocked and measured.
- ✅ Extractor and direct fallback remain behaviorally aligned.
