from __future__ import annotations

import inspect
import unittest

from src.media_pipeline.hardsub_e2e import run_hardsub_phases_1_to_4


class HardsubArtifactBoundaryTests(unittest.TestCase):
    def test_phase2_does_not_overwrite_master_timeline(self) -> None:
        source = inspect.getsource(run_hardsub_phases_1_to_4)
        self.assertIn('phase2_timeline_path = master_root / "phase2_ocr_timeline.json"', source)
        self.assertIn("phase2_timeline_path.write_text", source)
        self.assertNotIn("master.timeline_path.write_text", source)
        self.assertIn('side / "phase2_ocr_timeline.json"', source)


if __name__ == "__main__":
    unittest.main()
