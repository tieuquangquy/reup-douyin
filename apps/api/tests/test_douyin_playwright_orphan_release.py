from __future__ import annotations

import unittest

from src.services.douyin_playwright_orphan_release import (
    is_safe_playwright_profile_process,
    list_orphaned_chromium_pids_for_profile,
)


class OrphanPlaywrightReleaseTests(unittest.TestCase):
    def test_matches_playwright_main_profile_only(self) -> None:
        profile = r"c:\Users\PC\Desktop\reup_douyin\.douyin_profiles\main"
        self.assertTrue(
            is_safe_playwright_profile_process(
                r"C:\Users\PC\AppData\Local\ms-playwright\chromium-1208\chrome-win64\chrome.exe "
                r'--user-data-dir="c:\Users\PC\Desktop\reup_douyin\.douyin_profiles\main"',
                profile,
            )
        )
        self.assertFalse(
            is_safe_playwright_profile_process(
                r'"C:\Program Files\Google\Chrome\Application\chrome.exe" --profile-directory="Profile 18"',
                profile,
            )
        )

    def test_lists_root_pids_only(self) -> None:
        profile = r"c:\repo\.douyin_profiles\main"
        rows = [
            (10, r"ms-playwright\chrome.exe --user-data-dir=c:\repo\.douyin_profiles\main"),
            (11, r"ms-playwright\chrome.exe --type=renderer --user-data-dir=c:\repo\.douyin_profiles\main"),
            (12, r'"C:\Program Files\Google\Chrome\Application\chrome.exe" --profile-directory="Profile 18"'),
        ]
        self.assertEqual(list_orphaned_chromium_pids_for_profile(profile, process_rows=rows), [10])


if __name__ == "__main__":
    unittest.main()
