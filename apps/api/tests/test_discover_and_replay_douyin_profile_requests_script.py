from __future__ import annotations

import json
import unittest
from unittest.mock import MagicMock, patch
from uuid import uuid4

from scripts.discover_and_replay_douyin_profile_requests import main
from src.services.capture_inbox_request_replay_service import CaptureInboxRequestReplayError


class DiscoverAndReplayDouyinProfileRequestsScriptTests(unittest.TestCase):
    def test_script_outputs_success_payload(self) -> None:
        session_id = uuid4()
        db = MagicMock()
        service = MagicMock()
        result = MagicMock()
        result.to_dict.return_value = {"success": True, "updated_count": 3}
        service.discover_and_replay.return_value = result

        with patch("src.db.session.get_session_factory", return_value=lambda: db), patch(
            "src.services.capture_inbox_request_replay_service.CaptureInboxRequestReplayService",
            return_value=service,
        ), patch("builtins.print") as print_mock:
            exit_code = main(["--session-id", str(session_id)])

        self.assertEqual(exit_code, 0)
        self.assertEqual(json.loads(print_mock.call_args.args[0])["updated_count"], 3)

    def test_script_outputs_no_candidate_guidance(self) -> None:
        session_id = uuid4()
        db = MagicMock()
        service = MagicMock()
        service.discover_and_replay.side_effect = CaptureInboxRequestReplayError(
            "no_aweme_list_request_found",
            "No aweme-list request was detected from the profile/feed page.",
        )

        with patch("src.db.session.get_session_factory", return_value=lambda: db), patch(
            "src.services.capture_inbox_request_replay_service.CaptureInboxRequestReplayService",
            return_value=service,
        ), patch("builtins.print") as print_mock:
            exit_code = main(["--session-id", str(session_id)])

        self.assertEqual(exit_code, 1)
        payload = json.loads(print_mock.call_args.args[0])
        self.assertEqual(payload["code"], "no_aweme_list_request_found")
        self.assertIn("scroll naturally", payload["next_step"])


if __name__ == "__main__":
    unittest.main()
