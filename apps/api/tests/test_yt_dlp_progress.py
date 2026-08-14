from __future__ import annotations

import subprocess
import time

import pytest

from src.downloaders.yt_dlp_douyin_resolver import _parse_yt_dlp_progress, _run_yt_dlp_progress_process


class _FakeProcess:
    def __init__(self, lines: list[str]):
        self.stdout = iter(lines)
        self.returncode = 0
        self.terminated = False

    def poll(self):
        return self.returncode

    def terminate(self):
        self.terminated = True
        self.returncode = -15

    def kill(self):
        self.terminated = True
        self.returncode = -9

    def wait(self, timeout=None):
        return self.returncode


def test_parse_yt_dlp_progress_prefers_total_then_estimate() -> None:
    assert _parse_yt_dlp_progress("reup_douyin_progress:100:500:600") == (100, 500)
    assert _parse_yt_dlp_progress("reup_douyin_progress:100:NA:600") == (100, 600)
    assert _parse_yt_dlp_progress("ordinary yt-dlp log") is None


def test_progress_process_emits_byte_heartbeat(monkeypatch) -> None:
    process = _FakeProcess(
        [
            "download:reup_douyin_progress:10:100:100\n",
            "download:reup_douyin_progress:100:100:100\n",
        ]
    )
    monkeypatch.setattr(
        "src.downloaders.yt_dlp_douyin_resolver.subprocess.Popen",
        lambda *args, **kwargs: process,
    )
    progress: list[tuple[int, int | None]] = []

    result = _run_yt_dlp_progress_process(
        ["yt-dlp", "video"],
        timeout_seconds=5,
        on_progress=lambda done, total: progress.append((done, total)),
    )

    assert result.returncode == 0
    assert (10, 100) in progress
    assert (100, 100) in progress


def test_progress_process_propagates_cancellation_and_terminates(monkeypatch) -> None:
    process = _FakeProcess([])
    process.returncode = None
    monkeypatch.setattr(
        "src.downloaders.yt_dlp_douyin_resolver.subprocess.Popen",
        lambda *args, **kwargs: process,
    )

    class Cancelled(Exception):
        pass

    with pytest.raises(Cancelled):
        _run_yt_dlp_progress_process(
            ["yt-dlp", "video"],
            timeout_seconds=5,
            on_progress=lambda _done, _total: (_ for _ in ()).throw(Cancelled()),
        )
    assert process.terminated is True


def test_progress_process_aborts_when_first_media_byte_never_arrives(monkeypatch) -> None:
    class SlowEmptyStream:
        def __iter__(self):
            return self

        def __next__(self):
            time.sleep(0.08)
            raise StopIteration

    process = _FakeProcess([])
    process.stdout = SlowEmptyStream()
    process.returncode = None
    monkeypatch.setattr(
        "src.downloaders.yt_dlp_douyin_resolver.subprocess.Popen",
        lambda *args, **kwargs: process,
    )

    with pytest.raises(subprocess.TimeoutExpired) as caught:
        _run_yt_dlp_progress_process(
            ["yt-dlp", "video"],
            timeout_seconds=5,
            first_byte_timeout_seconds=0.02,
            stall_timeout_seconds=1,
            on_progress=lambda _done, _total: None,
        )

    assert "no media bytes received" in str(caught.value.output)
    assert process.terminated is True
