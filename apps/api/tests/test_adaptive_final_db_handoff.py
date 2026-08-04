from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from uuid import uuid4

from src.enums import ReupQueueStatus
from src.render_pipeline.types import VideoProbe
from src.services.adaptive_final_db_handoff import (
    AdaptiveFinalDbHandoffService,
    AdaptiveFinalDbHandoffError,
    load_adaptive_final_authority,
    load_locked_recipe_authority,
)
from src.storage.local import LocalStorageBackend


def _with_self_hash(payload: dict, field: str) -> dict:
    result = dict(payload)
    encoded = json.dumps(
        result, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    result[field] = hashlib.sha256(encoded).hexdigest()
    return result


class _ScalarRows:
    def __init__(self, values: list[object]) -> None:
        self.values = values

    def __iter__(self):
        return iter(self.values)


class _RetryDb:
    def __init__(self, *, source, queue, asset, render, package_item) -> None:
        self.source = source
        self.queue = queue
        self.asset = asset
        self.render = render
        self.package_item = package_item
        self.scalar_calls = 0
        self.scalars_calls = 0
        self.commits = 0
        self.added: list[object] = []

    def scalar(self, _statement):
        self.scalar_calls += 1
        return self.source if self.scalar_calls == 1 else self.package_item

    def scalars(self, _statement):
        self.scalars_calls += 1
        if self.scalars_calls == 1:
            values = [self.asset]
        elif self.scalars_calls == 2:
            values = [self.render]
        else:
            values = [self.package_item]
        return _ScalarRows(values)

    def get(self, _model, _identity):
        return self.queue

    def add(self, value) -> None:
        self.added.append(value)

    def flush(self) -> None:
        for value in self.added:
            if getattr(value, "id", None) is None:
                value.id = uuid4()

    def commit(self) -> None:
        self.commits += 1


class AdaptiveFinalDbHandoffAuthorityTests(unittest.TestCase):
    def test_recipe_evidence_refresh_reuses_same_release(self) -> None:
        recipe = SimpleNamespace(recipe_sha256="b" * 64, release_label="V24")
        self.assertTrue(
            AdaptiveFinalDbHandoffService._recipe_ref_matches(
                {
                    "schema_version": "pipeline_recipe_lock_ref_v1",
                    "recipe_sha256": "a" * 64,
                    "release_label": "V24",
                },
                recipe,
            )
        )
        self.assertFalse(
            AdaptiveFinalDbHandoffService._recipe_ref_matches(
                {
                    "schema_version": "pipeline_recipe_lock_ref_v1",
                    "recipe_sha256": "a" * 64,
                    "release_label": "V23",
                },
                recipe,
            )
        )

    def _recipe(self, root: Path, release_label: str = "V22.1") -> Path:
        payload = _with_self_hash(
            {
                "schema_version": "pipeline_recipe_lock_v3",
                "status": "LOCKED_FOR_CONTROLLED_PILOT_WITH_GAPS",
                "release_label": release_label,
                "execution": {"external_publish": False},
                "evidence": {
                    "phase4_preflight_closeout": {"case_count": 6},
                },
                "claims": {
                    "controlled_pilot_ready_through_phase4_preflight": True,
                    "phase4_preflight_case_count": 6,
                    "full_batch_end_to_end_pass": False,
                    "universal_video_support": False,
                },
            },
            "recipe_sha256",
        )
        path = root / f"pipeline_recipe_{release_label.replace('.', '_')}.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    def _fixture(self, root: Path, source_id: str) -> None:
        video = root / "phase4_adaptive_final.mp4"
        video.write_bytes(b"adaptive-final")
        video_sha = hashlib.sha256(video.read_bytes()).hexdigest()
        package = root / "export_packages" / "package"
        package.mkdir(parents=True)
        package_video = package / "final_video.mp4"
        package_video.write_bytes(video.read_bytes())
        package_ref = {
            "path": "final_video.mp4",
            "sha256": video_sha,
            "size_bytes": package_video.stat().st_size,
        }
        manifest = _with_self_hash(
            {"items": {"video": package_ref}}, "manifest_sha256"
        )
        (package / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        handoff = {
            "package": {
                "path": "export_packages/package",
                "manifest_sha256": manifest["manifest_sha256"],
            }
        }
        (root / "phase5_export_handoff.json").write_text(
            json.dumps(handoff), encoding="utf-8"
        )
        final = _with_self_hash(
            {
                "status": "FINAL_APPROVED",
                "source_video": {"id": source_id, "external_id": "external"},
                "refs": {"final_video": {"sha256": video_sha}},
            },
            "approval_sha256",
        )
        (root / "phase5_final_approval.json").write_text(
            json.dumps(final), encoding="utf-8"
        )
        for name, status in (
            ("phase5_metadata_approval.json", "METADATA_APPROVED"),
            (
                "phase5_rights_music_approval.json",
                "SOURCE_RIGHTS_AND_MUSIC_APPROVED",
            ),
        ):
            approval = _with_self_hash({"status": status}, "approval_sha256")
            (root / name).write_text(json.dumps(approval), encoding="utf-8")
        (root / "phase4_adaptive_render_meta.json").write_text(
            json.dumps(
                {
                    "status": "FINAL_RENDERED",
                    "output_qa_status": "PASS",
                    "output_video_sha256": video_sha,
                }
            ),
            encoding="utf-8",
        )
        (root / "qa").mkdir()
        (root / "qa" / "phase4_adaptive_final_output_qa.json").write_text(
            json.dumps({"status": "PASS", "failed_checks": []}), encoding="utf-8"
        )

    def test_loads_hash_verified_authority(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_id = str(uuid4())
            self._fixture(root, source_id)
            authority = load_adaptive_final_authority(
                root, expected_source_video_id=source_id
            )
            self.assertEqual(authority.source_video_id, source_id)
            self.assertEqual(len(authority.final_video_sha256), 64)

    def test_loads_v22_1_locked_recipe_authority(self) -> None:
        with TemporaryDirectory() as tmp:
            recipe_path = self._recipe(Path(tmp))
            authority = load_locked_recipe_authority(
                recipe_path, expected_release_label="V22.1"
            )
            recipe_ref = authority.reference()
            self.assertEqual(authority.release_label, "V22.1")
            self.assertEqual(len(authority.recipe_sha256), 64)
            self.assertEqual(len(authority.file_sha256), 64)
            self.assertEqual(recipe_ref["validation_boundary"], "PHASE4_PREFLIGHT")
            self.assertNotIn(str(Path(tmp).resolve()), json.dumps(recipe_ref))

    def test_rejects_tampered_locked_recipe(self) -> None:
        with TemporaryDirectory() as tmp:
            recipe_path = self._recipe(Path(tmp))
            payload = json.loads(recipe_path.read_text(encoding="utf-8"))
            payload["claims"]["phase4_preflight_case_count"] = 7
            recipe_path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(
                AdaptiveFinalDbHandoffError, "self-hash is invalid"
            ):
                load_locked_recipe_authority(
                    recipe_path, expected_release_label="V22.1"
                )

    def test_rejects_wrong_expected_recipe_release(self) -> None:
        with TemporaryDirectory() as tmp:
            recipe_path = self._recipe(Path(tmp))
            with self.assertRaisesRegex(
                AdaptiveFinalDbHandoffError, "expected release"
            ):
                load_locked_recipe_authority(
                    recipe_path, expected_release_label="V22.2"
                )

    def test_rejects_video_changed_after_final_approval(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_id = str(uuid4())
            self._fixture(root, source_id)
            (root / "phase4_adaptive_final.mp4").write_bytes(b"tampered")
            with self.assertRaises(AdaptiveFinalDbHandoffError):
                load_adaptive_final_authority(
                    root, expected_source_video_id=source_id
                )

    def test_rejects_tampered_operator_approval(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_id = str(uuid4())
            self._fixture(root, source_id)
            approval_path = root / "phase5_metadata_approval.json"
            approval = json.loads(approval_path.read_text(encoding="utf-8"))
            approval["status"] = "METADATA_REJECTED"
            approval_path.write_text(json.dumps(approval), encoding="utf-8")
            with self.assertRaises(AdaptiveFinalDbHandoffError):
                load_adaptive_final_authority(
                    root, expected_source_video_id=source_id
                )

    def test_rejects_export_package_path_escape(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_id = str(uuid4())
            self._fixture(root, source_id)
            handoff_path = root / "phase5_export_handoff.json"
            handoff = json.loads(handoff_path.read_text(encoding="utf-8"))
            handoff["package"]["path"] = "../outside"
            handoff_path.write_text(json.dumps(handoff), encoding="utf-8")
            with self.assertRaises(AdaptiveFinalDbHandoffError):
                load_adaptive_final_authority(
                    root, expected_source_video_id=source_id
                )

    def test_retry_reuses_rows_and_does_not_regress_downstream_queue_state(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp) / "authority"
            root.mkdir()
            source_id = uuid4()
            queue_id = uuid4()
            workspace_id = uuid4()
            self._fixture(root, str(source_id))
            (root / "phase4_render_input.json").write_text(
                json.dumps({"render_tracks": []}), encoding="utf-8"
            )
            render_meta_path = root / "phase4_adaptive_render_meta.json"
            render_meta = json.loads(render_meta_path.read_text(encoding="utf-8"))
            render_meta["audio_mix"] = {
                "strategy": "drop_verified_silent_or_absent_source_audio"
            }
            render_meta_path.write_text(json.dumps(render_meta), encoding="utf-8")
            recipe_path = self._recipe(Path(tmp))
            recipe_ref = load_locked_recipe_authority(
                recipe_path, expected_release_label="V22.1"
            ).reference()
            video_bytes = (root / "phase4_adaptive_final.mp4").read_bytes()
            video_sha = hashlib.sha256(video_bytes).hexdigest()

            storage = LocalStorageBackend(Path(tmp) / "storage")
            stored = storage.write_bytes("renders/final.mp4", video_bytes)
            asset = SimpleNamespace(
                id=uuid4(),
                storage_key=stored.storage_key,
                checksum_sha256=video_sha,
                is_current=True,
                metadata_json={"preserved_asset": True},
            )
            render = SimpleNamespace(
                id=uuid4(),
                media_asset_id=asset.id,
                status=None,
                render_settings_json={"preserved_setting": True},
                metadata_json={
                    "adaptive_final_import": {
                        "final_video_sha256": video_sha,
                        "recipe_lock": recipe_ref,
                    },
                    "preserved": True,
                },
            )
            package = SimpleNamespace(
                id=uuid4(),
                manifest_json={
                    "adaptive_final_import": {"recipe_lock": recipe_ref}
                },
                diagnostics_json={},
            )
            package_item = SimpleNamespace(
                export_package=package,
                manifest_json={},
                diagnostics_json={},
            )
            source = SimpleNamespace(
                id=source_id,
                workspace_id=workspace_id,
                source_video_external_id="external",
                source_platform="DOUYIN",
                status=None,
                source_profile=SimpleNamespace(
                    source_profile_external_id="profile",
                    handle="handle",
                    display_name="Profile",
                ),
            )
            queue = SimpleNamespace(
                id=queue_id,
                source_video_id=source_id,
                workspace_id=workspace_id,
                render_output_id=render.id,
                status=ReupQueueStatus.PUBLISH_HANDOFF_CREATED,
                media_prep_status=None,
                media_ready_at=None,
                blocked_at=None,
                blocked_reason=None,
                failed_at=None,
                last_error_code=None,
                last_error_message=None,
                last_action_at=None,
                last_action_note=None,
                metadata_json={"export_package_id": str(package.id)},
            )
            db = _RetryDb(
                source=source,
                queue=queue,
                asset=asset,
                render=render,
                package_item=package_item,
            )
            service = AdaptiveFinalDbHandoffService(db, storage=storage)
            service.probe_service = SimpleNamespace(
                probe=lambda _key: VideoProbe(
                    width=1920,
                    height=1080,
                    fps=30.0,
                    duration_seconds=1.0,
                    video_codec="h264",
                    audio_codec="aac",
                    raw={},
                )
            )

            result = service.import_final(
                root_dir=root,
                source_video_id=source_id,
                queue_item_id=queue_id,
                recipe_lock_path=recipe_path,
                expected_recipe_release="V22.1",
            )

            self.assertTrue(result["asset_reused"])
            self.assertTrue(result["render_reused"])
            self.assertTrue(result["export_package_reused"])
            self.assertEqual(queue.status, ReupQueueStatus.PUBLISH_HANDOFF_CREATED)
            self.assertEqual(queue.metadata_json["export_package_id"], str(package.id))
            self.assertTrue(render.metadata_json["preserved"])
            self.assertTrue(render.render_settings_json["preserved_setting"])
            self.assertEqual(
                render.metadata_json["adaptive_final_import"]["recipe_lock"],
                recipe_ref,
            )
            self.assertEqual(
                queue.metadata_json["adaptive_final_import"]["recipe_lock"],
                recipe_ref,
            )
            self.assertTrue(asset.metadata_json["preserved_asset"])
            self.assertEqual(
                asset.metadata_json["adaptive_final_recipe_refs"][
                    recipe_ref["recipe_sha256"]
                ],
                recipe_ref,
            )
            self.assertEqual(
                package.manifest_json["adaptive_final_import"]["final_video_sha256"],
                video_sha,
            )
            self.assertEqual(
                package.manifest_json["adaptive_final_import"]["recipe_lock"],
                recipe_ref,
            )
            self.assertEqual(
                package_item.manifest_json["adaptive_final_import"]["recipe_lock"],
                recipe_ref,
            )
            self.assertEqual(result["recipe_lock"], recipe_ref)
            self.assertFalse(package.diagnostics_json["external_publish_triggered"])
            self.assertFalse(result["external_publish_triggered"])
            self.assertEqual(db.commits, 2)

    def test_same_video_under_different_recipe_creates_new_render(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp) / "authority"
            root.mkdir()
            source_id = uuid4()
            queue_id = uuid4()
            workspace_id = uuid4()
            self._fixture(root, str(source_id))
            (root / "phase4_render_input.json").write_text(
                json.dumps({"render_tracks": []}), encoding="utf-8"
            )
            render_meta_path = root / "phase4_adaptive_render_meta.json"
            render_meta = json.loads(render_meta_path.read_text(encoding="utf-8"))
            render_meta["audio_mix"] = {
                "strategy": "drop_verified_silent_or_absent_source_audio"
            }
            render_meta_path.write_text(json.dumps(render_meta), encoding="utf-8")
            old_recipe_path = self._recipe(Path(tmp), "V22.0")
            recipe_path = self._recipe(Path(tmp), "V22.1")
            old_recipe_ref = load_locked_recipe_authority(
                old_recipe_path, expected_release_label="V22.0"
            ).reference()
            recipe_ref = load_locked_recipe_authority(
                recipe_path, expected_release_label="V22.1"
            ).reference()
            video_bytes = (root / "phase4_adaptive_final.mp4").read_bytes()
            video_sha = hashlib.sha256(video_bytes).hexdigest()

            storage = LocalStorageBackend(Path(tmp) / "storage")
            stored = storage.write_bytes("renders/final.mp4", video_bytes)
            asset = SimpleNamespace(
                id=uuid4(),
                storage_key=stored.storage_key,
                checksum_sha256=video_sha,
                is_current=True,
                metadata_json={},
            )
            old_render = SimpleNamespace(
                id=uuid4(),
                version=1,
                media_asset_id=asset.id,
                status=None,
                render_settings_json={"recipe_lock": old_recipe_ref},
                metadata_json={
                    "adaptive_final_import": {
                        "final_video_sha256": video_sha,
                        "recipe_lock": old_recipe_ref,
                    }
                },
            )
            old_package = SimpleNamespace(
                id=uuid4(),
                manifest_json={
                    "adaptive_final_import": {"recipe_lock": old_recipe_ref}
                },
                diagnostics_json={},
            )
            old_package_item = SimpleNamespace(
                export_package=old_package,
                manifest_json={},
                diagnostics_json={},
            )
            source = SimpleNamespace(
                id=source_id,
                workspace_id=workspace_id,
                source_video_external_id="external",
                source_platform="DOUYIN",
                status=None,
                source_profile=SimpleNamespace(
                    source_profile_external_id="profile",
                    handle="handle",
                    display_name="Profile",
                ),
            )
            queue = SimpleNamespace(
                id=queue_id,
                source_video_id=source_id,
                workspace_id=workspace_id,
                render_output_id=old_render.id,
                status=ReupQueueStatus.READY_TO_EXPORT,
                media_prep_status=None,
                media_ready_at=None,
                blocked_at=None,
                blocked_reason=None,
                failed_at=None,
                last_error_code=None,
                last_error_message=None,
                last_action_at=None,
                last_action_note=None,
                metadata_json={"export_package_id": str(old_package.id)},
            )
            db = _RetryDb(
                source=source,
                queue=queue,
                asset=asset,
                render=old_render,
                package_item=old_package_item,
            )
            service = AdaptiveFinalDbHandoffService(db, storage=storage)
            service.probe_service = SimpleNamespace(
                probe=lambda _key: VideoProbe(
                    width=1920,
                    height=1080,
                    fps=30.0,
                    duration_seconds=1.0,
                    video_codec="h264",
                    audio_codec="aac",
                    raw={},
                )
            )

            result = service.import_final(
                root_dir=root,
                source_video_id=source_id,
                queue_item_id=queue_id,
                create_export_package=False,
                recipe_lock_path=recipe_path,
                expected_recipe_release="V22.1",
            )

            self.assertTrue(result["asset_reused"])
            self.assertFalse(result["render_reused"])
            self.assertFalse(result["export_package_reused"])
            self.assertIsNone(result["export_package_id"])
            self.assertNotEqual(result["render_output_id"], str(old_render.id))
            self.assertEqual(queue.render_output_id, db.added[0].id)
            self.assertNotIn("export_package_id", queue.metadata_json)
            self.assertEqual(
                db.added[0].metadata_json["adaptive_final_import"]["recipe_lock"],
                recipe_ref,
            )
            self.assertEqual(db.added[0].version, 2)
            self.assertFalse(db.added[0].subtitle_burned)
            self.assertEqual(
                db.added[0].audio_strategy,
                "drop_verified_silent_or_absent_source_audio",
            )
            self.assertEqual(db.commits, 1)


if __name__ == "__main__":
    unittest.main()
