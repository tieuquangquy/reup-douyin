import unittest
from unittest.mock import patch

from src.adapters.douyin_live_fetch import (
    DouyinLiveFetchClient,
    DouyinLiveFetchConfig,
    DouyinRenderedPageProbe,
    extract_profile_payload_from_browser_artifacts,
)
from src.adapters.errors import SourceAdapterError, SourceAdapterErrorCode


PROFILE_URL = "https://www.douyin.com/user/MS4wLjABAAAAfixture-sec-uid"


class DouyinLiveFetchClientTests(unittest.TestCase):
    def test_browser_profile_fetch_extracts_rendered_video_links_as_primary_path(self) -> None:
        def browser_fetch(profile_url: str) -> dict:
            return extract_profile_payload_from_browser_artifacts(
                html="<html><body><a href='/video/1234567890'>video</a></body></html>",
                profile_url=profile_url,
                video_links=["https://www.douyin.com/video/1234567890"],
                page_title="creator",
                page_url=profile_url,
                max_videos=10,
            )

        client = DouyinLiveFetchClient(
            DouyinLiveFetchConfig(user_agent="ua-1", session_cookie="sessionid=abc"),
            http_get=lambda _: self.fail("HTTP fetch should not run when browser profile succeeds"),
            browser_fetch=browser_fetch,
            prefer_browser_profile=True,
        )

        payload = client(PROFILE_URL)

        self.assertEqual(payload["metadata"]["fetch_execution_path"], "browser_profile")
        self.assertEqual(payload["metadata"]["strategy_policy"], "browser_primary")
        self.assertEqual(payload["metadata"]["primary_execution_path"], "browser_profile")
        self.assertEqual(payload["metadata"]["final_execution_path_used"], "browser_profile")
        self.assertFalse(payload["metadata"]["http_fallback_attempted"])
        self.assertEqual(payload["metadata"]["parse_strategy"], "browser_dom_video_links")
        self.assertEqual(payload["videos"][0]["aweme_id"], "1234567890")

    def test_browser_profile_classified_failure_does_not_hide_behind_http_fallback(self) -> None:
        def browser_fetch(profile_url: str) -> dict:
            return extract_profile_payload_from_browser_artifacts(
                html="<html><body>captcha</body></html>",
                profile_url=profile_url,
                page_title="\u9a8c\u8bc1\u7801\u4e2d\u95f4\u9875",
                page_url=profile_url,
                max_videos=10,
            )

        client = DouyinLiveFetchClient(
            DouyinLiveFetchConfig(user_agent="ua-1", session_cookie="sessionid=abc"),
            http_get=lambda _: self.fail("HTTP fetch should not run after a classified browser-profile block"),
            browser_fetch=browser_fetch,
            prefer_browser_profile=True,
        )

        with self.assertRaises(SourceAdapterError) as ctx:
            client(PROFILE_URL)

        self.assertEqual(ctx.exception.raw_payload["metadata"]["fetch_execution_path"], "browser_profile")
        self.assertEqual(ctx.exception.raw_payload["metadata"]["response_classification"]["code"], "blocked_response")

    def test_browser_profile_unavailable_falls_back_to_http_html(self) -> None:
        def browser_fetch(_: str) -> dict:
            raw_payload = {
                "profile": {},
                "videos": [],
                "metadata": {
                    "response_classification": {
                        "result": "failed",
                        "code": "browser_profile_unavailable",
                        "message": "browser profile unavailable",
                    },
                },
            }
            raise SourceAdapterError(SourceAdapterErrorCode.ADAPTER_FETCH_FAILED, "browser profile unavailable", raw_payload=raw_payload)

        html = """
        <html><body>
          <script id="SIGI_STATE">
            {"user":{"sec_uid":"sec-1","nickname":"creator"},"aweme_list":[{"aweme_id":"v1","desc":"ok","statistics":{"play_count":10}}]}
          </script>
        </body></html>
        """
        client = DouyinLiveFetchClient(
            DouyinLiveFetchConfig(user_agent="ua-1", session_cookie="sessionid=abc"),
            http_get=lambda _: html,
            browser_fetch=browser_fetch,
            prefer_browser_profile=True,
            allow_http_fallback=True,
        )

        payload = client(PROFILE_URL)

        self.assertEqual(payload["metadata"]["fetch_execution_path"], "http_html")
        self.assertEqual(payload["metadata"]["strategy_policy"], "browser_primary")
        self.assertEqual(payload["metadata"]["primary_execution_path"], "browser_profile")
        self.assertEqual(payload["metadata"]["final_execution_path_used"], "http_html")
        self.assertTrue(payload["metadata"]["http_fallback_attempted"])
        self.assertEqual(payload["metadata"]["http_fallback_reason"], "browser_profile_unavailable")

    def test_browser_profile_unavailable_does_not_fallback_when_legacy_http_disabled(self) -> None:
        def browser_fetch(profile_url: str) -> dict:
            raise SourceAdapterError(
                SourceAdapterErrorCode.ADAPTER_FETCH_FAILED,
                "Browser profile unavailable",
                raw_payload={
                    "profile": {},
                    "videos": [],
                    "metadata": {
                        "response_classification": {
                            "result": "failed",
                            "code": "browser_profile_unavailable",
                            "message": "Browser profile unavailable",
                        }
                    },
                },
            )

        client = DouyinLiveFetchClient(
            DouyinLiveFetchConfig(user_agent="ua-1", session_cookie="sessionid=abc"),
            http_get=lambda _: self.sample_html(),
            browser_fetch=browser_fetch,
            prefer_browser_profile=True,
            allow_http_fallback=False,
        )

        with self.assertRaises(SourceAdapterError) as ctx:
            client("https://www.douyin.com/user/MS4wLjABAAAAfixture")

        self.assertIn("Browser profile unavailable", ctx.exception.message)
        self.assertEqual(ctx.exception.raw_payload["metadata"]["response_classification"]["code"], "browser_profile_unavailable")

    def test_http_parse_zero_videos_automatically_falls_back_to_browser_profile(self) -> None:
        def browser_fetch(profile_url: str) -> dict:
            return extract_profile_payload_from_browser_artifacts(
                html="<html><body><a href='/video/987654321'>video</a></body></html>",
                profile_url=profile_url,
                video_links=["https://www.douyin.com/video/987654321"],
                page_title="creator",
                page_url=profile_url,
                max_videos=10,
            )

        client = DouyinLiveFetchClient(
            DouyinLiveFetchConfig(user_agent="ua-1", session_cookie="sessionid=abc"),
            http_get=lambda _: "<html><body></body></html>",
            browser_fetch=browser_fetch,
            prefer_browser_profile=False,
        )

        with patch.object(
            client,
            "_probe_rendered_profile_page",
            return_value=DouyinRenderedPageProbe(
                available=True,
                status="no_rendered_videos",
                reason="http_shell_probe_no_videos",
                title="shell",
                page_url=PROFILE_URL,
                video_link_count=0,
            ),
        ):
            payload = client(PROFILE_URL)

        self.assertEqual(payload["metadata"]["fetch_execution_path"], "http_then_browser_fallback")
        self.assertEqual(payload["metadata"]["strategy_policy"], "http_primary_with_browser_fallback")
        self.assertEqual(payload["metadata"]["primary_execution_path"], "http_html")
        self.assertEqual(payload["metadata"]["final_execution_path_used"], "http_then_browser_fallback")
        self.assertEqual(payload["metadata"]["fallback_from_execution_path"], "http_html")
        self.assertTrue(payload["metadata"]["browser_fallback_attempted"])
        self.assertTrue(payload["metadata"]["http_shell_detected"])
        self.assertEqual(payload["metadata"]["http_response_classification"]["code"], "parse_zero_videos")
        self.assertEqual(payload["videos"][0]["aweme_id"], "987654321")

    def test_http_parse_zero_videos_records_browser_fallback_failure(self) -> None:
        def browser_fetch(profile_url: str) -> dict:
            return extract_profile_payload_from_browser_artifacts(
                html="<html><body>captcha</body></html>",
                profile_url=profile_url,
                page_title="\u9a8c\u8bc1\u7801\u4e2d\u95f4\u9875",
                page_url=profile_url,
                max_videos=10,
            )

        client = DouyinLiveFetchClient(
            DouyinLiveFetchConfig(user_agent="ua-1", session_cookie="sessionid=abc"),
            http_get=lambda _: "<html><body></body></html>",
            browser_fetch=browser_fetch,
            prefer_browser_profile=False,
        )

        with patch.object(
            client,
            "_probe_rendered_profile_page",
            return_value=DouyinRenderedPageProbe(
                available=True,
                status="no_rendered_videos",
                reason="http_shell_probe_no_videos",
                title="shell",
                page_url=PROFILE_URL,
                video_link_count=0,
            ),
        ), self.assertRaises(SourceAdapterError) as ctx:
            client(PROFILE_URL)

        metadata = ctx.exception.raw_payload["metadata"]
        self.assertEqual(metadata["fetch_execution_path"], "http_then_browser_fallback")
        self.assertEqual(metadata["fallback_from_execution_path"], "http_html")
        self.assertTrue(metadata["browser_fallback_attempted"])
        self.assertEqual(metadata["http_response_classification"]["code"], "parse_zero_videos")
        self.assertEqual(metadata["response_classification"]["code"], "blocked_response")

    def test_html_shell_is_classified_as_blocked_response_when_browser_probe_hits_challenge(self) -> None:
        client = DouyinLiveFetchClient(
            DouyinLiveFetchConfig(
                user_agent="ua-1",
                session_cookie="sessionid=abc; sid_guard=xyz",
            ),
        )

        with patch.object(
            client,
            "fetch_html",
            return_value="<html><head><meta charset='utf-8'></head><body></body><script>var glb={};</script></html>",
        ), patch.object(
            client,
            "_probe_rendered_profile_page",
            return_value=DouyinRenderedPageProbe(
                available=True,
                status="blocked",
                reason="browser_probe_detected_challenge_page",
                title="challenge",
                page_url=PROFILE_URL,
                video_link_count=0,
            ),
        ):
            with self.assertRaises(SourceAdapterError) as ctx:
                client(PROFILE_URL)

        self.assertEqual(str(ctx.exception.code), "adapter_fetch_failed")
        self.assertEqual(
            ctx.exception.raw_payload["metadata"]["response_classification"]["code"],
            "blocked_response",
        )


if __name__ == "__main__":
    unittest.main()
