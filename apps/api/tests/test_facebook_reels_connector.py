from pathlib import Path
from io import BytesIO
from tempfile import TemporaryDirectory
import unittest
from urllib.error import HTTPError
from uuid import uuid4

from src.enums import ExternalPublicationStatus, PublishAttemptStatus, PublishTargetPlatform
from src.publish.connectors.base import PublishConnectorError
from src.publish.connectors.facebook_reels import FacebookReelsConnector
from src.publish.types import PlatformAccountConfig, PublishMediaInput, PublishRequest


class _FakeResponse:
    def __init__(self, payload: bytes):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self) -> bytes:
        return self.payload


class FacebookReelsConnectorTests(unittest.TestCase):
    def test_validate_account_requires_facebook_page_config(self) -> None:
        connector = FacebookReelsConnector()
        errors = connector.validate_account(
            PlatformAccountConfig(
                platform_account_id=uuid4(),
                platform=PublishTargetPlatform.TIKTOK,
                page_id="",
                display_name="Bad",
                access_token="",
            )
        )
        self.assertIn("Platform account must target FACEBOOK_REELS", errors)
        self.assertIn("Facebook Page id is required", errors)
        self.assertIn("Facebook Page access token is required", errors)

    def test_publish_maps_create_upload_finish_to_normalized_result(self) -> None:
        connector = FacebookReelsConnector()
        calls: list[object] = []

        def fake_urlopen(req, timeout=120):
            calls.append(req)
            url = req.full_url
            if "video_reels" in url and b"upload_phase=start" in req.data:
                self.assertEqual(req.headers["Authorization"], "Bearer token-123")
                self.assertNotIn(b"access_token", req.data)
                return _FakeResponse(b'{"video_id":"video-123","upload_url":"https://rupload.facebook.com/video-upload/v20.0/video-123"}')
            if "rupload.facebook.com" in url:
                self.assertEqual(req.headers["Authorization"], "OAuth token-123")
                self.assertEqual(req.headers["File_size"], "5")
                return _FakeResponse(b'{"success":true}')
            if "video_reels" in url and b"upload_phase=finish" in req.data:
                self.assertEqual(req.headers["Authorization"], "Bearer token-123")
                self.assertNotIn(b"access_token", req.data)
                return _FakeResponse(b'{"success":true}')
            raise AssertionError(f"Unexpected request: {url}")

        with TemporaryDirectory() as tmpdir:
            video_path = Path(tmpdir) / "final.mp4"
            video_path.write_bytes(b"video")
            original_urlopen = __import__("src.publish.connectors.facebook_reels", fromlist=["request"]).request.urlopen
            __import__("src.publish.connectors.facebook_reels", fromlist=["request"]).request.urlopen = fake_urlopen
            try:
                result = connector.publish(
                    PublishRequest(
                        account=PlatformAccountConfig(
                            platform_account_id=uuid4(),
                            platform=PublishTargetPlatform.FACEBOOK_REELS,
                            page_id="page-123",
                            display_name="Demo Page",
                            access_token="token-123",
                            graph_api_version="v20.0",
                        ),
                        media=PublishMediaInput(
                            publish_draft_id=uuid4(),
                            render_output_id=uuid4(),
                            source_video_id=uuid4(),
                            video_path=video_path,
                            title="Demo",
                            description="Caption",
                        ),
                    )
                )
            finally:
                __import__("src.publish.connectors.facebook_reels", fromlist=["request"]).request.urlopen = original_urlopen

        self.assertEqual(result.status, PublishAttemptStatus.SUCCEEDED)
        self.assertEqual(result.external_reel_id, "video-123")
        self.assertEqual(len(calls), 3)

    def test_upload_failure_preserves_video_id_for_reconciliation(self) -> None:
        connector = FacebookReelsConnector()

        def fake_urlopen(req, timeout=120):
            url = req.full_url
            if "video_reels" in url and b"upload_phase=start" in req.data:
                return _FakeResponse(b'{"video_id":"video-123","upload_url":"https://rupload.facebook.com/video-upload/v20.0/video-123"}')
            if "rupload.facebook.com" in url:
                return _FakeResponse(b'{"success":false}')
            raise AssertionError(f"Unexpected request: {url}")

        with TemporaryDirectory() as tmpdir:
            video_path = Path(tmpdir) / "final.mp4"
            video_path.write_bytes(b"video")
            original_urlopen = __import__("src.publish.connectors.facebook_reels", fromlist=["request"]).request.urlopen
            __import__("src.publish.connectors.facebook_reels", fromlist=["request"]).request.urlopen = fake_urlopen
            try:
                with self.assertRaises(PublishConnectorError) as raised:
                    connector.publish(
                        PublishRequest(
                            account=PlatformAccountConfig(
                                platform_account_id=uuid4(),
                                platform=PublishTargetPlatform.FACEBOOK_REELS,
                                page_id="page-123",
                                display_name="Demo Page",
                                access_token="token-123",
                                graph_api_version="v20.0",
                            ),
                            media=PublishMediaInput(
                                publish_draft_id=uuid4(),
                                render_output_id=uuid4(),
                                source_video_id=uuid4(),
                                video_path=video_path,
                                title="Demo",
                                description="Caption",
                            ),
                        )
                    )
            finally:
                __import__("src.publish.connectors.facebook_reels", fromlist=["request"]).request.urlopen = original_urlopen

        self.assertEqual(raised.exception.code, "upload_failed")
        self.assertEqual(raised.exception.response_summary["video_id"], "video-123")

    def test_refresh_status_maps_published_response(self) -> None:
        connector = FacebookReelsConnector()
        calls: list[object] = []

        def fake_urlopen(req, timeout=120):
            calls.append(req)
            self.assertIn("fields=status", req.full_url)
            self.assertNotIn("access_token", req.full_url)
            self.assertEqual(req.headers["Authorization"], "Bearer token-123")
            return _FakeResponse(b'{"id":"video-123","published":true,"permalink_url":"https://facebook.com/reel/video-123"}')

        original_urlopen = __import__("src.publish.connectors.facebook_reels", fromlist=["request"]).request.urlopen
        __import__("src.publish.connectors.facebook_reels", fromlist=["request"]).request.urlopen = fake_urlopen
        try:
            result = connector.refresh_status(
                account=PlatformAccountConfig(
                    platform_account_id=uuid4(),
                    platform=PublishTargetPlatform.FACEBOOK_REELS,
                    page_id="page-123",
                    display_name="Demo Page",
                    access_token="token-123",
                    graph_api_version="v20.0",
                ),
                external_publish_id="video-123",
            )
        finally:
            __import__("src.publish.connectors.facebook_reels", fromlist=["request"]).request.urlopen = original_urlopen

        self.assertEqual(result.external_status, ExternalPublicationStatus.PUBLISHED)
        self.assertEqual(result.external_permalink, "https://facebook.com/reel/video-123")
        self.assertEqual(len(calls), 1)

    def test_rate_limit_error_is_normalized_without_exposing_nested_token(self) -> None:
        connector = FacebookReelsConnector()

        def fake_urlopen(req, timeout=120):
            raise HTTPError(
                req.full_url,
                429,
                "Too Many Requests",
                hdrs=None,
                fp=BytesIO(
                    b'{"error":{"code":4,"message":"limit access_token=secret-value"}}'
                ),
            )

        original_urlopen = __import__("src.publish.connectors.facebook_reels", fromlist=["request"]).request.urlopen
        __import__("src.publish.connectors.facebook_reels", fromlist=["request"]).request.urlopen = fake_urlopen
        try:
            with self.assertRaises(PublishConnectorError) as raised:
                connector.refresh_status(
                    account=PlatformAccountConfig(
                        platform_account_id=uuid4(),
                        platform=PublishTargetPlatform.FACEBOOK_REELS,
                        page_id="page-123",
                        display_name="Demo Page",
                        access_token="token-123",
                        graph_api_version="v20.0",
                    ),
                    external_publish_id="video-123",
                )
        finally:
            __import__("src.publish.connectors.facebook_reels", fromlist=["request"]).request.urlopen = original_urlopen

        self.assertEqual(raised.exception.code, "facebook_rate_limited")
        self.assertNotIn("secret-value", repr(raised.exception.response_summary))


if __name__ == "__main__":
    unittest.main()
