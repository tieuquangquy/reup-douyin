# OCR filtering Phase 2



Independent module: OCR sampled frames → **keep only bottom 1/3** subtitle boxes.



## Module



`apps/api/src/media_pipeline/ocr_filtering/`



- `run_ocr_filtering(frame_paths: list[Path], ...) -> OcrFilteringResult`

- Filter: box **center_y** must be in the lower third (`BOTTOM_BAND_RATIO = 1/3`)

- Providers: `RestOcrEndpointProvider` (reads `OCR_ENDPOINT_URL`), `MockOcrProvider`, wrapped by `RetryingOcrProvider`

- Output: `result.to_dict()` JSON with `frame_id`, `time_ms`, filtered `x/y/width/height`



## Cloud Run endpoint



1. Deploy + wire `.env` (repo root):



```bash

python deploy/hf-paddle-ocr/auto_deploy.py

```



2. Env (no hardcode in Phase 2):



```text

OCR_ENDPOINT_URL=https://YOUR_SERVICE_URL/predict

```



`RestOcrEndpointProvider` uses `os.environ.get("OCR_ENDPOINT_URL")` (and loads repo `.env` if needed), then `requests.post` multipart `file=` (.jpg) to that URL.



## Example



```python

from pathlib import Path

from src.media_pipeline.frame_sampling import extract_video_frames

from src.media_pipeline.ocr_filtering import run_ocr_filtering

from src.media_pipeline.ocr_filtering.providers import MockOcrProvider, RetryingOcrProvider



frames = extract_video_frames("clip.mp4", "/tmp/frames", sample_fps=1)

result = run_ocr_filtering(

    frames,

    ocr_provider=RetryingOcrProvider(MockOcrProvider()),  # or default RestOcrEndpointProvider

    frame_time_ms=[i * 1000 for i in range(len(frames))],

)

print(result.to_dict())

```



Without `OCR_ENDPOINT_URL`, `build_default_ocr_provider()` falls back to mock (dev only).

Set `OCR_FILTERING_USE_MOCK=true` to force mock.


