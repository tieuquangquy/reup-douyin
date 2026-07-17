from __future__ import annotations

from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from uuid import uuid4

from src.services.capture_inbox_request_replay_service import (
    CaptureInboxRequestReplayError,
    CaptureInboxRequestReplayService,
    apply_cursor_to_request,
    detect_candidate_requests,
    looks_like_captcha_or_block,
    merge_network_evidence_summary,
    request_url_without_query_secrets,
    sanitize_network_aweme,
    summarize_cursor_fields,
)


class CaptureInboxRequestReplayServiceTests(unittest.TestCase):
    def test_detects_candidate_request_from_aweme_list_response(self) -> None:
        records = [
            {
                "request_url": "https://www.douyin.com/aweme/v1/web/aweme/post/?sec_user_id=abc&max_cursor=0",
                "request_method": "GET",
                "request_headers": {"Accept": "application/json"},
                "request_post_data": None,
                "response_document": {
                    "aweme_list": [
                        {
                            "aweme_id": "1",
                            "create_time": 1710000000,
                            "video": {"duration": 42000},
                            "statistics": {"play_count": 100, "digg_count": 5},
                        }
                    ],
                    "max_cursor": 123,
                    "has_more": 1,
                },
            }
        ]

        candidates = detect_candidate_requests(records)

        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].matched_aweme_count, 1)
        self.assertEqual(candidates[0].has_statistics_count, 1)
        self.assertEqual(candidates[0].has_duration_count, 1)
        self.assertEqual(candidates[0].request_cursor_param_name, "max_cursor")

    def test_detects_nested_aweme_objects(self) -> None:
        records = [
            {
                "request_url": "https://www.douyin.com/api",
                "request_method": "GET",
                "request_headers": {},
                "request_post_data": None,
                "response_document": {
                    "data": {
                        "list": [
                            {"wrapper": {"aweme_id": "2", "author": {"nickname": "x"}, "statistics": {"play_count": 3}}},
                        ]
                    }
                },
            }
        ]

        candidates = detect_candidate_requests(records)

        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].sample_aweme_ids, ["2"])

    def test_summarizes_statistics_duration_and_cursor_fields(self) -> None:
        payload = {"data": {"aweme_list": []}, "cursor": 9, "has_more": True}

        summary = summarize_cursor_fields(payload)

        self.assertEqual(summary["cursor"], 9)
        self.assertTrue(summary["has_more"])

    def test_replays_get_candidate_with_modified_cursor(self) -> None:
        url, body = apply_cursor_to_request(
            request_url="https://www.douyin.com/api?max_cursor=0&count=18",
            request_method="GET",
            request_body=None,
            cursor_name="max_cursor",
            cursor_value="12345",
        )

        self.assertIn("max_cursor=12345", url)
        self.assertIsNone(body)

    def test_stops_on_captcha_security_response(self) -> None:
        db = Mock()
        service = CaptureInboxRequestReplayService(db)
        candidate = SimpleNamespace(
            request_url="https://www.douyin.com/api?max_cursor=0",
            request_method="GET",
            request_headers={},
            request_post_data=None,
            request_cursor_param_name="max_cursor",
        )

        with patch("src.services.capture_inbox_request_replay_service.douyin_browser_context_registry") as registry:
            registry.replay_request.return_value = SimpleNamespace(
                available=True,
                response_text="请完成验证 captcha security check",
                response_document=None,
            )
            with self.assertRaises(CaptureInboxRequestReplayError) as captured:
                service._replay_candidate_request(
                    account_id=uuid4(),
                    candidate=candidate,
                    max_pages=1,
                    delay_seconds=0,
                    timeout_seconds=5,
                )

        self.assertEqual(captured.exception.code, "captcha_or_login_wall_detected")

    def test_batch_update_persists_raw_network_aweme_and_reuses_normalizer(self) -> None:
        db = SimpleNamespace(add=lambda item: None, commit=lambda: None)
        service = CaptureInboxRequestReplayService(db)
        item = SimpleNamespace(
            id=uuid4(),
            source_video_external_id="7420000000000000001",
            metadata_json={"raw_dom_snapshot": {"visible_text": "fixture dom"}},
            posted_at=None,
            duration_seconds=None,
        )
        session = SimpleNamespace(items=[item])
        summary = service._batch_update_items_from_network_awemes(
            session,
            {
                "7420000000000000001": {
                    "aweme_id": "7420000000000000001",
                    "create_time": 1710000000,
                    "video": {"duration": 42000},
                    "statistics": {"play_count": 100, "digg_count": 5, "comment_count": 2, "share_count": 1},
                }
            },
        )

        self.assertEqual(summary["updated_count"], 1)
        self.assertEqual(item.duration_seconds, 42.0)
        self.assertEqual(item.metadata_json["view_count"], 100)
        self.assertTrue(item.metadata_json["raw_evidence_summary"]["has_network_aweme"])
        self.assertEqual(item.metadata_json["duration_source"], "network_json")

    def test_unmatched_aweme_id_is_ignored_without_creating_duplicates(self) -> None:
        db = SimpleNamespace(add=lambda item: None, commit=lambda: None)
        service = CaptureInboxRequestReplayService(db)
        item = SimpleNamespace(
            id=uuid4(),
            source_video_external_id="7420000000000000001",
            metadata_json={},
            posted_at=None,
            duration_seconds=None,
        )
        session = SimpleNamespace(items=[item])

        summary = service._batch_update_items_from_network_awemes(
            session,
            {"999": {"aweme_id": "999", "statistics": {"play_count": 5}}},
        )

        self.assertEqual(summary["matched_count"], 0)
        self.assertEqual(summary["updated_count"], 0)
        self.assertNotIn("raw_network_aweme", item.metadata_json)

    def test_request_url_output_drops_secret_query_keys(self) -> None:
        sanitized = request_url_without_query_secrets(
            "https://www.douyin.com/api?max_cursor=1&msToken=secret&token=hidden"
        )

        self.assertIn("max_cursor=1", sanitized)
        self.assertNotIn("msToken", sanitized)
        self.assertNotIn("token=", sanitized)

    def test_sanitize_network_aweme_removes_secret_like_keys(self) -> None:
        sanitized = sanitize_network_aweme(
            {
                "aweme_id": 1,
                "video": {"duration": 1000, "authorization_header": "secret"},
                "statistics": {"play_count": 1},
                "author": {"nickname": "x", "cookie_blob": "secret"},
            }
        )

        self.assertEqual(sanitized["aweme_id"], "1")
        self.assertNotIn("authorization_header", sanitized["video"])
        self.assertNotIn("cookie_blob", sanitized["author"])

    def test_operator_flow_discovers_replays_and_updates_session_items(self) -> None:
        db = Mock()
        service = CaptureInboxRequestReplayService(db)
        item = SimpleNamespace(
            id=uuid4(),
            source_video_external_id="1",
            metadata_json={"raw_dom_snapshot": {"visible_text": "dom"}},
            posted_at=None,
            duration_seconds=None,
        )
        session = SimpleNamespace(
            id=uuid4(),
            workspace_id=uuid4(),
            submitted_profile_url="https://www.douyin.com/user/demo",
            page_url=None,
            items=[item],
        )
        account = SimpleNamespace(id=uuid4())
        preflight = SimpleNamespace(preflight_result="passed", selected_fetch_path="browser_profile")
        fetch_result = SimpleNamespace(
            available=True,
            response_records=[
                {
                    "request_url": "https://www.douyin.com/api?max_cursor=0",
                    "request_method": "GET",
                    "request_headers": {"Accept": "application/json"},
                    "request_post_data": None,
                    "response_document": {
                        "aweme_list": [
                            {
                                "aweme_id": "1",
                                "create_time": 1710000000,
                                "video": {"duration": 42000},
                                "statistics": {"play_count": 100, "digg_count": 5},
                            }
                        ],
                        "max_cursor": 10,
                        "has_more": 0,
                    },
                }
            ],
        )

        with patch.object(service, "_get_capture_session", return_value=session), patch.object(
            service._hydration_service,
            "_resolve_browser_backed_account",
            return_value=(account, preflight),
        ), patch.object(service._hydration_service, "_ensure_browser_context_for_hydration"), patch(
            "src.services.capture_inbox_request_replay_service.douyin_browser_context_registry"
        ) as registry:
            registry.fetch_profile_page.return_value = fetch_result
            registry.replay_request.return_value = SimpleNamespace(
                available=True,
                response_text='{"aweme_list":[{"aweme_id":"1","create_time":1710000000,"video":{"duration":42000},"statistics":{"play_count":100,"digg_count":5}}],"has_more":0}',
                response_document={
                    "aweme_list": [
                        {
                            "aweme_id": "1",
                            "create_time": 1710000000,
                            "video": {"duration": 42000},
                            "statistics": {"play_count": 100, "digg_count": 5},
                        }
                    ],
                    "has_more": 0,
                },
            )

            result = service.discover_and_replay(session.id, max_pages=1, delay_seconds=0)

        self.assertEqual(result.updated_count, 1)
        self.assertEqual(item.metadata_json["view_count"], 100)
        registry.replay_request.assert_called_once()


if __name__ == "__main__":
    unittest.main()
