# Analyze OCR V29 (historical)

> Superseded by the frontend-default OCR-V34 recipe. This document is retained
> only for audit history; new frontend and auto-queue jobs must not bind V29.

`OCR-V29` was the official local-only Analyze OCR recipe used by the frontend
durable `ANALYZE_OCR` job. It preserves the v58 candidate Phase-1 authority and
keeps Authority V3.6 full-duration disabled.

This document is retained for audit history. `OCR-V34` supersedes V29 for all
new frontend and Reup Queue jobs.

V29 closes five general failure classes reported in rendered output:

- residual discovery is budgeted per spatial-temporal candidate epoch, so a
  short editor overlay cannot be starved by persistent scene texture;
- dense source UI provenance never propagates to hardsub geometry merely
  because both are visible on the same frames;
- DBNet contour orientation is retained long enough to build a conservative
  envelope for italic/rotated glyphs;
- cover timing uses an FPS-scaled transition hold and continuous explicit
  concealment intervals;
- overlapping tracks in one visual epoch are unioned and reconstructed once,
  and output QA keeps active cover transitions in its flicker verdict.

The OCR/detection path remains fully local. No network or model API call was
introduced. Translation remains a separate downstream concern.

The frontend path is unchanged:

```text
Frontend -> POST /ocr -> durable ANALYZE_OCR job -> worker
-> QualityLocalizationService.run_phase12 -> MasterPhase1Extractor
```

The runtime recipe is content-addressed through
`docs/pipeline-recipes/analyze_ocr_recipe_current.json`; every new job binds its
immutable V29 hash, preventing V28 artifacts from being reused as V29 output.
