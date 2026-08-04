"""Rescan must replace the working flag set, not stack history in summaries."""

from __future__ import annotations

import unittest
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

from src.enums import RiskFlagStatus
from src.risk.services.risk_service import flags_for_latest_scan, statuses_superseded_by_rescan


class RiskScanRescanContractTests(unittest.TestCase):
    def test_rescan_supersedes_open_and_acknowledged_not_only_open(self) -> None:
        superseded = statuses_superseded_by_rescan()
        self.assertIn(RiskFlagStatus.OPEN, superseded)
        self.assertIn(RiskFlagStatus.ACKNOWLEDGED, superseded)
        self.assertNotIn(RiskFlagStatus.RESOLVED, superseded)
        self.assertNotIn(RiskFlagStatus.WAIVED, superseded)

    def test_summary_flags_use_latest_scan_run_only(self) -> None:
        older_run = uuid4()
        newer_run = uuid4()
        t0 = datetime(2026, 7, 25, 12, 0, tzinfo=UTC)
        t1 = t0 + timedelta(minutes=5)
        flags = [
            SimpleNamespace(
                id="old-1",
                scan_run_id=older_run,
                detected_at=t0,
                status=RiskFlagStatus.RESOLVED,
                evidence_summary="subtitle_lines_wrapped_for_burn",
            ),
            SimpleNamespace(
                id="old-2",
                scan_run_id=older_run,
                detected_at=t0,
                status=RiskFlagStatus.ACKNOWLEDGED,
                evidence_summary="using_cleaned_video",
            ),
            SimpleNamespace(
                id="new-1",
                scan_run_id=newer_run,
                detected_at=t1,
                status=RiskFlagStatus.OPEN,
                evidence_summary="subtitle_lines_wrapped_for_burn",
            ),
            SimpleNamespace(
                id="new-2",
                scan_run_id=newer_run,
                detected_at=t1,
                status=RiskFlagStatus.OPEN,
                evidence_summary="using_cleaned_video",
            ),
        ]
        current = flags_for_latest_scan(flags)
        self.assertEqual({flag.id for flag in current}, {"new-1", "new-2"})
        self.assertEqual(len(current), 2)

    def test_repeated_identical_findings_do_not_grow_summary_set(self) -> None:
        """Simulate two scans with the same two warnings: summary size stays 2."""
        run_a = uuid4()
        run_b = uuid4()
        t0 = datetime(2026, 7, 25, 12, 0, tzinfo=UTC)
        t1 = t0 + timedelta(minutes=1)
        warnings = ["subtitle_lines_wrapped_for_burn", "using_cleaned_video"]
        history = [
            SimpleNamespace(id=f"a-{i}", scan_run_id=run_a, detected_at=t0, evidence_summary=w)
            for i, w in enumerate(warnings)
        ] + [
            SimpleNamespace(id=f"b-{i}", scan_run_id=run_b, detected_at=t1, evidence_summary=w)
            for i, w in enumerate(warnings)
        ]
        current = flags_for_latest_scan(history)
        self.assertEqual(len(current), len(warnings))
        self.assertEqual({f.evidence_summary for f in current}, set(warnings))


if __name__ == "__main__":
    unittest.main()
