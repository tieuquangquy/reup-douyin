import unittest
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

from src.enums import PublishTargetPlatform
from src.publish.services.platform_account_service import PlatformAccountService
from src.services.publish_draft_helpers import generate_initial_publish_payload, validate_publish_draft_payload
from src.services.publish_targets import get_target_config, list_target_configs


class PublishPreparationTests(unittest.TestCase):
    def test_target_configs_include_phase1_platforms(self) -> None:
        platforms = {config.platform for config in list_target_configs()}
        self.assertIn(PublishTargetPlatform.TIKTOK, platforms)
        self.assertIn(PublishTargetPlatform.FACEBOOK_REELS, platforms)
        self.assertIn(PublishTargetPlatform.YOUTUBE_SHORTS, platforms)

    def test_initial_payload_generation_is_deterministic(self) -> None:
        config = get_target_config(PublishTargetPlatform.TIKTOK)
        source_video = SimpleNamespace(
            caption="Mon an nay dang gay chu y vi cach lam rat nhanh",
            source_video_external_id="video-1",
            source_profile=SimpleNamespace(display_name="Douyin Food"),
        )
        payload = generate_initial_publish_payload(source_video, config)
        self.assertEqual(payload["cta_text"], config.default_cta)
        self.assertEqual(payload["hashtags"][0]["tag"], "vietsub")
        self.assertTrue(any(item["tag"] == "douyinfood" for item in payload["hashtags"]))

    def test_validate_draft_requires_metadata(self) -> None:
        draft = SimpleNamespace(
            target_platform="TIKTOK",
            caption="",
            cta_text="",
            hashtags_json=[],
        )
        errors = validate_publish_draft_payload(draft)
        self.assertIn("caption is required", errors)
        self.assertIn("cta_text is required", errors)
        self.assertIn("at least one hashtag is required", errors)


class PlatformAccountTokenResolutionTests(unittest.TestCase):
    def test_token_resolution_reads_api_env_file_when_process_env_missing(self) -> None:
        previous = os.environ.pop("FACEBOOK_PAGE_ACCESS_TOKEN", None)
        cwd = Path.cwd()
        try:
            with TemporaryDirectory() as tmpdir:
                try:
                    os.chdir(tmpdir)
                    Path(".env").write_text("FACEBOOK_PAGE_ACCESS_TOKEN=token-from-dotenv\n", encoding="utf-8")
                    service = object.__new__(PlatformAccountService)
                    self.assertEqual(service._resolve_access_token("FACEBOOK_PAGE_ACCESS_TOKEN"), "token-from-dotenv")
                finally:
                    os.chdir(cwd)
        finally:
            if previous is not None:
                os.environ["FACEBOOK_PAGE_ACCESS_TOKEN"] = previous

    def test_process_env_wins_over_dotenv_token(self) -> None:
        previous = os.environ.get("FACEBOOK_PAGE_ACCESS_TOKEN")
        os.environ["FACEBOOK_PAGE_ACCESS_TOKEN"] = "token-from-process"
        try:
            with TemporaryDirectory() as tmpdir:
                cwd = Path.cwd()
                try:
                    os.chdir(tmpdir)
                    Path(".env").write_text("FACEBOOK_PAGE_ACCESS_TOKEN=token-from-dotenv\n", encoding="utf-8")
                    service = object.__new__(PlatformAccountService)
                    self.assertEqual(service._resolve_access_token("FACEBOOK_PAGE_ACCESS_TOKEN"), "token-from-process")
                finally:
                    os.chdir(cwd)
        finally:
            if previous is None:
                os.environ.pop("FACEBOOK_PAGE_ACCESS_TOKEN", None)
            else:
                os.environ["FACEBOOK_PAGE_ACCESS_TOKEN"] = previous


if __name__ == "__main__":
    unittest.main()
