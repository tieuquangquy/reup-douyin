from __future__ import annotations

import hashlib
import json
import unittest
import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory

from src.services.local_final_handoff import (
    LocalFinalHandoffError,
    approve_local_publish_metadata,
    approve_local_source_rights_and_music,
    create_local_final_handoff,
    defer_local_manual_upload,
    finalize_local_manual_export,
    record_local_final_approval,
    record_local_manual_upload_evidence,
    update_local_publish_metadata,
)
from src.storage.local import to_windows_long_path


class LocalFinalHandoffTests(unittest.TestCase):
    def _fixture(self, root: Path) -> None:
        video = root / "phase4_adaptive_final.mp4"
        video.write_bytes(b"final-video")
        digest = hashlib.sha256(video.read_bytes()).hexdigest()
        (root / "qa").mkdir()
        values = {
            "phase4_adaptive_render_meta.json": {
                "status": "FINAL_RENDERED",
                "output_qa_status": "PASS",
                "output_video_sha256": digest,
            },
            "qa/phase4_adaptive_final_output_qa.json": {
                "status": "PASS",
                "failed_checks": [],
            },
            "phase4_render_recipe.json": {"recipe_sha256": "r" * 64},
            "phase4_visual_approval.json": {"status": "VISUAL_APPROVED"},
            "phase4_audio_approval.json": {"status": "AUDIO_APPROVED"},
            "phase3_closeout.json": {"status": "PHASE3_CLOSED"},
        }
        for relative, payload in values.items():
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(payload), encoding="utf-8")

    def _ready_manual_export(self, root: Path) -> None:
        self._fixture(root)
        create_local_final_handoff(
            root_dir=root,
            source_video_id="source-id",
            source_video_external_id="external-id",
            operator_id="operator",
            cover_generator=lambda _video, output: output.write_bytes(b"cover"),
        )
        update_local_publish_metadata(
            root_dir=root,
            target_platform="FACEBOOK_REELS",
            title="Cơm trộn trứng",
            caption="Công thức nhanh cho bữa ăn gọn nhẹ.",
            cta_text="Lưu lại để thử nhé.",
            hashtags=["reels"],
        )
        approve_local_publish_metadata(
            root_dir=root,
            operator_id="local_operator",
        )
        approve_local_source_rights_and_music(
            root_dir=root,
            operator_id="local_operator",
        )
        finalize_local_manual_export(
            root_dir=root,
            operator_id="local_operator",
        )

    def test_creates_hash_bound_package_without_publishing(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._fixture(root)

            def cover(_video: Path, output: Path) -> None:
                output.write_bytes(b"jpeg-cover")

            result = create_local_final_handoff(
                root_dir=root,
                source_video_id="source-id",
                source_video_external_id="external-id",
                operator_id="operator",
                cover_generator=cover,
            )
            self.assertEqual(
                result["final_approval"]["status"], "FINAL_APPROVED"
            )
            self.assertEqual(
                result["handoff"]["status"], "READY_FOR_OPERATOR"
            )
            self.assertFalse(result["handoff"]["external_publish_triggered"])
            self.assertTrue((result["package_root"] / "final_video.mp4").is_file())
            self.assertTrue((result["package_root"] / "manifest.json").is_file())

    def test_records_final_approval_without_creating_export_package(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._fixture(root)
            approval = record_local_final_approval(
                root_dir=root,
                source_video_id="source-id",
                source_video_external_id="external-id",
                operator_id="operator",
            )
            self.assertEqual(approval["status"], "FINAL_APPROVED")
            self.assertFalse(approval["external_publish_triggered"])
            self.assertTrue((root / "phase5_final_approval.json").is_file())
            self.assertFalse((root / "export_packages").exists())

            repeated = record_local_final_approval(
                root_dir=root,
                source_video_id="source-id",
                source_video_external_id="external-id",
                operator_id="operator",
            )
            self.assertEqual(repeated["approval_sha256"], approval["approval_sha256"])

    def test_rejects_final_video_hash_mismatch(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._fixture(root)
            meta_path = root / "phase4_adaptive_render_meta.json"
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            meta["output_video_sha256"] = "0" * 64
            meta_path.write_text(json.dumps(meta), encoding="utf-8")
            with self.assertRaises(LocalFinalHandoffError):
                create_local_final_handoff(
                    root_dir=root,
                    source_video_id="source-id",
                    source_video_external_id="external-id",
                    operator_id="operator",
                    cover_generator=lambda _video, output: output.write_bytes(b"cover"),
                )

    def test_updates_validated_metadata_without_publishing(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._fixture(root)

            def cover(_video: Path, output: Path) -> None:
                output.write_bytes(b"jpeg-cover")

            create_local_final_handoff(
                root_dir=root,
                source_video_id="source-id",
                source_video_external_id="external-id",
                operator_id="operator",
                cover_generator=cover,
            )
            result = update_local_publish_metadata(
                root_dir=root,
                target_platform="FACEBOOK_REELS",
                title="Cơm trộn trứng",
                caption="Công thức nhanh cho bữa ăn gọn nhẹ.",
                cta_text="Lưu lại để thử nhé.",
                hashtags=["reels", "comtrontung"],
            )
            draft = result["publish_draft"]
            self.assertEqual(
                draft["status"], "METADATA_DRAFT_COMPLETE_REVIEW_REQUIRED"
            )
            self.assertEqual(draft["validation"]["errors"], [])
            self.assertFalse(draft["external_publish_triggered"])
            self.assertEqual(result["handoff"]["external_publish_triggered"], False)

    def test_approves_hash_bound_metadata_without_publishing(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._fixture(root)

            create_local_final_handoff(
                root_dir=root,
                source_video_id="source-id",
                source_video_external_id="external-id",
                operator_id="operator",
                cover_generator=lambda _video, output: output.write_bytes(b"cover"),
            )
            update_local_publish_metadata(
                root_dir=root,
                target_platform="FACEBOOK_REELS",
                title="Cơm trộn trứng",
                caption="Công thức nhanh cho bữa ăn gọn nhẹ.",
                cta_text="Lưu lại để thử nhé.",
                hashtags=["reels", "comtrontung"],
            )

            result = approve_local_publish_metadata(
                root_dir=root,
                operator_id="local_operator",
            )

            approval = result["metadata_approval"]
            self.assertEqual(approval["status"], "METADATA_APPROVED")
            self.assertEqual(
                result["publish_draft"]["operator_review"]["status"],
                "METADATA_APPROVED",
            )
            self.assertEqual(
                result["handoff"]["status"], "READY_FOR_RIGHTS_REVIEW"
            )
            self.assertEqual(
                result["handoff"]["next_gate"],
                "SOURCE_RIGHTS_AND_MUSIC_REVIEW_REQUIRED",
            )
            self.assertFalse(result["handoff"]["external_publish_triggered"])
            self.assertTrue((root / "phase5_metadata_approval.json").is_file())
            self.assertTrue(
                (result["package_root"] / "metadata_approval.json").is_file()
            )
            self.assertEqual(
                len(list((result["package_root"] / "publish_drafts").iterdir())),
                2,
            )

    def test_metadata_approval_is_idempotent(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._fixture(root)
            create_local_final_handoff(
                root_dir=root,
                source_video_id="source-id",
                source_video_external_id="external-id",
                operator_id="operator",
                cover_generator=lambda _video, output: output.write_bytes(b"cover"),
            )
            update_local_publish_metadata(
                root_dir=root,
                target_platform="FACEBOOK_REELS",
                title="Cơm trộn trứng",
                caption="Công thức nhanh cho bữa ăn gọn nhẹ.",
                cta_text="Lưu lại để thử nhé.",
                hashtags=["reels"],
            )
            first = approve_local_publish_metadata(
                root_dir=root, operator_id="local_operator"
            )
            second = approve_local_publish_metadata(
                root_dir=root, operator_id="local_operator"
            )
            self.assertEqual(
                first["metadata_approval"]["approval_sha256"],
                second["metadata_approval"]["approval_sha256"],
            )
            self.assertEqual(
                first["package_manifest"]["manifest_sha256"],
                second["package_manifest"]["manifest_sha256"],
            )

    def test_atomic_copy_supports_long_windows_history_path(self) -> None:
        from src.services.local_final_handoff import _copy_atomic

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.json"
            source.write_text("history", encoding="utf-8")
            target = (
                root
                / ("nested_" + "x" * 120)
                / ("draft_" + "a" * 64 + ".json")
            )
            _copy_atomic(source, target)
            self.assertEqual(
                to_windows_long_path(target.resolve()).read_text(encoding="utf-8"),
                "history",
            )

    def test_atomic_zip_supports_long_windows_archive_path(self) -> None:
        from src.services.local_final_handoff import _create_zip_atomic

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "package"
            to_windows_long_path(source.resolve()).mkdir(parents=True, exist_ok=True)
            item = source / ("item_" + "a" * 120 + ".json")
            to_windows_long_path(item.resolve()).write_text("payload", encoding="utf-8")
            target = (
                root
                / ("manual_exports_" + "x" * 100)
                / ("archive_" + "b" * 80 + ".zip")
            )
            _create_zip_atomic(source, target)
            with zipfile.ZipFile(to_windows_long_path(target.resolve())) as archive:
                self.assertEqual(len(archive.namelist()), 1)

    def test_metadata_approval_rejects_tampered_draft(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._fixture(root)
            created = create_local_final_handoff(
                root_dir=root,
                source_video_id="source-id",
                source_video_external_id="external-id",
                operator_id="operator",
                cover_generator=lambda _video, output: output.write_bytes(b"cover"),
            )
            update_local_publish_metadata(
                root_dir=root,
                target_platform="FACEBOOK_REELS",
                title="Cơm trộn trứng",
                caption="Công thức nhanh cho bữa ăn gọn nhẹ.",
                cta_text="Lưu lại để thử nhé.",
                hashtags=["reels"],
            )
            draft_path = created["package_root"] / "publish_draft.json"
            draft = json.loads(draft_path.read_text(encoding="utf-8"))
            draft["caption"] = "Nội dung đã bị thay đổi sau khi kiểm tra."
            draft_path.write_text(json.dumps(draft), encoding="utf-8")

            with self.assertRaises(LocalFinalHandoffError):
                approve_local_publish_metadata(
                    root_dir=root,
                    operator_id="local_operator",
                )

    def test_approves_rights_attestation_idempotently_without_publishing(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._fixture(root)
            create_local_final_handoff(
                root_dir=root,
                source_video_id="source-id",
                source_video_external_id="external-id",
                operator_id="operator",
                cover_generator=lambda _video, output: output.write_bytes(b"cover"),
            )
            update_local_publish_metadata(
                root_dir=root,
                target_platform="FACEBOOK_REELS",
                title="Cơm trộn trứng",
                caption="Công thức nhanh cho bữa ăn gọn nhẹ.",
                cta_text="Lưu lại để thử nhé.",
                hashtags=["reels"],
            )
            approve_local_publish_metadata(
                root_dir=root,
                operator_id="local_operator",
            )

            first = approve_local_source_rights_and_music(
                root_dir=root,
                operator_id="local_operator",
            )
            second = approve_local_source_rights_and_music(
                root_dir=root,
                operator_id="local_operator",
            )

            approval = first["rights_music_approval"]
            self.assertEqual(
                approval["status"], "SOURCE_RIGHTS_AND_MUSIC_APPROVED"
            )
            self.assertEqual(
                approval["verification_method"],
                "EXPLICIT_OPERATOR_ATTESTATION",
            )
            self.assertFalse(approval["external_publish_triggered"])
            self.assertFalse(approval["evidence"]["legal_review_performed"])
            self.assertEqual(
                first["handoff"]["status"],
                "READY_FOR_MANUAL_PUBLISH_HANDOFF",
            )
            self.assertEqual(
                first["handoff"]["publish_authorization_status"],
                "NOT_GRANTED",
            )
            self.assertEqual(
                first["handoff"]["next_gate"],
                "EXTERNAL_PUBLISH_AUTHORIZATION_REQUIRED",
            )
            self.assertEqual(
                approval["approval_sha256"],
                second["rights_music_approval"]["approval_sha256"],
            )
            self.assertEqual(
                first["package_manifest"]["manifest_sha256"],
                second["package_manifest"]["manifest_sha256"],
            )

    def test_rights_approval_rejects_tampered_final_video(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._fixture(root)
            created = create_local_final_handoff(
                root_dir=root,
                source_video_id="source-id",
                source_video_external_id="external-id",
                operator_id="operator",
                cover_generator=lambda _video, output: output.write_bytes(b"cover"),
            )
            update_local_publish_metadata(
                root_dir=root,
                target_platform="FACEBOOK_REELS",
                title="Cơm trộn trứng",
                caption="Công thức nhanh cho bữa ăn gọn nhẹ.",
                cta_text="Lưu lại để thử nhé.",
                hashtags=["reels"],
            )
            approve_local_publish_metadata(
                root_dir=root,
                operator_id="local_operator",
            )
            (created["package_root"] / "final_video.mp4").write_bytes(
                b"tampered-video"
            )

            with self.assertRaises(LocalFinalHandoffError):
                approve_local_source_rights_and_music(
                    root_dir=root,
                    operator_id="local_operator",
                )

    def test_builds_idempotent_manual_export_zip_without_publishing(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._fixture(root)
            create_local_final_handoff(
                root_dir=root,
                source_video_id="source-id",
                source_video_external_id="external-id",
                operator_id="operator",
                cover_generator=lambda _video, output: output.write_bytes(b"cover"),
            )
            update_local_publish_metadata(
                root_dir=root,
                target_platform="FACEBOOK_REELS",
                title="Cơm trộn trứng",
                caption="Công thức nhanh cho bữa ăn gọn nhẹ.",
                cta_text="Lưu lại để thử nhé.",
                hashtags=["reels"],
            )
            approve_local_publish_metadata(
                root_dir=root,
                operator_id="local_operator",
            )
            approve_local_source_rights_and_music(
                root_dir=root,
                operator_id="local_operator",
            )

            first = finalize_local_manual_export(
                root_dir=root,
                operator_id="local_operator",
            )
            second = finalize_local_manual_export(
                root_dir=root,
                operator_id="local_operator",
            )

            self.assertEqual(
                first["manual_export_handoff"]["status"],
                "MANUAL_EXPORT_READY",
            )
            self.assertEqual(
                first["handoff"]["publish_authorization_status"],
                "MANUAL_EXPORT_ONLY",
            )
            self.assertFalse(
                first["manual_export_handoff"]["external_publish_authorized"]
            )
            self.assertFalse(
                first["manual_export_handoff"]["external_publish_triggered"]
            )
            self.assertEqual(
                first["manual_export_handoff"]["archive"]["sha256"],
                second["manual_export_handoff"]["archive"]["sha256"],
            )
            with zipfile.ZipFile(first["archive_path"]) as archive:
                names = set(archive.namelist())
            prefix = first["package_root"].name + "/"
            self.assertIn(prefix + "final_video.mp4", names)
            self.assertIn(prefix + "publish_draft.json", names)
            self.assertIn(prefix + "MANUAL_UPLOAD_CHECKLIST.md", names)
            self.assertIn(prefix + "manual_export_decision.json", names)
            self.assertIn(prefix + "manifest.json", names)

    def test_manual_export_requires_rights_approval(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._fixture(root)
            create_local_final_handoff(
                root_dir=root,
                source_video_id="source-id",
                source_video_external_id="external-id",
                operator_id="operator",
                cover_generator=lambda _video, output: output.write_bytes(b"cover"),
            )
            update_local_publish_metadata(
                root_dir=root,
                target_platform="FACEBOOK_REELS",
                title="Cơm trộn trứng",
                caption="Công thức nhanh cho bữa ăn gọn nhẹ.",
                cta_text="Lưu lại để thử nhé.",
                hashtags=["reels"],
            )
            approve_local_publish_metadata(
                root_dir=root,
                operator_id="local_operator",
            )

            with self.assertRaises(LocalFinalHandoffError):
                finalize_local_manual_export(
                    root_dir=root,
                    operator_id="local_operator",
                )

    def test_manual_upload_evidence_mismatch_fails_closed(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._ready_manual_export(root)

            result = record_local_manual_upload_evidence(
                root_dir=root,
                operator_id="local_operator",
                permalink="https://www.facebook.com/reel/2775481049474021",
                published_at="2026-07-27T08:50:00+07:00",
                timezone_name="Asia/Bangkok",
                verification={
                    "method": "IN_APP_BROWSER_READ_ONLY",
                    "permalink_reachable": True,
                    "public_visibility_observed": True,
                    "content_match": False,
                    "mismatch_reasons": ["CAPTION_DOES_NOT_MATCH_APPROVED_DRAFT"],
                },
            )

            self.assertEqual(
                result["status"], "MANUAL_UPLOAD_EVIDENCE_MISMATCH"
            )
            self.assertEqual(result["handoff"]["status"], "MANUAL_EXPORT_READY")
            self.assertEqual(
                result["handoff"]["next_gate"],
                "CORRECT_MANUAL_UPLOAD_EVIDENCE_REQUIRED",
            )
            self.assertIsNone(result["completion"])
            self.assertFalse(
                (root / "phase5_manual_upload_completion.json").exists()
            )

    def test_verified_manual_upload_evidence_closes_idempotently(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._ready_manual_export(root)
            arguments = {
                "root_dir": root,
                "operator_id": "local_operator",
                "permalink": "https://www.facebook.com/reel/1234567890123456",
                "published_at": "2026-07-27T08:50:00+07:00",
                "timezone_name": "Asia/Bangkok",
                "verification": {
                    "method": "IN_APP_BROWSER_READ_ONLY",
                    "permalink_reachable": True,
                    "public_visibility_observed": True,
                    "content_match": True,
                    "mismatch_reasons": [],
                },
            }

            first = record_local_manual_upload_evidence(**arguments)
            second = record_local_manual_upload_evidence(**arguments)

            self.assertEqual(first["status"], "MANUAL_UPLOAD_COMPLETED")
            self.assertEqual(first["handoff"]["next_gate"], "PILOT_CLOSED")
            self.assertFalse(
                first["completion"]["system_external_publish_triggered"]
            )
            self.assertEqual(
                first["completion"]["completion_sha256"],
                second["completion"]["completion_sha256"],
            )

    def test_operator_attestation_can_close_without_external_check(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._ready_manual_export(root)

            result = record_local_manual_upload_evidence(
                root_dir=root,
                operator_id="local_operator",
                permalink="https://www.facebook.com/reel/1062786602978280",
                published_at="2026-08-01T01:35:00+07:00",
                timezone_name="Asia/Bangkok",
                verification={
                    "method": "OPERATOR_ATTESTATION_NO_EXTERNAL_CHECK",
                    "operator_attested": True,
                    "external_verification_skipped": True,
                    "skip_reason": "operator_explicitly_requested_skip",
                    "permalink_reachable": False,
                    "public_visibility_observed": False,
                    "content_match": False,
                },
            )

            self.assertEqual(result["status"], "MANUAL_UPLOAD_COMPLETED")
            self.assertEqual(
                result["evidence"]["status"],
                "MANUAL_UPLOAD_EVIDENCE_OPERATOR_ATTESTED",
            )
            self.assertEqual(
                result["completion"]["evidence_status"],
                "MANUAL_UPLOAD_EVIDENCE_OPERATOR_ATTESTED",
            )
            self.assertEqual(result["handoff"]["next_gate"], "PILOT_CLOSED")
            self.assertFalse(
                result["completion"]["system_external_publish_triggered"]
            )

    def test_defers_manual_upload_idempotently_and_preserves_evidence(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._ready_manual_export(root)
            record_local_manual_upload_evidence(
                root_dir=root,
                operator_id="local_operator",
                permalink="https://www.facebook.com/reel/2775481049474021",
                published_at="2026-07-27T08:50:00+07:00",
                timezone_name="Asia/Bangkok",
                verification={
                    "method": "IN_APP_BROWSER_READ_ONLY",
                    "permalink_reachable": True,
                    "public_visibility_observed": True,
                    "content_match": False,
                },
            )

            first = defer_local_manual_upload(
                root_dir=root,
                operator_id="local_operator",
            )
            second = defer_local_manual_upload(
                root_dir=root,
                operator_id="local_operator",
            )

            self.assertEqual(first["handoff"]["status"], "MANUAL_UPLOAD_DEFERRED")
            self.assertEqual(first["handoff"]["next_gate"], "BATCH_REGRESSION_READY")
            self.assertTrue(first["deferral"]["archive_preserved"])
            self.assertTrue(first["deferral"]["evidence_audit_preserved"])
            self.assertFalse(first["deferral"]["system_external_publish_triggered"])
            self.assertEqual(
                first["deferral"]["deferral_sha256"],
                second["deferral"]["deferral_sha256"],
            )

            completion = record_local_manual_upload_evidence(
                root_dir=root,
                operator_id="local_operator",
                permalink="https://www.facebook.com/reel/1234567890123456",
                published_at="2026-07-28T08:50:00+07:00",
                timezone_name="Asia/Bangkok",
                verification={
                    "method": "IN_APP_BROWSER_READ_ONLY",
                    "permalink_reachable": True,
                    "public_visibility_observed": True,
                    "content_match": True,
                },
            )
            self.assertEqual(completion["status"], "MANUAL_UPLOAD_COMPLETED")


if __name__ == "__main__":
    unittest.main()
