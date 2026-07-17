# Video renderer Phase 3+4 (Single Render)

One FFmpeg pass: cover Chinese hard-subs → burn Vietnamese → light anti-hash.

## Module

`apps/api/src/media_pipeline/video_renderer/`

| Piece | Role |
|-------|------|
| `overlays_from_ocr_payload` | Phase 2 `to_dict()` + VI map → timed `OverlaySegment` |
| `build_single_render_filter` | Layer1 `drawbox` + Layer2 `drawtext` + Layer3 `eq`/`noise` |
| `render_video_single_pass` | Exactly **one** `ffmpeg -filter_complex` invocation |

## Layers

1. **Mask** — timed `drawbox` fill on union of bottom-band boxes  
2. **Inject** — timed `drawtext` (VI), centered in the box  
3. **Anti-detection** — brightness/contrast/saturation ±1–2% + very light `noise`

## Example

```python
from src.media_pipeline.video_renderer import render_video_single_pass

render_video_single_pass(
    "clip.mp4",
    "out.mp4",
    ocr_payload=phase2_result.to_dict(),
    vi_texts={0: "Xin chào", 1000: "Phụ đề dịch"},
    anti_seed=42,
)
```

## Local demo

```bash
cd apps/api
python -m src.media_pipeline.video_renderer
python -m src.media_pipeline.video_renderer --video path\to\clip.mp4
```

Font: auto-detects Windows/Linux/macOS TTF, or set `DRAWTEXT_FONTFILE`.
