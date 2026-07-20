"""Phase 1: video frame sampling (text_onnx default, ffmpeg_fps rollback)."""

from src.media_pipeline.frame_sampling.backend import extract_phase1_frames, resolve_frame_backend
from src.media_pipeline.frame_sampling.ffmpeg_engine import extract_video_frames, normalize_sample_fps
from src.media_pipeline.frame_sampling.job import FrameSamplingJobRequest, FrameSamplingJobResult, run_frame_sampling_job
from src.media_pipeline.frame_sampling.types import ExtractedFrame, SampleFps

__all__ = [
    "ExtractedFrame",
    "FrameSamplingJobRequest",
    "FrameSamplingJobResult",
    "SampleFps",
    "extract_phase1_frames",
    "extract_video_frames",
    "normalize_sample_fps",
    "resolve_frame_backend",
    "run_frame_sampling_job",
]
