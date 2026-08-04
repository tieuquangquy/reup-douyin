from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from src.affiliate_intelligence.services.affiliate_comment_verification_service import (
    AffiliateCommentVerificationError,
    check_affiliate_url,
)
from src.publish.connectors.facebook_reels import FacebookReelsConnector
from src.publish.types import PlatformAccountConfig
from src.enums import PublishTargetPlatform
from src.enums import JobType
from src.services.job_templates import get_step_templates


class _Response:
    def __init__(self, payload: bytes, status_code: int = 200, headers: dict | None = None):
        self.payload = payload
        self.status_code = status_code
        self.headers = headers or {}

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self) -> bytes:
        return self.payload


class AffiliateCommentVerificationTests(unittest.TestCase):
    def test_verification_job_has_one_combined_external_boundary_step(self):
        self.assertEqual(
            [step.key for step in get_step_templates(JobType.VERIFY_AFFILIATE_COMMENT)],
            ["validate_target", "verify_comment_and_link", "persist_result", "finalize"],
        )

    def test_connector_reads_visible_comment_without_exposing_token(self):
        account = PlatformAccountConfig(
            platform_account_id=uuid4(),
            platform=PublishTargetPlatform.FACEBOOK_REELS,
            page_id="page",
            display_name="Page",
            access_token="secret-token",
        )
        module = __import__("src.publish.connectors.facebook_reels", fromlist=["request"])
        original = module.request.urlopen
        module.request.urlopen = lambda *_args, **_kwargs: _Response(b'{"id":"comment-1","message":"hello","attachment":{"type":"photo"},"is_hidden":false}')
        try:
            result = FacebookReelsConnector().verify_affiliate_comment(account=account, external_comment_id="comment-1")
        finally:
            module.request.urlopen = original
        self.assertEqual(result["status"], "VERIFIED")
        self.assertTrue(result["has_attachment"])
        self.assertNotIn("secret-token", repr(result))

    def test_link_checker_revalidates_safe_redirects_and_accepts_403_as_restricted(self):
        class _Session:
            def __init__(self):
                self.calls = 0
                self.headers = {}

            def head(self, *_args, **_kwargs):
                self.calls += 1
                if self.calls == 1:
                    return SimpleNamespace(status_code=302, headers={"location": "https://store.example/final"})
                return SimpleNamespace(status_code=403, headers={})

            def close(self):
                pass

        with patch("src.affiliate_intelligence.services.affiliate_comment_verification_service._resolve_public_addresses"), patch(
            "src.affiliate_intelligence.services.affiliate_comment_verification_service.requests.Session", return_value=_Session()
        ):
            result = check_affiliate_url("https://short.example/item")
        self.assertEqual(result["status"], "ACCESS_RESTRICTED")
        self.assertEqual(result["redirect_count"], 1)

    def test_link_checker_rejects_private_targets(self):
        with self.assertRaises(AffiliateCommentVerificationError) as raised:
            check_affiliate_url("https://127.0.0.1/item")
        self.assertEqual(raised.exception.code, "affiliate_link_unsafe_redirect")


if __name__ == "__main__":
    unittest.main()
