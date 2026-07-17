from __future__ import annotations

import json
import unittest
from unittest.mock import MagicMock, patch
from uuid import uuid4

from scripts.hydrate_capture_session_metadata import main
from src.services.capture_inbox_metadata_hydration_service import CaptureInboxMetadataHydrationError


class HydrateCaptureSessionMetadataScriptTests(unittest.TestCase):
    def test_script_entrypoint_runs_with_explicit_session(self) -> None:
        session_id = uuid4()
        account_id = uuid4()
        db = MagicMock()
        service = MagicMock()
        result = MagicMock()
        result.to_dict.return_value = {"capture_session_id": str(session_id), "hydrated_count": 1}
        service.hydrate_capture_session_metadata.return_value = result

        with patch("src.db.session.get_session_factory", return_value=lambda: db), patch(
            "src.services.capture_inbox_metadata_hydration_service.CaptureInboxMetadataHydrationService",
            return_value=service,
        ), patch("builtins.print") as print_mock:
            exit_code = main(
                [
                    "--session-id",
                    str(session_id),
                    "--account-id",
                    str(account_id),
                    "--limit",
                    "5",
                ]
            )

        self.assertEqual(exit_code, 0)
        service.hydrate_capture_session_metadata.assert_called_once()
        printed = print_mock.call_args.args[0]
        self.assertEqual(json.loads(printed)["hydrated_count"], 1)

    def test_script_points_operator_to_readiness_command_when_browser_profile_is_missing(self) -> None:
        session_id = uuid4()
        db = MagicMock()
        service = MagicMock()
        service.hydrate_capture_session_metadata.side_effect = CaptureInboxMetadataHydrationError(
            "browser_profile_required",
            "No browser-profile-backed Douyin account is available for metadata hydration.",
        )

        with patch("src.db.session.get_session_factory", return_value=lambda: db), patch(
            "src.services.capture_inbox_metadata_hydration_service.CaptureInboxMetadataHydrationService",
            return_value=service,
        ), patch("builtins.print") as print_mock:
            exit_code = main(["--session-id", str(session_id)])

        self.assertEqual(exit_code, 1)
        payload = json.loads(print_mock.call_args.args[0])
        self.assertEqual(payload["code"], "browser_profile_required")
        self.assertEqual(payload["recommended_command"], "python scripts/douyin_account_readiness.py")
        self.assertIn("Create or attach a browser-profile-backed Douyin account", payload["next_step"])

    def test_script_outputs_open_profile_command_when_captcha_is_required(self) -> None:
        session_id = uuid4()
        account_id = uuid4()
        db = MagicMock()
        service = MagicMock()
        service.hydrate_capture_session_metadata.side_effect = CaptureInboxMetadataHydrationError(
            "captcha_required",
            "Douyin requires manual verification in the browser profile.",
            details={
                "capture_session_id": str(session_id),
                "account_id": str(account_id),
                "selected_fetch_path": "browser_profile",
                "hydrated_count": 0,
                "skipped_count": 0,
                "failed_count": 1,
                "captcha_required_count": 1,
                "detail_page_blocked_count": 0,
            },
        )

        with patch("src.db.session.get_session_factory", return_value=lambda: db), patch(
            "src.services.capture_inbox_metadata_hydration_service.CaptureInboxMetadataHydrationService",
            return_value=service,
        ), patch("builtins.print") as print_mock:
            exit_code = main(["--session-id", str(session_id)])

        self.assertEqual(exit_code, 1)
        payload = json.loads(print_mock.call_args.args[0])
        self.assertEqual(payload["code"], "captcha_required")
        self.assertEqual(payload["account_id"], str(account_id))
        self.assertIn("--open-profile --timeout-seconds 300", payload["recommended_command"])
        self.assertEqual(payload["captcha_required_count"], 1)

    def test_script_outputs_revalidate_and_open_profile_commands_when_account_is_not_fetch_ready(self) -> None:
        session_id = uuid4()
        account_id = uuid4()
        db = MagicMock()
        service = MagicMock()
        service.hydrate_capture_session_metadata.side_effect = CaptureInboxMetadataHydrationError(
            "account_not_fetch_ready",
            "Douyin account health is UNKNOWN; revalidate or choose another account before Intake fetch.",
        )
        default_account = MagicMock()
        default_account.id = account_id

        with patch("src.db.session.get_session_factory", return_value=lambda: db), patch(
            "src.services.capture_inbox_metadata_hydration_service.CaptureInboxMetadataHydrationService",
            return_value=service,
        ), patch(
            "src.services.douyin_account_service.DouyinAccountService"
        ) as account_service_cls, patch("builtins.print") as print_mock:
            account_service_cls.return_value.default_account.return_value = default_account
            exit_code = main(["--session-id", str(session_id)])

        self.assertEqual(exit_code, 1)
        payload = json.loads(print_mock.call_args.args[0])
        self.assertEqual(payload["code"], "account_not_fetch_ready")
        self.assertEqual(payload["account_id"], str(account_id))
        self.assertIn("--revalidate --timeout-seconds 120", payload["recommended_command"])
        self.assertIn("--open-profile --timeout-seconds 300", payload["fallback_command"])
        self.assertIn("--operator-confirm-ready", payload["operator_confirm_command"])

    def test_script_outputs_open_profile_command_when_browser_context_is_unavailable(self) -> None:
        session_id = uuid4()
        account_id = uuid4()
        db = MagicMock()
        service = MagicMock()
        service.hydrate_capture_session_metadata.side_effect = CaptureInboxMetadataHydrationError(
            "browser_context_unavailable",
            "Saved browser profile could not provide a live browser context for hydration.",
            details={
                "account_id": str(account_id),
                "selected_fetch_path": "browser_profile",
                "total_items_considered": 49,
                "detail_hydrate_attempted_count": 0,
            },
        )

        with patch("src.db.session.get_session_factory", return_value=lambda: db), patch(
            "src.services.capture_inbox_metadata_hydration_service.CaptureInboxMetadataHydrationService",
            return_value=service,
        ), patch("builtins.print") as print_mock:
            exit_code = main(["--session-id", str(session_id)])

        self.assertEqual(exit_code, 1)
        payload = json.loads(print_mock.call_args.args[0])
        self.assertEqual(payload["code"], "browser_context_unavailable")
        self.assertEqual(payload["account_id"], str(account_id))
        self.assertIn("--open-profile --timeout-seconds 300", payload["recommended_command"])
        self.assertEqual(payload["detail_hydrate_attempted_count"], 0)


if __name__ == "__main__":
    unittest.main()
