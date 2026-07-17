from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from src.downloaders.douyin_download_cookie_store import (
    download_cookie_store_root,
    read_download_cookie_store,
    write_download_cookie_store,
)


class DownloadCookieStoreRootTests(unittest.TestCase):
    def test_store_root_is_repo_anchored_not_cwd_local_storage(self) -> None:
        root = download_cookie_store_root()
        self.assertTrue(root.is_absolute())
        self.assertEqual(root.name, "download_cookies")
        self.assertIn(".douyin_profiles", root.parts)
        # Must not depend on process cwd (API vs worker cwd mismatch).
        with tempfile.TemporaryDirectory() as tmp:
            old = os.getcwd()
            try:
                os.chdir(tmp)
                again = download_cookie_store_root()
            finally:
                os.chdir(old)
        self.assertEqual(root, again)

    def test_write_read_under_custom_root(self) -> None:
        account_id = uuid4()
        cookies = [
            {
                "name": "sessionid",
                "value": "x",
                "domain": ".douyin.com",
                "path": "/",
                "secure": True,
            }
        ]
        with tempfile.TemporaryDirectory() as tmp:
            store_root = Path(tmp)
            write_download_cookie_store(
                store_root=store_root,
                account_id=account_id,
                playwright_cookies=cookies,
                user_agent="ua",
            )
            payload = read_download_cookie_store(store_root=store_root, account_id=account_id)
            self.assertIsNotNone(payload)
            assert payload is not None
            self.assertEqual(payload.playwright_cookies[0]["name"], "sessionid")


if __name__ == "__main__":
    unittest.main()
