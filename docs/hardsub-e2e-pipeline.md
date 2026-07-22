# Hard-sub E2E orchestrator

Shared core: `apps/api/src/media_pipeline/hardsub_e2e.py` — Phase 1 → 2 → 2.5 → 3+4.

Used by:

- CLI: `apps/api/src/main_pipeline.py` (`python -m src.main_pipeline`)
- Final Review: `OcrPipelineService` when `clean_hardsub=True`

## Phases

1. `extract_video_frames_detailed` (1|2 fps) — still used for legacy/default OCR path and render plate
2. OCR:
   - **`OCR_QUALITY_PROFILE=best`:** `run_per_frame_position_authority` (Authority V3.6, **full video timeline**, sparse Cloud + local mid-title/hardsub)
   - **default:** `run_ocr_filtering` (bottom band crop → parallel REST OCR → probe early-exit; `OCR_ENDPOINT_URL`)
3. `translate_subtitles` (Ops **Caption AI** / env)
4. `render_video_single_pass` (one FFmpeg command)

Temp frames are always deleted in `finally` unless `keep_temp=True`. If Phase 2 finds no boxes, translate/render are skipped and `output_path` is empty.

## Authority V3.6 full-duration box QA (no blur)

Prefer this before enabling blur/render review. Same function as E2E best profile:

```powershell
cd apps/api
$env:PYTHONPATH = "src;."
python -m src.media_pipeline.ocr_filtering.per_frame_position_authority `
  --video path\to\clip.mp4 `
  --out tmp_ocr_v36_run\ocr-authority-v3.6.json `
  --ocr-cache tmp_ocr_v36_run\ocr-cache.json `
  --overlay-dir tmp_ocr_v36_run\overlays_full_duration `
  --overlay-all
```

See also `docs/ocr-hardsub-pipeline.md` (section Authority V3.6).

## Run (CLI E2E with blur)

```bash
cd apps/api
# Best profile → V3.6 full-duration authority in Phase 2
set OCR_QUALITY_PROFILE=best
python -m src.main_pipeline --video path\to\clip.mp4 --out out_hardsub.mp4 --fps 1
# dry OCR (skips V3.6 Cloud path):
python -m src.main_pipeline --video clip.mp4 --out out.mp4 --mock-ocr
```

```python
from src.main_pipeline import run_pipeline

run_pipeline("in.mp4", "out.mp4", sample_fps=1)
```
