from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import numpy as np

from scripts.build_pipeline_regression_corpus import _resolve_selected_video
from src.services.pipeline_regression_corpus import (
    build_corpus_payload,
    classify_probe,
    load_phase1_metrics,
    sample_visual_features,
)


class PipelineRegressionCorpusTests(unittest.TestCase):
    def test_visual_sampling_falls_back_to_sequential_decode_when_seek_fails(
        self,
    ) -> None:
        class FakeCapture:
            def __init__(self, *, sequential: bool) -> None:
                self.sequential = sequential
                self.frame_index = 0

            def get(self, _property: int) -> float:
                return 10.0

            def isOpened(self) -> bool:
                return True

            def set(self, _property: int, _value: float) -> bool:
                return True

            def read(self) -> tuple[bool, np.ndarray | None]:
                if not self.sequential or self.frame_index >= 10:
                    return False, None
                frame = np.full(
                    (18, 32, 3), self.frame_index, dtype=np.uint8
                )
                self.frame_index += 1
                return True, frame

            def release(self) -> None:
                return None

        captures = [
            FakeCapture(sequential=False),
            FakeCapture(sequential=True),
            FakeCapture(sequential=True),
        ]
        with patch("cv2.VideoCapture", side_effect=captures):
            result = sample_visual_features("short-unseekable.webm")

        self.assertEqual(result["sample_count"], 7)
        self.assertEqual(result["motion"], "low")

    def test_resolves_selected_video_from_additional_input_directory(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            primary = root / "primary"
            additional = root / "additional"
            primary.mkdir()
            additional.mkdir()
            expected = additional / "123.mp4"
            expected.write_bytes(b"video")

            resolved = _resolve_selected_video("123", [primary, additional])

            self.assertEqual(resolved, expected.resolve())

    def test_resolves_selected_original_container_without_transcoding(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            expected = root / "public_source.ogv"
            expected.write_bytes(b"original-ogv")

            resolved = _resolve_selected_video("public_source", [root])

            self.assertEqual(resolved, expected.resolve())

    def test_classifies_cfr_vfr_and_duration(self) -> None:
        cfr = classify_probe(
            {
                "width": 1920,
                "height": 1080,
                "duration_seconds": 34.0,
                "r_frame_rate": "30/1",
                "avg_frame_rate": "30/1",
                "has_audio": True,
            }
        )
        vfr = classify_probe(
            {
                "width": 1080,
                "height": 1920,
                "duration_seconds": 51.0,
                "r_frame_rate": "60/1",
                "avg_frame_rate": "1500/49",
                "has_audio": False,
            }
        )
        self.assertEqual(cfr["timebase"], "CFR")
        self.assertEqual(cfr["duration_band"], "under_35s")
        self.assertEqual(vfr["timebase"], "VFR")
        self.assertEqual(vfr["orientation"], "portrait")
        self.assertEqual(vfr["frame_rate"], "above_30fps")
        self.assertEqual(vfr["audio"], "absent")

    def test_payload_is_stable_and_reports_real_gaps(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            video = root / "video.mp4"
            video.write_bytes(b"video")
            case = {
                "case_id": "local_1",
                "video_path": video,
                "phase1_artifact_root": None,
                "dimensions": {
                    "orientation": "landscape",
                    "resolution": "1080p_or_higher",
                    "timebase": "CFR",
                    "frame_rate": "30fps_or_lower",
                    "duration_band": "under_35s",
                    "lighting": "light",
                    "motion": "medium",
                    "audio": "present",
                    "text_density": "unknown",
                },
            }
            first = build_corpus_payload(cases=[case], workspace_root=root)
            second = build_corpus_payload(cases=[case], workspace_root=root)
            self.assertEqual(first["corpus_sha256"], second["corpus_sha256"])
            self.assertEqual(first["status"], "CORPUS_READY_WITH_GAPS")
            self.assertIn("portrait", first["real_video_gaps"]["orientation"])
            self.assertEqual(first["cases"][0]["video_path"], "video.mp4")

    def test_phase1_metrics_do_not_leak_from_another_video_root(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp) / "phase1_for_video_111"
            root.mkdir()
            (root / "phase1_meta.json").write_text(
                '{"video": "111.mp4"}', encoding="utf-8"
            )
            (root / "master_timeline.json").write_text(
                '[{"text_id": "sub_01"}]', encoding="utf-8"
            )
            wrong = load_phase1_metrics("222", [root])
            correct = load_phase1_metrics("111", [root])
            self.assertEqual(wrong["text_density"], "unknown")
            self.assertEqual(correct["hardsub_count"], 1)

    def test_unknown_text_density_is_not_a_required_coverage_class(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            cases = []
            for index, density in enumerate(("light", "medium", "dense"), start=1):
                video = root / f"video_{index}.mp4"
                video.write_bytes(b"video")
                cases.append(
                    {
                        "case_id": f"local_{index}",
                        "video_path": video,
                        "phase1_artifact_root": None,
                        "dimensions": {
                            "orientation": "landscape",
                            "resolution": "1080p_or_higher",
                            "timebase": "CFR",
                            "frame_rate": "30fps_or_lower",
                            "duration_band": "under_35s",
                            "lighting": "light",
                            "motion": "medium",
                            "audio": "present",
                            "text_density": density,
                        },
                    }
                )

            payload = build_corpus_payload(cases=cases, workspace_root=root)

            self.assertNotIn("text_density", payload["real_video_gaps"])

    def test_loads_metrics_from_runner_local_case_directory(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp) / "regression_run"
            case_root = root / "local_333"
            case_root.mkdir(parents=True)
            (case_root / "phase1_meta.json").write_text(
                '{"video": "333.mp4"}', encoding="utf-8"
            )
            (case_root / "master_timeline.json").write_text(
                '[{"text_id": "sub_01"}, {"text_id": "title_01"}]',
                encoding="utf-8",
            )

            metrics = load_phase1_metrics("333", [root])

            self.assertEqual(metrics["artifact_root"], case_root.resolve())
            self.assertEqual(metrics["track_count"], 2)
            self.assertEqual(metrics["hardsub_count"], 1)


if __name__ == "__main__":
    unittest.main()
