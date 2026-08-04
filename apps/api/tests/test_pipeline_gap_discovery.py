from __future__ import annotations

import hashlib
import json
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from src.services.pipeline_gap_discovery import (
    _io_path,
    discover_gap_candidates,
    enumerate_source_videos,
)


class PipelineGapDiscoveryTests(unittest.TestCase):
    @unittest.skipUnless(os.name == "nt", "Windows extended-length path policy")
    def test_windows_io_path_uses_extended_length_prefix(self) -> None:
        path = Path("C:/") / ("x" * 270) / "source.mp4"

        self.assertTrue(str(_io_path(path)).startswith("\\\\?\\"))

    def test_enumeration_accepts_sources_and_rejects_rendered_outputs(self) -> None:
        with TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            raw = workspace / "data" / "raw"
            rendered = workspace / "data" / "render" / "raw"
            raw.mkdir(parents=True)
            rendered.mkdir(parents=True)
            source = raw / "source.mp4"
            ogv_source = raw / "source.ogv"
            output = rendered / "final.mp4"
            source.write_bytes(b"source")
            ogv_source.write_bytes(b"ogv-source")
            output.write_bytes(b"rendered")

            accepted, excluded = enumerate_source_videos(
                [workspace / "data"], workspace_root=workspace
            )

            self.assertEqual(accepted, [source.resolve(), ogv_source.resolve()])
            self.assertEqual(excluded, ["data/render/raw/final.mp4"])

    def test_discovers_real_gap_candidate_and_dedupes_original_bytes(self) -> None:
        with TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            staging = workspace / "download_staging"
            raw = workspace / "profile" / "raw"
            staging.mkdir()
            raw.mkdir(parents=True)
            duplicate_a = staging / "a.mp4"
            duplicate_b = raw / "b.mp4"
            candidate = raw / "portrait.mp4"
            duplicate_a.write_bytes(b"same")
            duplicate_b.write_bytes(b"same")
            candidate.write_bytes(b"candidate")

            def probe(path: Path) -> dict[str, object]:
                portrait = path.name == "portrait.mp4"
                return {
                    "duration_seconds": 20.0,
                    "size_bytes": path.stat().st_size,
                    "width": 720 if portrait else 1280,
                    "height": 1280 if portrait else 720,
                    "r_frame_rate": "30/1",
                    "avg_frame_rate": "30/1",
                    "has_audio": not portrait,
                }

            def visual(path: Path) -> dict[str, object]:
                return {
                    "lighting": "light",
                    "motion": "medium" if path.name == "portrait.mp4" else "high",
                }

            payload = discover_gap_candidates(
                video_paths=[duplicate_a, duplicate_b, candidate],
                workspace_root=workspace,
                target_gaps={
                    "orientation": ["portrait"],
                    "motion": ["low", "medium"],
                    "audio": ["absent"],
                },
                probe_fn=probe,
                visual_fn=visual,
            )

            self.assertEqual(payload["status"], "CANDIDATES_FOUND")
            self.assertEqual(payload["inventory"]["duplicate_file_count"], 1)
            self.assertEqual(payload["candidate_count"], 1)
            row = payload["candidates"][0]
            self.assertEqual(row["source_path"], "profile/raw/portrait.mp4")
            self.assertEqual(
                row["matched_gaps"],
                ["audio:absent", "motion:medium", "orientation:portrait"],
            )
            self.assertEqual(
                row["source_sha256"], hashlib.sha256(b"candidate").hexdigest()
            )
            self.assertFalse(payload["source_policy"]["source_transformations"])
            unsigned = dict(payload)
            claimed = unsigned.pop("discovery_sha256")
            encoded = json.dumps(
                unsigned,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
            self.assertEqual(claimed, hashlib.sha256(encoded).hexdigest())


if __name__ == "__main__":
    unittest.main()
