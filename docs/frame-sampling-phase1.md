# Frame sampling Phase 1 (Cloud Run ready)

Independent FFmpeg frame extraction at **STRICT 1 fps or 2 fps** only. Never dumps every frame.

## Module

- `apps/api/src/media_pipeline/frame_sampling/`
  - `extract_video_frames(video_source, output_dir, sample_fps=1|2) -> list[Path]`
  - `run_frame_sampling_job(...)` — serverless job payload/result
  - `cloud_run_entry.py` — env batch or minimal HTTP (`PORT`) for Cloud Run scale-to-zero

## OCR adapter

`ocr_pipeline/frame_sampler.py` delegates to this module (not deleted — still required by ANALYZE_OCR).

## Call examples

```python
from src.media_pipeline.frame_sampling import extract_video_frames, run_frame_sampling_job
from src.media_pipeline.frame_sampling.job import FrameSamplingJobRequest

paths = extract_video_frames("/data/clip.mp4", "/tmp/frames", sample_fps=1)

result = run_frame_sampling_job(
    FrameSamplingJobRequest(video_source="https://…/clip.mp4", output_dir="/tmp/frames", sample_fps=2)
)
```

Cloud Run Jobs (env):

```text
VIDEO_SOURCE=...
OUTPUT_DIR=/tmp/frames
SAMPLE_FPS=1
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