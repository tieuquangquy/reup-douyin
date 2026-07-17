from __future__ import annotations

import json
import unittest
from io import BytesIO
from urllib.error import HTTPError

from src.audio_pipeline.machine_translate import mymemory_zh_to_vi


class _FakeResponse:
    def __init__(self, payload: dict):
        self._raw = json.dumps(payload).encode("utf-8")

    def read(self) -> bytes:
        return self._raw

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class MyMemoryTranslateTests(unittest.TestCase):
    def test_mymemory_returns_vietnamese(self) -> None:
        def opener(request, timeout=20.0):
            del request, timeout
            return _FakeResponse({"responseData": {"translatedText": "Xin chao"}})

        text = mymemory_zh_to_vi("你好", opener=opener)
        self.assertEqual(text, "Xin chao")

    def test_mymemory_rejects_cjk_output(self) -> None:
        def opener(request, timeout=20.0):
            del request, timeout
            return _FakeResponse({"responseData": {"translatedText": "还是中文"}})

        with self.assertRaises(RuntimeError) as ctx:
            mymemory_zh_to_vi("你好", opener=opener)
        self.assertIn("still_contains_cjk", str(ctx.exception))

    def test_mymemory_http_error(self) -> None:
        def opener(request, timeout=20.0):
            del request, timeout
            raise HTTPError("http://x", 429, "rate", hdrs=None, fp=BytesIO(b"slow"))

        with self.assertRaises(RuntimeError) as ctx:
            mymemory_zh_to_vi("你好", opener=opener)
        self.assertIn("mymemory_http_429", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
