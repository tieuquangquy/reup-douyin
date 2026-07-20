# Frame sampling Phase 1 (Cloud Run ready)

Independent frame extraction for OCR Phase 1. Two backends:

| Backend | Env | Behavior |
|---------|-----|----------|
| **text_onnx** (default for ANALYZE_OCR worker) | `OCR_FRAME_BACKEND=text_onnx` | OpenCV scan every 5 frames (~6fps) + local DBNet ONNX; keep JPEG only when **new** text boxes appear (IoU &lt; 0.1 vs previous). Progress via tqdm. |
| **ffmpeg_fps** (rollback / Cloud Run Alpine image) | `OCR_FRAME_BACKEND=ffmpeg_fps` | STRICT FFmpeg `fps=1\|2` grid + thumbnail + EOF still. |

Never dumps every source frame.

## Module

- `apps/api/src/media_pipeline/frame_sampling/`
  - `extract_phase1_frames(...)` — router used by hardsub E2E / OCR adapter
  - `extract_video_frames(video_source, output_dir, sample_fps=1|2) -> list[Path]` — FFmpeg only
  - `text_change_sampler.extract_text_change_keyframes` — ONNX text-change keyframes
  - `local_text_detector.LocalTextDetector` — DBNet det-only via onnxruntime
  - `ensure_dbnet_model.ensure_dbnet_onnx` — download `apps/api/models/dbnet.onnx` if missing
  - `run_frame_sampling_job(...)` — serverless job payload/result (FFmpeg path)
  - `cloud_run_entry.py` — env batch or minimal HTTP (`PORT`) for Cloud Run scale-to-zero

### Model download

```powershell
cd apps\api
$env:PYTHONPATH="."
python -c "from src.media_pipeline.frame_sampling.ensure_dbnet_model import ensure_dbnet_onnx; print(ensure_dbnet_onnx())"
```

Override URL: `DBNET_ONNX_URL=https://...`

## OCR adapter

`ocr_pipeline/frame_sampler.py` delegates to `extract_phase1_frames`.

## Call examples

```python
from src.media_pipeline.frame_sampling import extract_video_frames, extract_phase1_frames, run_frame_sampling_job
from src.media_pipeline.frame_sampling.job import FrameSamplingJobRequest

# Default: text_onnx (set OCR_FRAME_BACKEND=ffmpeg_fps to force grid)
frames = extract_phase1_frames("/data/clip.mp4", "/tmp/frames")

paths = extract_video_frames("/data/clip.mp4", "/tmp/frames", sample_fps=1)

result = run_frame_sampling_job(
    FrameSamplingJobRequest(video_source="https://…/clip.mp4", output_dir="/tmp/frames", sample_fps=2)
)
```

Cloud Run Jobs (env) — keep **ffmpeg_fps** (Alpine image has no onnxruntime):

```text
VIDEO_SOURCE=...
OUTPUT_DIR=/tmp/frames
SAMPLE_FPS=1
OCR_FRAME_BACKEND=ffmpeg_fps
python -m src.media_pipeline.frame_sampling.cloud_run_entry
```

HTTP (Cloud Run Service):

```text
python -m src.media_pipeline.frame_sampling.cloud_run_entry serve
```

## Docker (Alpine / Cloud Run)

Dockerfile: `apps/api/src/media_pipeline/frame_sampling/Dockerfile`  
Requirements (stdlib-only): cùng thư mục `requirements.txt`

### Build (lệnh chuẩn — context = `frame_sampling`)

```powershell
cd apps\api\src\media_pipeline\frame_sampling
docker build -t frame-extractor .
```

Image runtime dùng **FFmpeg tự biên dịch tối giản** (decode H.264 + `fps` + JPEG), không `apk add ffmpeg` full → thực tế ~**84MB** (`docker images`), dưới ngưỡng 100MB.

Cấu trúc trong image:

```text
/app/
  requirements.txt
  src/
    __init__.py
    media_pipeline/
      __init__.py
      frame_sampling/   # toàn bộ module Phase 1
```

`PYTHONPATH=/app` → import `src.media_pipeline.frame_sampling` khớp code local.

### Chạy local (giống Cloud Run Jobs)

```powershell
docker run --rm `
  -e VIDEO_SOURCE="https://example.com/clip.mp4" `
  -e OUTPUT_DIR=/tmp/frames `
  -e SAMPLE_FPS=1 `
  reup-frame-sampling:phase1
```

Hoặc mount video local:

```powershell
docker run --rm `
  -v C:\path\to\videos:/data:ro `
  -e VIDEO_SOURCE=/data/clip.mp4 `
  -e OUTPUT_DIR=/tmp/frames `
  -e SAMPLE_FPS=2 `
  reup-frame-sampling:phase1
```

### Cloud Run Jobs (gợi ý)

1. Push image lên Artifact Registry  
2. Tạo Job với env `VIDEO_SOURCE`, `OUTPUT_DIR=/tmp/frames`, `SAMPLE_FPS=1|2`  
3. CMD mặc định trong image đã là worker job (không cần ghi đè trừ khi chuyển sang HTTP `serve`)

**Không** build từ `apps/api` với Dockerfile cũ (apk ffmpeg full ~280MB). Dùng lệnh `docker build -t frame-extractor .` trong thư mục `frame_sampling` như trên.