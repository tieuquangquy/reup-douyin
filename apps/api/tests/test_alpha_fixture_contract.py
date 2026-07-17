import json
import unittest
from pathlib import Path


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "alpha_demo_fixture.json"


class AlphaFixtureContractTests(unittest.TestCase):
    def test_fixture_has_required_demo_cases(self) -> None:
        fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
        videos = fixture["source_videos"]
        paths = {video["path"] for video in videos}
        self.assertIn("ingested_only", paths)
        self.assertIn("candidate_high_score", paths)
        self.assertIn("rendered_final", paths)
        self.assertIn("warning_path", paths)
        self.assertIn("publish_ready", paths)

    def test_fixture_shapes_match_seed_expectations(self) -> None:
        fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
        for video in fixture["source_videos"]:
            self.assertIn("external_id", video)
            self.assertIn("status", video)
            self.assertIn("metrics", video)
            for metric in ["view_count", "like_count", "comment_count", "share_count"]:
                self.assertIn(metric, video["metrics"])

    def test_job_cases_include_success_and_failure(self) -> None:
        fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
        statuses = {job["status"] for job in fixture["job_cases"]}
        self.assertIn("COMPLETED", statuses)
        self.assertIn("FAILED", statuses)


if __name__ == "__main__":
    unittest.main()
