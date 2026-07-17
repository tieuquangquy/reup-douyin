import unittest
from types import SimpleNamespace

from src.enums import OperatorRiskDecisionType, RiskFlagStatus, RiskFlagType, RiskSeverity
from src.risk.scanners.rule_based import scan_publish_draft, scan_render_output, scan_source_video
from src.risk.services.policy import evaluate_gate


class RiskPolicyTests(unittest.TestCase):
    def test_source_video_scanner_uses_existing_metadata_signals(self) -> None:
        source_video = SimpleNamespace(
            metadata_json={"has_heavy_watermark": True, "text_density": "high", "processing_complexity": "high"}
        )
        findings = scan_source_video(source_video)
        types = {finding.risk_type for finding in findings}
        self.assertIn(RiskFlagType.WATERMARK_RISK, types)
        self.assertIn(RiskFlagType.OCR_DENSITY_RISK, types)

    def test_render_scanner_maps_warnings(self) -> None:
        render = SimpleNamespace(
            warning_summary_json={"warnings": ["subtitle timing mismatch"]},
            metadata_json={},
            subtitle_burned=True,
        )
        findings = scan_render_output(render)
        self.assertEqual(findings[0].risk_type, RiskFlagType.MANUAL_REVIEW_REQUIRED)
        self.assertEqual(findings[0].severity, RiskSeverity.HIGH)

    def test_publish_draft_scanner_flags_missing_metadata(self) -> None:
        draft = SimpleNamespace(caption="", hashtags_json=[])
        findings = scan_publish_draft(draft)
        self.assertGreaterEqual(len(findings), 2)

    def test_gate_blocks_critical_until_accept_with_warning(self) -> None:
        flags = [SimpleNamespace(status=RiskFlagStatus.OPEN, severity=RiskSeverity.CRITICAL, title="Critical")]
        gate = evaluate_gate(flags)
        self.assertFalse(gate.can_continue)
        accepted_gate = evaluate_gate(flags, SimpleNamespace(decision_type=OperatorRiskDecisionType.ACCEPT_WITH_WARNING))
        self.assertTrue(accepted_gate.can_continue)


if __name__ == "__main__":
    unittest.main()
