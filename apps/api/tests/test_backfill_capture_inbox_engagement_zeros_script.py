from __future__ import annotations

import json
import unittest
from unittest.mock import MagicMock, patch
from uuid import uuid4

from scripts.backfill_capture_inbox_engagement_zeros import main


class BackfillCaptureInboxEngagementZerosScriptTests(unittest.TestCase):
    def test_script_runs_profile_backfill(self) -> None:
        db = MagicMock()
        service = MagicMock()
        result = MagicMock()
        result.to_dict.return_value = {"updated_count": 3, "candidate_count": 5}
        service.backfill_profile.return_value = result

        with patch("src.db.session.get_session_factory", return_value=lambda: db), patch(
            "src.services.capture_inbox_engagement_backfill_service.CaptureInboxEngagementBackfillService",
            return_value=service,
        ), patch("builtins.print") as print_mock:
            exit_code = main(
                [
                    "--profile-identifier",
                    "MS4wLjABAAAAfixture",
                    "--limit",
                    "100",
                    "--dry-run",
                ]
            )

        self.assertEqual(exit_code, 0)
        service.backfill_profile.assert_called_once()
        payload = json.loads(print_mock.call_args.args[0])
        self.assertEqual(payload["updated_count"], 3)


if __name__ == "__main__":
    unittest.main()
