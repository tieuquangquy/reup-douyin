# Hard-sub E2E orchestrator

Shared core: `apps/api/src/media_pipeline/hardsub_e2e.py` — Phase 1 → 2 → 2.5 → 3+4.

Used by:

- CLI: `apps/api/src/main_pipeline.py` (`python -m src.main_pipeline`)
- Final Review: `OcrPipelineService` when `clean_hardsub=True`

## Phases

1. `extract_video_frames_detailed` (1|2 fps)
2. `run_ocr_filtering` (bottom band crop → parallel REST OCR → probe early-exit; `OCR_ENDPOINT_URL`)
3. `translate_subtitles` (Ops **Caption AI** / env)
4. `render_video_single_pass` (one FFmpeg command)

Temp frames are always deleted in `finally` unless `keep_temp=True`. If Phase 2 finds no boxes, translate/render are skipped and `output_path` is empty.

## Run (CLI)

```bash
cd apps/api
python -m src.main_pipeline --video path\to\clip.mp4 --out out_hardsub.mp4 --fps 1
# dry OCR:
python -m src.main_pipeline --video clip.mp4 --out out.mp4 --mock-ocr
```

```python
from src.main_pipeline import run_pipeline

run_pipeline("in.mp4", "out.mp4", sample_fps=1)
```
