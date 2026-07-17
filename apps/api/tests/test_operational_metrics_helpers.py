import unittest

from src.services.operational_metrics_helpers import (
    DurationSample,
    calculate_failure_rate,
    safe_average,
    summarize_counts,
    summarize_duration_samples,
)


class OperationalMetricsHelperTests(unittest.TestCase):
    def test_safe_average_ignores_negative_values(self) -> None:
        self.assertEqual(safe_average([10, -1, 20]), 15.0)
        self.assertEqual(safe_average([]), 0.0)

    def test_summarize_counts_groups_by_type_and_status(self) -> None:
        summary = summarize_counts(
            [
                ("DOWNLOAD_VIDEO", "COMPLETED", 2),
                ("DOWNLOAD_VIDEO", "FAILED", 1),
                ("RENDER_FINAL", "RUNNING", 3),
            ]
        )
        self.assertEqual(summary["DOWNLOAD_VIDEO"]["COMPLETED"], 2)
        self.assertEqual(summary["DOWNLOAD_VIDEO"]["FAILED"], 1)
        self.assertEqual(summary["RENDER_FINAL"]["RUNNING"], 3)

    def test_duration_summary_is_grouped_and_rounded(self) -> None:
        summary = summarize_duration_samples(
            [
                DurationSample("RENDER_FINAL", 12.345),
                DurationSample("RENDER_FINAL", 17.655),
            ]
        )
        self.assertEqual(summary["RENDER_FINAL"]["sample_count"], 2)
        self.assertEqual(summary["RENDER_FINAL"]["average_seconds"], 15.0)
        self.assertEqual(summary["RENDER_FINAL"]["max_seconds"], 17.66)

    def test_failure_rate_counts_failed_and_retryable(self) -> None:
        self.assertEqual(
            calculate_failure_rate({"COMPLETED": 6, "FAILED": 2, "RETRYABLE": 2}),
            40.0,
        )
        self.assertEqual(calculate_failure_rate({}), 0.0)


if __name__ == "__main__":
    unittest.main()
