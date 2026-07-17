from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parent))

from metadata_phase5a_real_live_audit import _raw_evidence_coverage


class MetadataPhase5ARealLiveAuditTests(unittest.TestCase):
    def test_raw_evidence_coverage_counts_dom_detail_metrics(self) -> None:
        item_id = uuid4()
        items = [
            SimpleNamespace(
                id=item_id,
                raw_evidence_summary={
                    "has_network_aweme": False,
                    "has_detail_aweme": False,
                    "has_dom_snapshot": True,
                    "has_dom_detail_metrics": True,
                },
            )
        ]
        orm_items = {
            item_id: SimpleNamespace(
                metadata_json={
                    "raw_dom_snapshot": {"visible_text": "fixture"},
                    "raw_dom_detail_metrics": {"duration_seconds": 619, "like_count": 197},
                }
            )
        }

        coverage = _raw_evidence_coverage(items, orm_items)

        self.assertEqual(coverage["raw_dom_detail_metrics"]["present"], 1)
        self.assertEqual(coverage["raw_evidence_summary.has_dom_detail_metrics"]["present"], 1)


if __name__ == "__main__":
    unittest.main()
