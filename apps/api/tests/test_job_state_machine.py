import unittest

from src.enums import JobStatus, JobStepStatus
from src.services.job_state_machine import (
    InvalidJobStepTransition,
    InvalidJobTransition,
    can_cancel_job,
    can_delete_job,
    can_retry_job,
    can_resume_job,
    validate_job_transition,
    validate_step_transition,
)


class JobStateMachineTests(unittest.TestCase):
    def test_valid_job_transitions(self) -> None:
        validate_job_transition(JobStatus.QUEUED, JobStatus.RUNNING)
        validate_job_transition(JobStatus.RUNNING, JobStatus.WAITING_FOR_REVIEW)
        validate_job_transition(JobStatus.RETRYABLE, JobStatus.QUEUED)
        validate_job_transition(JobStatus.RUNNING, JobStatus.COMPLETED)

    def test_invalid_job_transitions(self) -> None:
        with self.assertRaises(InvalidJobTransition):
            validate_job_transition(JobStatus.COMPLETED, JobStatus.RUNNING)
        with self.assertRaises(InvalidJobTransition):
            validate_job_transition(JobStatus.CANCELLED, JobStatus.QUEUED)

    def test_valid_step_transitions(self) -> None:
        validate_step_transition(JobStepStatus.PENDING, JobStepStatus.RUNNING)
        validate_step_transition(JobStepStatus.RUNNING, JobStepStatus.WAITING_FOR_INPUT)
        validate_step_transition(JobStepStatus.FAILED, JobStepStatus.PENDING)
        validate_step_transition(JobStepStatus.PENDING, JobStepStatus.SKIPPED)

    def test_invalid_step_transitions(self) -> None:
        with self.assertRaises(InvalidJobStepTransition):
            validate_step_transition(JobStepStatus.COMPLETED, JobStepStatus.RUNNING)
        with self.assertRaises(InvalidJobStepTransition):
            validate_step_transition(JobStepStatus.SKIPPED, JobStepStatus.PENDING)

    def test_retry_cancel_resume_helpers(self) -> None:
        self.assertTrue(can_retry_job(JobStatus.FAILED, attempts=1, max_attempts=3))
        self.assertTrue(can_retry_job(JobStatus.RETRYABLE, attempts=1, max_attempts=3))
        self.assertFalse(can_retry_job(JobStatus.FAILED, attempts=3, max_attempts=3))
        self.assertFalse(can_retry_job(JobStatus.FAILED, attempts=1, max_attempts=3, retryable=False))

        self.assertTrue(can_cancel_job(JobStatus.RUNNING))
        self.assertFalse(can_cancel_job(JobStatus.COMPLETED))

        self.assertTrue(can_resume_job(JobStatus.WAITING_FOR_REVIEW))
        self.assertTrue(can_resume_job(JobStatus.RETRYABLE))
        self.assertFalse(can_resume_job(JobStatus.FAILED))

        self.assertTrue(can_delete_job(JobStatus.RUNNING))
        self.assertTrue(can_delete_job(JobStatus.FAILED))
        self.assertTrue(can_delete_job(JobStatus.COMPLETED))


if __name__ == "__main__":
    unittest.main()

