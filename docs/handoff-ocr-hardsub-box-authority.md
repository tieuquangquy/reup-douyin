# Handoff: OCR hardsub box authority (prototype)

Paste / attach this file when starting a new chat about Analyze OCR → hard-sub clean boxes.

**Date:** 2026-07-20 (v4b)  
**Scope:** Prototype only — **not** wired into production `ANALYZE_OCR` / blur / burn-in yet.  
**Test video:** source `0014c4b6` (~759 frames, ~29s cooking hardsub).

---

## Goal

Accurate per-frame text boxes for blur/sub. Prefer **Cloud OCR as authority**, not local DBNet.

## Decisions locked in (v4b)

| Decision | Why |
|----------|-----|
| **Hard-band OCR + mid-title band (early only)** | Full-frame + aggressive snap moved mid titles to bottom (f0) |
| **Never snap mid-title** (`MID_TITLE_Y_MAX=0.65`) | Mid zone must not overlap hardsub band |
| **Snap band-stuck hardsubs** (`cy≈0.67–0.85` → bottom strip) | Hard-band OCR often returns correct CJK at band top; old `hardsub_min_center_y` dropped them → empty ticks |
| **Bottom-band change ticks** (`y0≈0.85`, MAE≥18, gap≥800ms) | Blind 2fps misses; full bottom-third MAE spams from wok motion |
| **`densify(..., skip_empty=True)`** | Empty OCR tick wiped hold-forward |
| Overlay labels via **PIL CJK** | OpenCV `putText` → `????` |
| `OCR_ASYNC_CONCURRENCY=2` + 429 retry | Quota |

---

## Architecture (v4)

```text
bottom-band pixel change ticks (y≥0.85) + forced overlay QA frames
  → Cloud OCR: hard band (+ mid band only t≤2500ms)
  → clean_box_authority (band-stuck snap; no mid snap)
  → densify hold-forward (skip empty)
  → JSON + overlay JPGs
```

### Key files

| Path | Role |
|------|------|
| `ocr_filtering/ocr_track_prototype.py` | CLI prototype |
| `ocr_filtering/bottom_band_change_ticks.py` | Change-driven OCR times |
| `ocr_filtering/clean_box_authority.py` | Filter + repair |
| `ocr_filtering/box_timeline_tracker.py` | Hold-forward densify |
| `ocr_filtering/overlay_zones.py` | `MID_TITLE_Y_MAX=0.65` |
| `ocr_filtering/async_batch.py` | Concurrency 2, dotenv, 429 |

### Tests

- `test_clean_box_authority.py` — mid not snapped; band-stuck snaps
- `test_box_timeline_tracker.py` — skip_empty
- `test_bottom_band_change_ticks.py`
- `test_overlay_zones.py`

---

## Latest artifacts (`apps/api/`)

| Path | Meaning |
|------|---------|
| **`tmp_ocr_v4b_overlays_0014c4b6/`** | **Latest QA** (reprocess raw + band-stuck fix) |
| **`tmp_ocr_v4b_0014c4b6.json`** | Latest JSON |
| `tmp_ocr_v4_*` | Same OCR raw; clean before band-stuck fix |
| `tmp_ocr_v3_*` | Prior full+band (f0 title wrongly at bottom) |

### v4b QA snapshot

| Frame | Result |
|-------|--------|
| f0 | Mid title + kcal boxed at correct mid Y |
| f119 | Hardsub held/updated |
| f221 | Hardsub OK `cy≈0.96` |
| f327 | Hardsub line present (merged text order may be messy) |
| f436 / f449 | Seasoning hardsub kept (was empty / stale in v3–v4) |
| f536 / f643 | Hardsub OK |

**Still imperfect:** OCR string quality / merge order; box width sometimes short of full line; hold can lag one caption behind until next good tick.

---

## How to re-run

```powershell
cd apps/api
$env:PYTHONPATH = (Get-Location).Path
# load worker .env OCR_* then:
python -m src.media_pipeline.ocr_filtering.ocr_track_prototype `
  --video "<path-to-*nl.mp4>" `
  --out tmp_ocr_v4_0014c4b6.json `
  --overlay-dir tmp_ocr_v4_overlays_0014c4b6 `
  --overlay-indices 0,119,221,327,436,449,536,643 `
  --concurrency 2
```

Flags: `--fixed-fps`, `--full-frame`, `--no-mid-title`, `--dual-band` (legacy).

Offline re-clean without Cloud OCR: load `ocr_observations_raw` → `apply_temporal_consensus` → `densify_hold_forward(..., skip_empty=True)` → `_write_overlays`.

---

## Non-goals

- Not wired into production ANALYZE_OCR / blur yet.
- Do not raise OCR concurrency above 2 casually.

## Suggested next

1. Ink / edge refine box width to full hardsub line after OCR.
2. On high MAE change tick: if cleaned empty after band-stuck repair, OCR ±neighbor frames.
3. When quality accepted: propose production chokepoint (proposal first per `RULE.md`).
