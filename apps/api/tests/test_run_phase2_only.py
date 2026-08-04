from __future__ import annotations

import unittest
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from scripts import run_phase2_only


class _ReconfigurableStream:
    def __init__(self) -> None:
        self.calls: list[dict[str, str]] = []

    def reconfigure(self, **kwargs: str) -> None:
        self.calls.append(dict(kwargs))


class RunPhase2OnlyCliTests(unittest.TestCase):
    def test_mock_flag_is_removed_from_positionals(self) -> None:
        positional, provider_mode = run_phase2_only._parse_cli_args(
            ["phase1-out", "--mock", "video.mp4"]
        )

        self.assertEqual(positional, ["phase1-out", "video.mp4"])
        self.assertEqual(provider_mode, "mock")

    def test_local_provider_is_default_and_cloud_is_explicit(self) -> None:
        positional, provider_mode = run_phase2_only._parse_cli_args(
            ["phase1-out"]
        )
        self.assertEqual(positional, ["phase1-out"])
        self.assertEqual(provider_mode, "local")

        positional, provider_mode = run_phase2_only._parse_cli_args(
            ["--provider", "cloud", "phase1-out"]
        )
        self.assertEqual(positional, ["phase1-out"])
        self.assertEqual(provider_mode, "cloud")

    def test_local_endpoint_defaults_to_loopback(self) -> None:
        with patch.dict(run_phase2_only.os.environ, {}, clear=True):
            endpoint = run_phase2_only._resolve_provider_endpoint("local")

        self.assertEqual(endpoint, "http://127.0.0.1:8080/predict")

    def test_stdout_is_reconfigured_for_cjk_on_windows_console(self) -> None:
        stream = _ReconfigurableStream()
        with patch.object(run_phase2_only.sys, "stdout", stream):
            run_phase2_only._configure_stdout_utf8()

        self.assertEqual(
            stream.calls,
            [{"encoding": "utf-8", "errors": "replace"}],
        )

    def test_rejects_approval_file_from_different_phase1_hash(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "phase2_approvals.json"
            path.write_text(
                json.dumps(
                    {
                        "phase1_ref": {"sha256": "old-hash"},
                        "approvals": [],
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaises(RuntimeError):
                run_phase2_only._load_content_map(
                    path,
                    list_key="approvals",
                    expected_phase1_sha256="new-hash",
                )

    def test_carries_unchanged_approval_across_transient_empty_ocr(self) -> None:
        contract = {
            "track_enrichments": [
                {
                    "text_id": "sub_02",
                    "content_id": "ocr_content_002",
                    "ocr_source": "failed",
                }
            ],
            "content_objects": [
                {
                    "content_id": "ocr_content_002",
                    "geometry_refs": ["sub_02"],
                    "ocr_text_candidate": "",
                    "review_status": "OCR_REVIEW_STALE",
                    "review_input_sha256": "new-review-hash",
                }
            ],
        }
        approvals = {
            "ocr_content_002": {
                "content_id": "ocr_content_002",
                "decision": "APPROVE",
                "review_input_sha256": "old-review-hash",
                "ocr_text_approved": "474千卡",
                "reviewer": "operator",
                "reviewed_at": "2026-07-28T01:00:00+00:00",
            }
        }

        carried = run_phase2_only._carry_forward_transient_ocr_failures(
            contract, approvals, remediated_text_ids={"sub_08", "sub_09"}
        )

        self.assertEqual(
            carried["ocr_content_002"]["review_input_sha256"],
            "new-review-hash",
        )
        self.assertEqual(
            carried["ocr_content_002"]["carry_forward"][
                "previous_review_input_sha256"
            ],
            "old-review-hash",
        )

    def test_never_carries_empty_ocr_for_a_remediated_track(self) -> None:
        contract = {
            "track_enrichments": [
                {
                    "text_id": "sub_08",
                    "content_id": "ocr_content_008",
                    "ocr_source": "failed",
                }
            ],
            "content_objects": [
                {
                    "content_id": "ocr_content_008",
                    "geometry_refs": ["sub_08"],
                    "ocr_text_candidate": "",
                    "review_status": "OCR_REVIEW_STALE",
                    "review_input_sha256": "new-review-hash",
                }
            ],
        }
        approvals = {
            "ocr_content_008": {
                "decision": "APPROVE",
                "review_input_sha256": "old-review-hash",
                "ocr_text_approved": "下入西红柿",
            }
        }

        carried = run_phase2_only._carry_forward_transient_ocr_failures(
            contract, approvals, remediated_text_ids={"sub_08"}
        )

        self.assertEqual(carried, {})


if __name__ == "__main__":
    unittest.main()
