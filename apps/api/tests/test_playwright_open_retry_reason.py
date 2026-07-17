from __future__ import annotations

import unittest

from src.services.douyin_playwright_orphan_release import should_retry_playwright_open_after_orphan_release


class PlaywrightOpenRetryReasonTests(unittest.TestCase):
    def test_retries_lock_and_early_page_close(self) -> None:
        self.assertTrue(should_retry_playwright_open_after_orphan_release("profile_locked_by_existing_process:Error"))
        self.assertTrue(should_retry_playwright_open_after_orphan_release("first_page_closed_early:TargetClosedError"))
        self.assertTrue(should_retry_playwright_open_after_orphan_release("managed_runtime_reopen_failed:TargetClosedError"))
        self.assertTrue(should_retry_playwright_open_after_orphan_release("browser_context_lost:TargetClosedError"))
        self.assertFalse(should_retry_playwright_open_after_orphan_release("dependency_missing"))
        self.assertFalse(should_retry_playwright_open_after_orphan_release(None))


if __name__ == "__main__":
    unittest.main()
