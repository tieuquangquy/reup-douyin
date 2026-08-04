from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from src.services.pipeline_rights_review_pack import (
    write_pipeline_rights_review_pack,
)


def _sha_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _self_hashed(payload: dict, field: str) -> dict:
    result = dict(payload)
    encoded = json.dumps(
        result, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    result[field] = hashlib.sha256(encoded).hexdigest()
    return result


class PipelineRightsReviewPackTests(unittest.TestCase):
    def test_builds_read_only_pack_without_writing_approval(self) -> None:
        with TemporaryDirectory() as tmp:
            run = Path(tmp)
            case = run / "local_123"
            package = case / "export_packages" / "package"
            package.mkdir(parents=True)
            source = run / "source.mp4"
            source.write_bytes(b"source")
            final = case / "phase4_adaptive_final.mp4"
            final.write_bytes(b"final")
            package_video = package / "final_video.mp4"
            package_video.write_bytes(final.read_bytes())
            metadata = _self_hashed(
                {
                    "status": "METADATA_APPROVED",
                    "target_platform": "FACEBOOK_REELS",
                },
                "approval_sha256",
            )
            (case / "phase5_metadata_approval.json").write_text(
                json.dumps(metadata), encoding="utf-8"
            )
            package_metadata = package / "metadata_approval.json"
            package_metadata.write_text(json.dumps(metadata), encoding="utf-8")
            final_approval = _self_hashed(
                {
                    "status": "FINAL_APPROVED",
                    "source_video": {"id": "source", "external_id": "123"},
                    "refs": {
                        "final_video": {"sha256": _sha_file(final)},
                    },
                },
                "approval_sha256",
            )
            (case / "phase5_final_approval.json").write_text(
                json.dumps(final_approval), encoding="utf-8"
            )
            (case / "phase4_adaptive_render_meta.json").write_text(
                json.dumps(
                    {
                        "output_video_sha256": _sha_file(final),
                        "audio_mix": {
                            "strategy": "preserve_verified_no_dialogue_source_audio",
                            "background_present": False,
                        },
                    }
                ),
                encoding="utf-8",
            )
            (case / "phase1_meta.json").write_text(
                json.dumps({"video": str(source)}), encoding="utf-8"
            )
            manifest = _self_hashed(
                {
                    "source_video": {"id": "source", "external_id": "123"},
                    "items": {
                        "video": {
                            "path": package_video.name,
                            "sha256": _sha_file(package_video),
                            "size_bytes": package_video.stat().st_size,
                        },
                        "metadata_approval": {
                            "path": package_metadata.name,
                            "sha256": _sha_file(package_metadata),
                            "size_bytes": package_metadata.stat().st_size,
                        },
                    },
                },
                "manifest_sha256",
            )
            (package / "manifest.json").write_text(
                json.dumps(manifest), encoding="utf-8"
            )
            (case / "phase5_export_handoff.json").write_text(
                json.dumps(
                    {
                        "status": "READY_FOR_RIGHTS_REVIEW",
                        "package": {
                            "path": package.relative_to(case).as_posix(),
                            "manifest_sha256": manifest["manifest_sha256"],
                        },
                    }
                ),
                encoding="utf-8",
            )
            state = _self_hashed(
                {
                    "cases": [
                        {
                            "case_id": case.name,
                            "source_video_external_id": "123",
                            "source_video_sha256": _sha_file(source),
                            "status": "WAITING_SOURCE_RIGHTS_AND_MUSIC_REVIEW",
                        }
                    ]
                },
                "run_sha256",
            )
            (run / "batch_regression_state.json").write_text(
                json.dumps(state), encoding="utf-8"
            )

            pack = write_pipeline_rights_review_pack(run)

            self.assertTrue(pack["all_evidence_valid"])
            self.assertEqual(pack["case_count"], 1)
            self.assertEqual(
                pack["cases"][0]["approval_token"],
                "SOURCE_RIGHTS_AND_MUSIC_APPROVED_123_V23",
            )
            self.assertFalse(
                pack["authority_boundary"]["operator_decision_recorded"]
            )
            self.assertFalse((case / "phase5_rights_music_approval.json").exists())


if __name__ == "__main__":
    unittest.main()
