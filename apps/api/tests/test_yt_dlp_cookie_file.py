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
    write_netscape_cookie_file,
)
from src.downloaders.douyin_video_resolver import DouyinVideoResolveRequest


class CookieFileTests(unittest.TestCase):
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

        with patch.object(resolver, "is_available", return_value=True), patch(
            "src.downloaders.yt_dlp_douyin_resolver.subprocess.run",
            side_effect=fake_run,
        ) as run_mock, patch(
            "src.core.settings.get_settings",
            return_value=MagicMock(
                douyin_download_allow_watermarked_fallback=True,
                douyin_yt_dlp_binary="yt-dlp",
                douyin_yt_dlp_format="best",
                douyin_yt_dlp_timeout_seconds=30,
            ),
        ):
            result = resolver.resolve(request)

        command = run_mock.call_args.args[0]
        self.assertIn("--cookies", command)
        self.assertNotIn("Cookie:", " ".join(command))
        self.assertIn("sessionid\tabc", seen["cookie_content"])
        self.assertEqual(result.content, b"video-bytes")

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


if __name__ == "__main__":
    unittest.main()
