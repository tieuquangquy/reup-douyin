from datetime import UTC, datetime
from types import SimpleNamespace
import unittest

from src.schemas.operations import OperationalMetricsResponse
from src.services.operational_dependency_probe import probe_operational_dependencies


class OperationalDependencyProbeTests(unittest.TestCase):
    def test_missing_idle_worker_and_redis_telemetry_stays_not_observed(self) -> None:
        metrics = OperationalMetricsResponse(generated_at=datetime.now(UTC))
        dependencies, capacity = probe_operational_dependencies(
            metrics,
            settings=SimpleNamespace(local_storage_root=".", min_free_disk_gb=0),
        )
        by_key = {item.key: item for item in dependencies}

        self.assertEqual(by_key["worker"].state, "not_observed")
        self.assertEqual(by_key["redis"].state, "not_observed")
        self.assertEqual(capacity.state, "ready")

    def test_runnable_backlog_without_busy_worker_is_warning(self) -> None:
        metrics = OperationalMetricsResponse.model_validate(
            {
                "generated_at": datetime.now(UTC),
                "queue_backlog": {"queued": 3, "active_worker_count": 0},
            }
        )
        dependencies, _capacity = probe_operational_dependencies(
            metrics,
            settings=SimpleNamespace(local_storage_root=".", min_free_disk_gb=0),
        )

        worker = next(item for item in dependencies if item.key == "worker")
        self.assertEqual(worker.state, "warning")


if __name__ == "__main__":
    unittest.main()
