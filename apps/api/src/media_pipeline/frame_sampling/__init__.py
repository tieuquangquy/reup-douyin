"""Phase 1: video frame sampling at STRICT 1|2 fps (FFmpeg core)."""

from src.media_pipeline.frame_sampling.ffmpeg_engine import extract_video_frames, normalize_sample_fps
from src.media_pipeline.frame_sampling.job import FrameSamplingJobRequest, FrameSamplingJobResult, run_frame_sampling_job
from src.media_pipeline.frame_sampling.types import ExtractedFrame, SampleFps

__all__ = [
    "ExtractedFrame",
    "FrameSamplingJobRequest",
    "FrameSamplingJobResult",
    "SampleFps",
    "extract_video_frames",
    "normalize_sample_fps",
    "run_frame_sampling_job",
]
