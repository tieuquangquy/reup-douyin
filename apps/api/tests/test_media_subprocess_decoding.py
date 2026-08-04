"""Media subprocess output must survive non-Latin filenames.

Douyin filenames are Chinese. Decoding ffmpeg/demucs output with the Windows console
codepage raises UnicodeDecodeError inside subprocess reader threads, which throws away
the stderr we need to report why separation failed.
"""

from __future__ import annotations

import os
import sys
import unittest
from unittest.mock import patch

from src.audio_pipeline.demucs_runner import run_captured


class MediaSubprocessDecodingTests(unittest.TestCase):
    def test_chinese_stdout_is_captured(self) -> None:
        # Reproduce the Windows failure mode even when the test runner is UTF-8.
        # run_captured must override the child process setting.
        with patch.dict(os.environ, {"PYTHONIOENCODING": "cp1252"}):
            completed = run_captured(
                [sys.executable, "-c", "import sys; sys.stdout.write('\\u9760\\u5403\\u7626')"]
            )

        self.assertEqual(completed.returncode, 0)
        self.assertIn("靠吃瘦", completed.stdout)

    def test_chinese_stderr_survives_a_failure(self) -> None:
        completed = run_captured(
            [sys.executable, "-c", "import sys; sys.stderr.write('\\u5931\\u8d25'); sys.exit(1)"]
        )

        self.assertEqual(completed.returncode, 1)
        self.assertIn("失败", completed.stderr, "Failure detail must not be lost to a decode error")

    def test_undecodable_bytes_do_not_raise(self) -> None:
        completed = run_captured(
            [sys.executable, "-c", "import sys; sys.stdout.buffer.write(bytes([0x8f, 0x8d, 0xff]))"]
        )

        self.assertEqual(completed.returncode, 0)
        self.assertIsInstance(completed.stdout, str)


if __name__ == "__main__":
    unittest.main()
