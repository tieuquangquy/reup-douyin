import json
from pathlib import Path
import unittest
from urllib.parse import quote

from src.adapters.douyin import DouyinProfileAdapter
from src.adapters.douyin_live_fetch import DouyinLiveFetchClient, DouyinLiveFetchConfig
from src.adapters.errors import SourceAdapterError, SourceAdapterErrorCode
from src.enums import SourcePlatformEnum
from src.services.source_dedupe import normalized_profile_dedupe_key, normalized_video_dedupe_key


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "douyin_profile_payload.json"


class DouyinAdapterTests(unittest.TestCase):
    def test_validate_and_normalize_douyin_user_url(self) -> None:
        adapter = DouyinProfileAdapter()
        identity = adapter.normalize_profile_identity("https://www.douyin.com/user/MS4wLjABAAAAfixture-sec-uid")
        self.assertEqual(identity.source_platform, SourcePlatformEnum.DOUYIN)
        self.assertEqual(identity.source_profile_external_id, "MS4wLjABAAAAfixture-sec-uid")

    def test_invalid_url_is_classified(self) -> None:
        adapter = DouyinProfileAdapter()
        with self.assertRaises(SourceAdapterError) as ctx:
            adapter.validate_profile_url("not-a-url")
        self.assertEqual(ctx.exception.code, SourceAdapterErrorCode.INVALID_URL)

    def test_normalized_payload_mapping(self) -> None:
        adapter = DouyinProfileAdapter()
        payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
        result = adapter.normalize_fetch_payload(
            "https://www.douyin.com/user/MS4wLjABAAAAfixture-sec-uid",
            payload,
        )

        self.assertEqual(result.profile.display_name, "Fixture Creator")
        self.assertEqual(len(result.videos), 2)
        first_video = result.videos[0]
        self.assertEqual(first_video.source_video_external_id, "7420000000000000001")
        self.assertEqual(first_video.duration_seconds, 12.345)
        self.assertEqual(first_video.metrics.view_count, 1000)
        self.assertEqual(first_video.metrics.like_count, 120)
        self.assertIn("food", first_video.hashtags)

    def test_dedupe_keys_are_platform_and_external_id(self) -> None:
        adapter = DouyinProfileAdapter()
        payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
        result = adapter.normalize_fetch_payload(
            "https://www.douyin.com/user/MS4wLjABAAAAfixture-sec-uid",
            payload,
        )
        self.assertEqual(
            normalized_profile_dedupe_key(result.profile),
            (SourcePlatformEnum.DOUYIN, "MS4wLjABAAAAfixture-sec-uid"),
        )
        self.assertEqual(
            normalized_video_dedupe_key(result.videos[0]),
            (SourcePlatformEnum.DOUYIN, "7420000000000000001"),
        )

    def test_missing_video_id_is_recorded_as_drop_reason(self) -> None:
        adapter = DouyinProfileAdapter()
        result = adapter.normalize_fetch_payload(
            "https://www.douyin.com/user/MS4wLjABAAAAfixture-sec-uid",
            {"profile": {"sec_uid": "MS4wLjABAAAAfixture-sec-uid"}, "videos": [{"desc": "missing id"}]},
        )
        self.assertEqual(result.metadata_json.get("drop_reasons"), {"normalization_failed": 1})

    def test_normalize_collects_drop_diagnostics_and_blocked_reason_for_empty_payload(self) -> None:
        adapter = DouyinProfileAdapter()
        result = adapter.normalize_fetch_payload(
            "https://www.douyin.com/user/MS4wLjABAAAAfixture-sec-uid",
            {
                "profile": {"sec_uid": "MS4wLjABAAAAfixture-sec-uid", "nickname": "Fixture"},
                "videos": [{"desc": "missing external id"}],
            },
        )

        self.assertEqual(len(result.videos), 0)
        self.assertEqual(result.metadata_json.get("raw_video_item_count"), 1)
        self.assertEqual(result.metadata_json.get("normalized_video_count"), 0)
        self.assertEqual(result.metadata_json.get("drop_count"), 1)
        self.assertEqual(result.metadata_json.get("drop_reasons"), {"normalization_failed": 1})

    def test_normalize_marks_login_required_from_payload_markers(self) -> None:
        adapter = DouyinProfileAdapter()
        result = adapter.normalize_fetch_payload(
            "https://www.douyin.com/user/MS4wLjABAAAAfixture-sec-uid",
            {
                "profile": {"sec_uid": "MS4wLjABAAAAfixture-sec-uid"},
                "videos": [],
                "message": "verify login to continue",
            },
        )

        self.assertEqual(result.metadata_json.get("blocked_reason"), "login_required")

    def test_fetch_without_client_is_adapter_fetch_failed(self) -> None:
        adapter = DouyinProfileAdapter()
        with self.assertRaises(SourceAdapterError) as ctx:
            adapter.fetch_profile("https://www.douyin.com/user/MS4wLjABAAAAfixture-sec-uid")
        self.assertEqual(ctx.exception.code, SourceAdapterErrorCode.ADAPTER_FETCH_FAILED)

    def test_live_fetch_client_extracts_embedded_render_data(self) -> None:
        payload = {
            "user": {
                "sec_uid": "MS4wLjABAAAAlive-sec-uid",
                "nickname": "Live Fixture",
                "unique_id": "live_fixture",
                "follower_count": 321,
            },
            "aweme_list": [
                {
                    "aweme_id": "7430000000000000001",
                    "desc": "Live extracted video #test",
                    "create_time": 1710000000,
                    "duration": 9000,
                    "share_url": "https://www.douyin.com/video/7430000000000000001",
                    "statistics": {
                        "play_count": 1234,
                        "digg_count": 234,
                        "comment_count": 12,
                        "share_count": 4,
                    },
                }
            ],
        }
        html = f'<html><script id="RENDER_DATA" type="application/json">{quote(json.dumps(payload))}</script></html>'
        client = DouyinLiveFetchClient(
            DouyinLiveFetchConfig(user_agent="test-agent"),
            http_get=lambda _: html,
        )
        adapter = DouyinProfileAdapter(fetch_client=client)

        result = adapter.fetch_profile("https://www.douyin.com/user/MS4wLjABAAAAlive-sec-uid")

        self.assertEqual(result.profile.display_name, "Live Fixture")
        self.assertEqual(len(result.videos), 1)
        self.assertEqual(result.videos[0].source_video_external_id, "7430000000000000001")
        self.assertEqual(result.videos[0].metrics.view_count, 1234)


if __name__ == "__main__":
    unittest.main()
