# OCR / Hard-sub pipeline (Pilot A + media E2E)

Final Review **Analyze OCR / clean hard-sub** (`clean_hardsub=True`, default) runs full Phase 1–4 via `media_pipeline.hardsub_e2e`: sample → REST/mock OCR (bottom band) → Caption AI translate → single-pass FFmpeg (mask + VI burn + anti-hash) → `CLEANED_VIDEO`.

`clean_hardsub=False` keeps the events-only path (legacy band crop + local OCR provider, no render).

## Flow (`clean_hardsub=True`)

1. `POST /ocr` → job `ANALYZE_OCR`
2. `OcrPipelineService` → `run_hardsub_phases_1_to_4` (shared with CLI `main_pipeline`)
3. Phase 1: sample frames (**STRICT 1 or 2 fps**)
4. Phase 2: OCR via `OCR_ENDPOINT_URL` / mock; keep bottom-band boxes
5. Phase 2.5: batch translate with Ops **Caption AI** (`caption_ai` / `caption_prompt` — not dialogue Translation settings)
6. Phase 3+4: one FFmpeg pass → cleaned MP4
7. Persist detections + `OCR_EVENTS` (includes `vi_texts`, `pipeline_backend=media_e2e_v1`) + `CLEANED_VIDEO` (`clean_method=single_pass_mask_vi_antihash`)
8. Checkpoint #3: review → Approve visual
9. Downstream TTS / `RENDER_FINAL` still prefer current `CLEANED_VIDEO` plate (may already have burned hard-sub VI)

## API

- `POST /ocr` — enqueue analyze + clean (E2E when `clean_hardsub`)
- `GET /source-videos/{id}/ocr-summary`
- `POST /source-videos/{id}/ocr-visual-approve`

## Non-goals

- OCR every frame at 30fps
- Auto-cover scene text (signs, clothes, logos)
- VSR / LaMa inpaint (upgrade later)
- Using dialogue Translation AI settings for hard-sub captions

## Ops / env

- Caption AI: `/ops/caption-ai`, `/ops/caption-prompt`
- OCR Cloud Run: `OCR_ENDPOINT_URL` (see `deploy/hf-paddle-ocr/`)
- Dry OCR: `OCR_FILTERING_USE_MOCK=1` or CLI `--mock-ocr`
- HTTP timeout to Cloud Run: default **300s** (`OCR_HTTP_TIMEOUT_SECONDS`) — cold start can exceed 120s
- Cold start: client polls `/health` up to **180s** (`OCR_WARMUP_DEADLINE_SECONDS`) before first `/predict`
- When OCR finds **0 hard-sub boxes**, job stays `COMPLETED` but sets `error_code=OCR_NO_HARDSUB_OUTPUT` + message on the job (Ops Jobs Error column / warn badge). No new `CLEANED_VIDEO` is written; prior plate is restored if any.
- **Perf (Phase 2 defaults):**
  - `OCR_CROP_BAND=1` — OCR only bottom subtitle band (smaller upload; boxes remapped to full frame)
  - `OCR_HTTP_CONCURRENCY=4` — parallel `/predict` calls (warmup is thread-safe)
  - `OCR_PROBE_STRIDE=2` — OCR every 2nd frame first; if probe empty → skip rest (`ocr_probe_empty_early_exit`)
  - `OCR_PROBE_EARLY_EXIT=1` — enable that skip (set `0` to always OCR every sampled frame)
- **Batch throughput:** during multi-video sessions set Cloud Run `--min-instances 1` (keep warm); idle → `0` for cost. See `deploy/hf-paddle-ocr/README_DEPLOY.md`.

## Related

- CLI orchestrator: `docs/hardsub-e2e-pipeline.md`
- Legacy timed drawbox util still in `ocr_pipeline/clean_hardsub.py` (not used on Final Review clean path)
