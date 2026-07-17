from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from src.render_pipeline.errors import RenderPipelineError, RenderPipelineErrorCode
from src.render_pipeline.types import ExportInput, ExportResult


def build_subtitles_vf(subtitle_path: str) -> str:
    """Build `-vf` value for burning SRT via libass.

    FFmpeg filter graphs treat unescaped ``:`` as option separators. On Windows a
    drive letter path like ``C:/foo.srt`` is parsed as filename ``C`` plus a bogus
    ``original_size`` option (the remainder of the path). Prefer passing only a
    basename and setting subprocess ``cwd`` to the subtitle directory so the
    filter never sees a drive letter.
    """
    normalized = subtitle_path.replace("\\", "/")
    escaped = (
        normalized.replace("\\", "\\\\")
        .replace(":", "\\:")
        .replace("'", "\\'")
        .replace(",", "\\,")
        .replace("[", "\\[")
        .replace("]", "\\]")
    )
    return (
        f"subtitles='{escaped}':"
        "force_style='Fontsize=18\\,PrimaryColour=&H00FFFFFF\\,OutlineColour=&H80000000\\,"
        "BorderStyle=3\\,Outline=2\\,Shadow=0\\,MarginV=28\\,Alignment=2'"
    )


class FfmpegRenderRunner:
    runner_name = "ffmpeg"

    def __init__(self, ffmpeg_binary: str = "ffmpeg"):
        self.ffmpeg_binary = ffmpeg_binary

    def export(self, export_input: ExportInput) -> ExportResult:
        if shutil.which(self.ffmpeg_binary) is None:
            raise RenderPipelineError(RenderPipelineErrorCode.EXPORT_FAILED, "ffmpeg binary not found on PATH")
        Path(export_input.output_path).parent.mkdir(parents=True, exist_ok=True)
        subtitle_file = Path(export_input.subtitle_path)
        if not subtitle_file.is_file():
            raise RenderPipelineError(
                RenderPipelineErrorCode.EXPORT_FAILED,
                f"subtitle file not found: {export_input.subtitle_path}",
            )
        # Basename + cwd avoids Windows drive-letter ``:`` in the filter graph.
        subtitle_cwd = str(subtitle_file.resolve().parent)
        subtitle_filter = build_subtitles_vf(subtitle_file.name)
        command = [
            self.ffmpeg_binary,
            "-y",
            "-i",
            export_input.source_video_path,
            "-i",
            export_input.narration_path,
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-vf",
            subtitle_filter,
            "-c:v",
            export_input.profile.video_codec,
            "-c:a",
            export_input.profile.audio_codec,
            "-shortest",
            export_input.output_path,
        ]
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
            cwd=subtitle_cwd,
        )
        log_text = "\n".join([completed.stdout, completed.stderr]).strip()
        if completed.returncode != 0:
            raise RenderPipelineError(
                RenderPipelineErrorCode.EXPORT_FAILED,
                f"vf={subtitle_filter} cwd={subtitle_cwd}\n{log_text or 'ffmpeg export failed'}",
            )
        return ExportResult(output_path=export_input.output_path, log_text=log_text, warnings=[], command=command)
