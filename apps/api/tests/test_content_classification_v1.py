from __future__ import annotations

from types import SimpleNamespace
import unittest
from uuid import uuid4

from pydantic import ValidationError

from src.content_intelligence.services.content_classification_service import (
    LocalKeywordTopicClassifier,
    evidence_fingerprint,
    normalize_for_matching,
)
from src.enums import JobType
from src.schemas.content_intelligence import (
    ContentClassificationDecisionRequest,
    TopicCategoryCreateRequest,
)
from src.services.job_templates import get_step_templates


def _topic(code: str, name: str, keywords: list[str], order: int):
    return SimpleNamespace(
        id=uuid4(),
        code=code,
        name=name,
        keywords_json=keywords,
        sort_order=order,
        is_active=True,
    )


class ContentClassificationV1Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.topics = [
            _topic("SKINCARE", "Skincare", ["dưỡng da", "serum", "防晒"], 10),
            _topic("COOKING_RECIPES", "Cooking & Recipes", ["công thức", "nấu ăn", "食谱"], 20),
            _topic("GENERAL_OTHER", "General / Other", [], 999),
        ]

    def test_local_classifier_uses_multiple_persisted_evidence_sources(self) -> None:
        evidence = [
            {
                "source": "PUBLICATION_CAPTION",
                "source_id": str(uuid4()),
                "text": "Routine dưỡng da với serum buổi tối",
                "language_code": "vi",
                "confidence": None,
                "matched_keywords": [],
            },
            {
                "source": "OCR",
                "source_id": str(uuid4()),
                "text": "防晒 SPF 50",
                "language_code": "zh",
                "confidence": 0.92,
                "matched_keywords": [],
            },
        ]

        result = LocalKeywordTopicClassifier().classify(evidence=evidence, topics=self.topics)

        self.assertEqual(result.primary_topic.code, "SKINCARE")
        self.assertGreaterEqual(result.confidence, 0.7)
        self.assertEqual(len(result.evidence), 2)
        self.assertTrue(all(item["matched_keywords"] for item in result.evidence))

    def test_no_keyword_match_fails_closed_to_general_and_needs_low_confidence(self) -> None:
        evidence = [{"source": "TRANSCRIPT", "source_id": None, "text": "Xin chào mọi người", "matched_keywords": []}]

        result = LocalKeywordTopicClassifier().classify(evidence=evidence, topics=self.topics)

        self.assertEqual(result.primary_topic.code, "GENERAL_OTHER")
        self.assertLess(result.confidence, 0.5)
        self.assertIn("operator review", result.rationale)

    def test_matching_is_accent_insensitive_without_destroying_chinese(self) -> None:
        self.assertEqual(normalize_for_matching("DƯỠNG DA!"), "duong da")
        self.assertEqual(normalize_for_matching("防晒 SPF"), "防晒 spf")

    def test_input_fingerprint_is_stable_and_changes_with_evidence(self) -> None:
        first = [{"source": "TRANSCRIPT", "source_id": "1", "text": "nấu ăn", "language_code": "vi"}]
        same = [{**first[0], "confidence": 0.5, "matched_keywords": ["COOKING:nấu ăn"]}]
        changed = [{**first[0], "text": "dưỡng da"}]

        self.assertEqual(evidence_fingerprint(first), evidence_fingerprint(same))
        self.assertNotEqual(evidence_fingerprint(first), evidence_fingerprint(changed))

    def test_override_requires_topic_and_reason(self) -> None:
        with self.assertRaises(ValidationError):
            ContentClassificationDecisionRequest(decision="OVERRIDDEN")
        request = ContentClassificationDecisionRequest(
            decision="OVERRIDDEN",
            primary_topic_id=uuid4(),
            reason="OCR identifies a recipe, not skincare",
        )
        self.assertEqual(request.decision, "OVERRIDDEN")

    def test_topic_keywords_are_deduplicated(self) -> None:
        request = TopicCategoryCreateRequest(
            code="COFFEE",
            name="Coffee",
            keywords=[" coffee ", "Coffee", "cà phê"],
        )
        self.assertEqual(request.keywords, ["coffee", "cà phê"])

    def test_classification_job_template_has_one_persist_boundary(self) -> None:
        self.assertEqual(
            [step.key for step in get_step_templates(JobType.CLASSIFY_CONTENT)],
            ["validate_publication", "collect_evidence", "classify_and_persist", "finalize"],
        )


if __name__ == "__main__":
    unittest.main()
