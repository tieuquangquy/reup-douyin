import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch
from uuid import uuid4

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

from src.enums import DouyinAccountConnectionStatus
from src.models.source_accounts import DouyinAccountConnection
from src.services.douyin_profile_cleanup_service import DouyinProfileCleanupService


def make_account(*, account_id=None, metadata=None, status=DouyinAccountConnectionStatus.ACTIVE):
    account = DouyinAccountConnection(
        workspace_id=uuid4(),
        display_name="Source account",
        status=status,
        is_default=False,
        metadata_json=metadata or {},
    )
    account.id = account_id or uuid4()
    return account


class DouyinProfileCleanupServiceTests(unittest.TestCase):
    def test_dry_run_keeps_canonical_and_plans_orphan_quarantine(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            account_id = uuid4()
            root = os.path.join(temp_dir, "profiles")
            os.makedirs(os.path.join(root, f"account-{account_id}"))
            os.makedirs(os.path.join(root, "old-session-profile"))
            account = make_account(
                account_id=account_id,
                metadata={
                    "browser_profile_id": f"account-{account_id}",
                    "browser_profile_path": os.path.join(root, f"account-{account_id}"),
                    "browser_profile_mode": "persistent_profile",
                },
            )
            db = Mock()
            service = DouyinProfileCleanupService(db)
            service._load_accounts = Mock(return_value=[account])

            with patch("src.services.douyin_profile_cleanup_service.get_settings", return_value=SimpleNamespace(douyin_persistent_browser_profiles_root_dir=root)):
                with patch("src.services.douyin_profile_cleanup_service.douyin_browser_context_registry.active_profile_ids", return_value=set()):
                    result = service.scan(apply=False)

            self.assertEqual(result.profiles_scanned, 2)
            self.assertEqual(result.canonical_count, 1)
            self.assertEqual(result.orphan_count, 1)
            self.assertEqual(result.quarantine_count, 1)
            self.assertTrue(os.path.isdir(os.path.join(root, "old-session-profile")))
            db.commit.assert_not_called()

    def test_apply_quarantines_noncanonical_without_hard_delete(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            account_id = uuid4()
            root = os.path.join(temp_dir, "profiles")
            canonical = f"account-{account_id}"
            orphan = "old-session-profile"
            os.makedirs(os.path.join(root, canonical))
            os.makedirs(os.path.join(root, orphan))
            account = make_account(
                account_id=account_id,
                metadata={
                    "browser_profile_id": canonical,
                    "browser_profile_path": os.path.join(root, canonical),
                    "browser_profile_mode": "persistent_profile",
                },
            )
            service = DouyinProfileCleanupService(Mock())
            service._load_accounts = Mock(return_value=[account])

            with patch("src.services.douyin_profile_cleanup_service.get_settings", return_value=SimpleNamespace(douyin_persistent_browser_profiles_root_dir=root)):
                with patch("src.services.douyin_profile_cleanup_service.douyin_browser_context_registry.active_profile_ids", return_value=set()):
                    result = service.scan(apply=True)

            self.assertTrue(result.applied)
            self.assertTrue(os.path.isdir(os.path.join(root, canonical)))
            self.assertFalse(os.path.exists(os.path.join(root, orphan)))
            self.assertTrue(os.path.isdir(os.path.join(root, "_quarantine")))

    def test_active_noncanonical_profile_is_not_quarantined(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = os.path.join(temp_dir, "profiles")
            active_profile = "old-session-profile"
            os.makedirs(os.path.join(root, active_profile))
            service = DouyinProfileCleanupService(Mock())
            service._load_accounts = Mock(return_value=[])

            with patch("src.services.douyin_profile_cleanup_service.get_settings", return_value=SimpleNamespace(douyin_persistent_browser_profiles_root_dir=root)):
                with patch("src.services.douyin_profile_cleanup_service.douyin_browser_context_registry.active_profile_ids", return_value={active_profile}):
                    result = service.scan(apply=True)

            self.assertEqual(result.skipped_active_count, 1)
            self.assertTrue(os.path.isdir(os.path.join(root, active_profile)))
            self.assertEqual(result.quarantine_count, 0)

    def test_account_named_profile_is_adopted_when_metadata_missing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            account_id = uuid4()
            root = os.path.join(temp_dir, "profiles")
            canonical = f"account-{account_id}"
            os.makedirs(os.path.join(root, canonical))
            account = make_account(account_id=account_id, metadata={})
            db = Mock()
            service = DouyinProfileCleanupService(db)
            service._load_accounts = Mock(return_value=[account])

            with patch("src.services.douyin_profile_cleanup_service.get_settings", return_value=SimpleNamespace(douyin_persistent_browser_profiles_root_dir=root)):
                with patch("src.services.douyin_profile_cleanup_service.douyin_browser_context_registry.active_profile_ids", return_value=set()):
                    result = service.scan(apply=True)

            self.assertEqual(result.metadata_repairs_count, 1)
            self.assertEqual(account.metadata_json["browser_profile_id"], canonical)
            self.assertEqual(account.metadata_json["browser_profile_mode"], "persistent_profile")
            db.commit.assert_called_once()


if __name__ == "__main__":
    unittest.main()
