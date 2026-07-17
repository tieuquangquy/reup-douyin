"""Optional Cloud Run HTTP/CLI entry for Phase 1 frame sampling.

Keep this module free of FastAPI/DB so the container image stays small and
scale-to-zero friendly. Wire a minimal HTTP server only when deploying.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

from src.media_pipeline.frame_sampling.errors import FrameSamplingError
from src.media_pipeline.frame_sampling.job import FrameSamplingJobRequest, run_frame_sampling_job

logger = logging.getLogger(__name__)


def run_from_env() -> dict[str, Any]:
    """Run one job from environment variables (batch / Cloud Run Jobs style).

    Env:
      VIDEO_SOURCE — local path or http(s) URL
      OUTPUT_DIR — directory for JPEG frames
      SAMPLE_FPS — must be 1 or 2 (default 1)
      FFMPEG_BINARY — optional
    """
    video_source = os.environ.get("VIDEO_SOURCE", "").strip()
    output_dir = os.environ.get("OUTPUT_DIR", "").strip()
    if not video_source or not output_dir:
        raise SystemExit("VIDEO_SOURCE and OUTPUT_DIR are required")
    sample_fps = float(os.environ.get("SAMPLE_FPS", "1"))
    ffmpeg_binary = os.environ.get("FFMPEG_BINARY", "ffmpeg")
    result = run_frame_sampling_job(
        FrameSamplingJobRequest(
            video_source=video_source,
            output_dir=output_dir,
            sample_fps=sample_fps,
            ffmpeg_binary=ffmpeg_binary,
        )
    )
    payload = {
        "sample_fps": result.sample_fps,
        "frame_count": result.frame_count,
        "frame_paths": result.frame_paths,
        "frame_time_ms": result.frame_time_ms,
    }
    print(json.dumps(payload))
    return payload


class _FrameSamplingHandler(BaseHTTPRequestHandler):
    """Minimal JSON POST handler for Cloud Run HTTP services."""

    def log_message(self, format: str, *args: object) -> None:  # noqa: A003
        logger.info("frame_sampling_http", extra={"message": format % args})

    def do_POST(self) -> None:  # noqa: N802
        if self.path not in {"/", "/sample", "/v1/frame-sampling"}:
            self.send_error(404)
            return
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length) if length else b"{}"
        try:
            body = json.loads(raw.decode("utf-8") or "{}")
            result = run_frame_sampling_job(
                FrameSamplingJobRequest(
                    video_source=str(body["video_source"]),
                    output_dir=str(body["output_dir"]),
                    sample_fps=body.get("sample_fps", 1),
                    ffmpeg_binary=str(body.get("ffmpeg_binary") or "ffmpeg"),
                )
            )
            payload = {
                "sample_fps": result.sample_fps,
                "frame_count": result.frame_count,
                "frame_paths": result.frame_paths,
                "frame_time_ms": result.frame_time_ms,
            }
            data = json.dumps(payload).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        except FrameSamplingError as exc:
            data = json.dumps({"code": exc.code, "message": exc.message}).encode("utf-8")
            self.send_response(422)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        except Exception as exc:  # pragma: no cover — last-resort Cloud Run surface
            data = json.dumps({"code": "INTERNAL", "message": str(exc)[:400]}).encode("utf-8")
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)


def serve_http(host: str = "0.0.0.0", port: int = 8080) -> None:
    server = HTTPServer((host, port), _FrameSamplingHandler)
    logger.info("frame_sampling_http_listen", extra={"host": host, "port": port})
    server.serve_forever()


def main(argv: list[str] | None = None) -> None:
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
    args = list(sys.argv[1:] if argv is None else argv)
    if args and args[0] == "serve":
        port = int(os.environ.get("PORT", "8080"))
        serve_http(port=port)
        return
    run_from_env()


if __name__ == "__main__":
    main()
