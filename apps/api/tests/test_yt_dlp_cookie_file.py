from __future__ import annotations

import unittest
from pathlib import Path
from subprocess import CompletedProcess
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch

from src.downloaders.errors import DownloadError, DownloadErrorCode
from src.downloaders.yt_dlp_douyin_resolver import (
    YtDlpDouyinVideoResolver,
    cookie_header_to_netscape_lines,
    _video_quality_from_info,
    write_netscape_cookie_file,
)
from src.downloaders.douyin_video_resolver import DouyinVideoResolveRequest


class CookieFileTests(unittest.TestCase):
    def test_extracts_actual_merged_video_quality(self) -> None:
        quality = _video_quality_from_info(
            {
                "format_id": "137+140",
                "requested_formats": [
                    {"format_id": "140", "vcodec": "none"},
                    {"format_id": "137", "vcodec": "h264", "width": 1080, "height": 1920, "fps": 30, "tbr": 4500},
                ],
            }
        )
        self.assertEqual(quality["codec"], "h264")
        self.assertEqual(quality["width"], 1080)
        self.assertEqual(quality["height"], 1920)
        self.assertEqual(quality["bitrate"], 4_500_000)
        self.assertEqual(quality["fps"], 30.0)
    def test_cookie_header_to_netscape_lines_skips_invalid_pairs(self) -> None:
        lines = cookie_header_to_netscape_lines("sessionid=abc; ttwid=1%7Cxyz; douyin.com; enter_pc_once=1")
        joined = "\n".join(lines)
        self.assertIn("sessionid\tabc", joined)
        self.assertIn("ttwid\t1%7Cxyz", joined)
        self.assertNotIn("douyin.com;", joined)

    def test_write_netscape_cookie_file(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "cookies.txt"
            write_netscape_cookie_file("sessionid=abc", path)
            content = path.read_text(encoding="utf-8")
            self.assertIn("# Netscape HTTP Cookie File", content)
            self.assertIn(".douyin.com\tTRUE\t/\tTRUE\t", content)
            self.assertIn("\tsessionid\tabc", content)


class YtDlpCookieInvocationTests(unittest.TestCase):
    def test_discover_uses_skip_download_and_returns_ranked_formats(self) -> None:
        resolver = YtDlpDouyinVideoResolver(binary="yt-dlp", format_selector="best", timeout_seconds=30)
        request = DouyinVideoResolveRequest(
            aweme_id="1",
            page_url="https://www.douyin.com/video/1",
            session_cookie="sessionid=abc",
            user_agent="Mozilla/5.0",
        )
        payload = {
            "formats": [
                {
                    "format_id": "play-720",
                    "format_note": "play",
                    "vcodec": "h264",
                    "width": 720,
                    "height": 1280,
                    "tbr": 2500,
                },
                {
                    "format_id": "play-1080",
                    "format_note": "play",
                    "vcodec": "h264",
                    "width": 1080,
                    "height": 1920,
                    "tbr": 5000,
                },
            ]
        }
        with patch.object(resolver, "is_available", return_value=True), patch(
            "src.downloaders.yt_dlp_douyin_resolver.subprocess.run",
            return_value=CompletedProcess([], 0, stdout=__import__("json").dumps(payload), stderr=""),
        ) as run_mock, patch(
            "src.downloaders.yt_dlp_douyin_resolver.get_settings",
            return_value=MagicMock(douyin_download_allow_watermarked_fallback=False),
        ):
            candidates = resolver.discover(request)

        command = run_mock.call_args.args[0]
        self.assertIn("--skip-download", command)
        self.assertIn("--dump-single-json", command)
        self.assertNotIn("-o", command)
        self.assertEqual(candidates[0].format_id, "play-1080+bestaudio/best")

    def test_resolve_uses_cookies_file_not_header(self) -> None:
        resolver = YtDlpDouyinVideoResolver(binary="yt-dlp", format_selector="best", timeout_seconds=30)
        request = DouyinVideoResolveRequest(
            aweme_id="7640466047388785802",
            page_url="https://www.douyin.com/video/7640466047388785802",
            session_cookie="sessionid=abc; ttwid=xyz",
            user_agent="Mozilla/5.0",
            proxy_url=None,
        )

        seen: dict[str, str] = {}

        def fake_run(command, **kwargs):
            cookie_index = command.index("--cookies")
            seen["cookie_content"] = Path(command[cookie_index + 1]).read_text(encoding="utf-8")
            output_template = command[command.index("-o") + 1]
            output_path = Path(output_template.replace("%(ext)s", "mp4"))
            output_path.write_bytes(b"video-bytes")
            info_path = output_path.with_name(f"{output_path.stem}.info.json")
            info_path.write_text(
                '{"format_id":"download","height":1080,"width":1920}',
                encoding="utf-8",
            )
            return CompletedProcess(command, 0, stdout="", stderr="")

        with TemporaryDirectory() as staging_tmp, patch.object(
            resolver,
            "is_available",
            return_value=True,
        ), patch(
            "src.downloaders.yt_dlp_douyin_resolver.subprocess.run",
            side_effect=fake_run,
        ) as run_mock, patch(
            "src.downloaders.yt_dlp_douyin_resolver.staging_directory",
            return_value=Path(staging_tmp),
        ), patch(
            "src.downloaders.yt_dlp_douyin_resolver.get_settings",
            return_value=MagicMock(
                douyin_download_allow_watermarked_fallback=True,
                douyin_yt_dlp_binary="yt-dlp",
                douyin_yt_dlp_format="best",
                douyin_yt_dlp_timeout_seconds=30,
            ),
        ):
            # INFO is the production log level. Reserved LogRecord keys in
            # ``extra`` only fail when this record is actually emitted.
            with self.assertLogs(
                "src.downloaders.yt_dlp_douyin_resolver",
                level="INFO",
            ) as captured_logs:
                result = resolver.resolve(request)
            self.assertIsNone(result.content)
            self.assertEqual(Path(result.local_path or "").read_bytes(), b"video-bytes")
            self.assertTrue(any("yt_dlp_download_completed" in row for row in captured_logs.output))

        command = run_mock.call_args.args[0]
        self.assertIn("--cookies", command)
        self.assertNotIn("Cookie:", " ".join(command))
        self.assertIn("sessionid\tabc", seen["cookie_content"])

    def test_resolve_surfaces_yt_dlp_stderr(self) -> None:
        resolver = YtDlpDouyinVideoResolver(binary="yt-dlp", format_selector="best", timeout_seconds=30)
        request = DouyinVideoResolveRequest(
            aweme_id="1",
            page_url="https://www.douyin.com/video/1",
            session_cookie="sessionid=abc",
            user_agent="Mozilla/5.0",
            proxy_url=None,
        )
        with patch.object(resolver, "is_available", return_value=True), patch(
            "src.downloaders.yt_dlp_douyin_resolver.subprocess.run",
            return_value=CompletedProcess([], 1, stdout="", stderr="ERROR: [Douyin] Fresh cookies are needed"),
        ):
            with self.assertRaises(DownloadError) as ctx:
                resolver.resolve(request)
        self.assertEqual(ctx.exception.code, DownloadErrorCode.DOWNLOAD_FAILED)
        self.assertIn("Fresh cookies", ctx.exception.message)

    def test_resolve_enforces_max_bytes_and_removes_oversized_staging(self) -> None:
        resolver = YtDlpDouyinVideoResolver(
            binary="yt-dlp",
            format_selector="best",
            timeout_seconds=30,
            max_bytes=4,
        )
        request = DouyinVideoResolveRequest(
            aweme_id="1",
            page_url="https://www.douyin.com/video/1",
            session_cookie="sessionid=abc",
            user_agent="Mozilla/5.0",
        )

        def fake_run(command, **_kwargs):
            output_template = command[command.index("-o") + 1]
            output_path = Path(output_template.replace("%(ext)s", "mp4"))
            output_path.write_bytes(b"12345")
            output_path.with_name(f"{output_path.stem}.info.json").write_text(
                '{"format_id":"best"}',
                encoding="utf-8",
            )
            return CompletedProcess(command, 0, stdout="", stderr="")

        with TemporaryDirectory() as staging_tmp, patch.object(
            resolver,
            "is_available",
            return_value=True,
        ), patch(
            "src.downloaders.yt_dlp_douyin_resolver.subprocess.run",
            side_effect=fake_run,
        ), patch(
            "src.downloaders.yt_dlp_douyin_resolver.staging_directory",
            return_value=Path(staging_tmp),
        ), patch(
            "src.downloaders.yt_dlp_douyin_resolver.get_settings",
            return_value=MagicMock(douyin_download_allow_watermarked_fallback=True),
        ):
            with self.assertRaises(DownloadError) as ctx:
                resolver.resolve(request)
            self.assertEqual(ctx.exception.code, DownloadErrorCode.VALIDATION_FAILED)
            self.assertEqual(list(Path(staging_tmp).glob("video.*")), [])


if __name__ == "__main__":
    unittest.main()
