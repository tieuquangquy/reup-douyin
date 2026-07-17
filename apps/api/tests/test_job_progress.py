from dataclasses import dataclass
import unittest

from src.enums import JobStepStatus
from src.services.job_progress import calculate_job_progress


@dataclass
class FakeStep:
    step_key: str
    step_order: int
    status: JobStepStatus
    progress_percent: int = 0


class JobProgressTests(unittest.TestCase):
    def test_empty_steps_progress(self) -> None:
        progress = calculate_job_progress([])
        self.assertEqual(progress["progress_percent"], 0)
        self.assertEqual(progress["total_steps"], 0)

    def test_progress_counts_completed_and_running_step(self) -> None:
        progress = calculate_job_progress(
            [
                FakeStep("a", 0, JobStepStatus.COMPLETED, 100),
                FakeStep("b", 1, JobStepStatus.RUNNING, 50),
                FakeStep("c", 2, JobStepStatus.PENDING, 0),
                FakeStep("d", 3, JobStepStatus.PENDING, 0),
            ]
        )
        self.assertEqual(progress["progress_percent"], 38)
        self.assertEqual(progress["completed_steps"], 1)
        self.assertEqual(progress["failed_steps"], 0)
        self.assertEqual(progress["current_step_key"], "b")

    def test_progress_reaches_100_when_all_terminal_success(self) -> None:
        progress = calculate_job_progress(
            [
                FakeStep("a", 0, JobStepStatus.COMPLETED, 100),
                FakeStep("b", 1, JobStepStatus.SKIPPED, 100),
            ]
        )
        self.assertEqual(progress["progress_percent"], 100)
        self.assertEqual(progress["completed_steps"], 1)
        self.assertEqual(progress["current_step_key"], None)

    def test_failed_step_is_current_and_counted(self) -> None:
        progress = calculate_job_progress(
            [
                FakeStep("a", 0, JobStepStatus.COMPLETED, 100),
                FakeStep("b", 1, JobStepStatus.FAILED, 20),
            ]
        )
        self.assertEqual(progress["failed_steps"], 1)
        self.assertEqual(progress["current_step_key"], "b")
        self.assertEqual(progress["progress_percent"], 50)


if __name__ == "__main__":
    unittest.main()

