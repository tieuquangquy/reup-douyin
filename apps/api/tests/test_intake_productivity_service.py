from datetime import UTC, datetime
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from uuid import uuid4

from src.schemas.intake import (
    IntakeLatestSuccessShortcutResponse,
    IntakeRecentProfileResponse,
    IntakeSavedPresetCreateRequest,
    IntakeSavedPresetResponse,
    IntakeSavedPresetUpdateRequest,
)
from src.services.intake_productivity_service import IntakeProductivityError, IntakeProductivityService


class IntakeProductivityServiceTests(unittest.TestCase):
    def test_bootstrap_aggregates_saved_recent_and_latest(self) -> None:
        workspace_id = uuid4()
        db = Mock()
        service = IntakeProductivityService(db)

        with patch("src.services.intake_productivity_service.ensure_default_workspace", return_value=SimpleNamespace(id=workspace_id)):
            preset_id = uuid4()
            profile_id = uuid4()
            session_id = uuid4()
            now = datetime(2026, 4, 22, tzinfo=UTC)
            service.list_saved_presets = Mock(
                return_value=SimpleNamespace(
                    presets=[
                        IntakeSavedPresetResponse(
                            id=preset_id,
                            workspace_id=workspace_id,
                            name="Daily shortlist",
                            profile_url="https://www.douyin.com/user/MS4wLjABAAAAfixture",
                            preset_name="viral_discovery",
                            filter_config={},
                            force_live_refresh=False,
                            douyin_account_connection_id=None,
                            notes=None,
                            created_at=now,
                            updated_at=now,
                        )
                    ]
                )
            )
            service.list_recent_profiles = Mock(
                return_value=[
                    IntakeRecentProfileResponse(
                        source_profile_id=profile_id,
                        profile_url="https://www.douyin.com/user/MS4wLjABAAAAfixture",
                        normalized_profile_identifier="MS4wLjABAAAAfixture",
                        display_name="Fixture",
                        last_crawled_at=now,
                    )
                ]
            )
            service.list_latest_success_shortcuts = Mock(
                return_value=[
                    IntakeLatestSuccessShortcutResponse(
                        crawl_session_id=session_id,
                        source_profile_id=profile_id,
                        submitted_profile_url="https://www.douyin.com/user/MS4wLjABAAAAfixture",
                        normalized_profile_identifier="MS4wLjABAAAAfixture",
                        finished_at=now,
                        videos_discovered_count=3,
                    )
                ]
            )

            payload = service.bootstrap(workspace_id=None)

        self.assertEqual(payload.workspace_id, workspace_id)
        self.assertEqual(len(payload.saved_presets), 1)
        self.assertEqual(len(payload.recent_profiles), 1)
        self.assertEqual(len(payload.latest_success_shortcuts), 1)
        service.list_saved_presets.assert_called_once_with(workspace_id=workspace_id)
        service.list_recent_profiles.assert_called_once_with(workspace_id=workspace_id)
        service.list_latest_success_shortcuts.assert_called_once_with(workspace_id=workspace_id)

    def test_create_saved_preset_rejects_duplicate_name(self) -> None:
        workspace_id = uuid4()
        db = Mock()
        db.scalar.return_value = SimpleNamespace(id=uuid4())
        service = IntakeProductivityService(db)

        request = IntakeSavedPresetCreateRequest(
            workspace_id=workspace_id,
            name="Daily shortlist",
            profile_url="https://www.douyin.com/user/MS4wLjABAAAAfixture",
            preset_name="viral_discovery",
            filter_config=None,
            force_live_refresh=False,
            douyin_account_connection_id=None,
            notes=None,
        )

        with self.assertRaisesRegex(IntakeProductivityError, "already exists"):
            service.create_saved_preset(request)

    def test_update_saved_preset_raises_not_found(self) -> None:
        db = Mock()
        db.get.return_value = None
        service = IntakeProductivityService(db)

        with self.assertRaisesRegex(IntakeProductivityError, "not found"):
            service.update_saved_preset(uuid4(), IntakeSavedPresetUpdateRequest(name="renamed"))

    def test_list_latest_success_shortcuts_maps_session_fields(self) -> None:
        workspace_id = uuid4()
        session = SimpleNamespace(
            id=uuid4(),
            source_profile_id=uuid4(),
            submitted_profile_url="https://www.douyin.com/user/MS4wLjABAAAAfixture",
            normalized_profile_identifier="MS4wLjABAAAAfixture",
            finished_at=datetime(2026, 4, 22, tzinfo=UTC),
            videos_discovered_count=12,
        )
        db = Mock()
        db.scalars.return_value = [session]
        service = IntakeProductivityService(db)

        shortcuts = service.list_latest_success_shortcuts(workspace_id=workspace_id, limit=8)

        self.assertEqual(len(shortcuts), 1)
        self.assertEqual(shortcuts[0].crawl_session_id, session.id)
        self.assertEqual(shortcuts[0].submitted_profile_url, session.submitted_profile_url)
        self.assertEqual(shortcuts[0].videos_discovered_count, 12)


if __name__ == "__main__":
    unittest.main()
