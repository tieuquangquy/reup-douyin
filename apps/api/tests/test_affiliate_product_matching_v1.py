from __future__ import annotations

from types import SimpleNamespace
import unittest
from uuid import uuid4

from pydantic import ValidationError

from src.affiliate_intelligence.services.affiliate_product_service import (
    AffiliateProductMatchingService,
    build_affiliate_match_queue_kpis,
    product_identity_fingerprint,
)
from src.enums import JobType
from src.schemas.affiliate import (
    AffiliateProductCreateRequest,
    AffiliateProductMatchDecisionRequest,
    AffiliateProductMatchQueueKpis,
)
from src.services.job_templates import get_step_templates


class AffiliateProductMatchingV1Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.topic_id = uuid4()
        self.publication = SimpleNamespace(platform="FACEBOOK_REELS")
        self.classification = SimpleNamespace(
            primary_topic_id=self.topic_id,
            primary_topic_code="FOOD_DRINK",
            secondary_topics_json=[],
            evidence_json=[{"text": "Trà thảo mộc tự nhiên giúp giải khát"}],
        )

    def _product(self, *, topic: bool = True, keywords: list[str] | None = None):
        return SimpleNamespace(
            id=uuid4(),
            name="Trà thảo mộc",
            merchant_name="Herb Tea",
            platform="SHOPEE",
            affiliate_url="https://example.com/affiliate/tea",
            image_url=None,
            price_amount=99000,
            currency_code="VND",
            commission_rate_percent=20,
            availability_status="IN_STOCK",
            keywords_json=keywords or [],
            supported_platforms_json=["FACEBOOK_REELS"],
            topic_mappings=[SimpleNamespace(topic_category_id=self.topic_id)] if topic else [],
        )

    def test_matcher_keeps_affiliate_fit_components_separate(self) -> None:
        suggestions = AffiliateProductMatchingService(None)._match(  # type: ignore[arg-type]
            publication=self.publication,
            classification=self.classification,
            products=[self._product(keywords=["trà thảo mộc"])],
            max_suggestions=5,
        )
        self.assertEqual(len(suggestions), 1)
        suggestion = suggestions[0]
        self.assertEqual(suggestion["affiliate_fit_score"], 81.25)
        self.assertEqual(
            suggestion["score_breakdown"],
            {
                "topic_relevance": 40.0,
                "keyword_entity_match": 6.25,
                "availability": 15.0,
                "commission_quality": 10.0,
                "platform_compatibility": 10.0,
            },
        )
        self.assertNotIn("growth", suggestion["score_breakdown"])

    def test_unrelated_product_is_not_made_eligible_by_commission(self) -> None:
        suggestions = AffiliateProductMatchingService(None)._match(  # type: ignore[arg-type]
            publication=self.publication,
            classification=self.classification,
            products=[self._product(topic=False, keywords=["son môi"])],
            max_suggestions=5,
        )
        self.assertEqual(suggestions, [])

    def test_product_identity_is_stable_for_external_id(self) -> None:
        first = product_identity_fingerprint(
            platform="SHOPEE", external_product_id="SKU-1", affiliate_url="https://a.example/one"
        )
        second = product_identity_fingerprint(
            platform="shopee", external_product_id="SKU-1", affiliate_url="https://a.example/two"
        )
        self.assertEqual(first, second)

    def test_product_requires_http_affiliate_url(self) -> None:
        with self.assertRaises(ValidationError):
            AffiliateProductCreateRequest(name="Tea", affiliate_url="javascript:alert(1)")

    def test_product_image_url_accepts_http_for_local_preview_but_rejects_invalid_scheme(self) -> None:
        with self.assertRaises(ValidationError):
            AffiliateProductCreateRequest(
                name="Tea",
                affiliate_url="https://example.com/affiliate/tea",
                image_url="javascript:alert(1)",
            )
        request = AffiliateProductCreateRequest(
            name="Tea",
            affiliate_url="https://example.com/affiliate/tea",
            image_url="http://localhost:3000/api/public/affiliate-product-images/test.jpg",
        )
        self.assertEqual(request.image_url, "http://localhost:3000/api/public/affiliate-product-images/test.jpg")

    def test_approve_requires_product_and_override_requires_reason(self) -> None:
        with self.assertRaises(ValidationError):
            AffiliateProductMatchDecisionRequest(decision="APPROVED")
        with self.assertRaises(ValidationError):
            AffiliateProductMatchDecisionRequest(decision="OVERRIDDEN", selected_product_id=uuid4())
        request = AffiliateProductMatchDecisionRequest(
            decision="OVERRIDDEN",
            selected_product_id=uuid4(),
            reason="Operator selected a more specific product",
        )
        self.assertEqual(request.decision, "OVERRIDDEN")

    def test_product_matching_job_has_one_persist_boundary(self) -> None:
        self.assertEqual(
            [step.key for step in get_step_templates(JobType.MATCH_AFFILIATE_PRODUCTS)],
            ["validate_classification", "load_catalog", "match_and_persist", "finalize"],
        )

    def test_queue_kpis_expose_overridden_and_partition_eligible(self) -> None:
        """Eligible must equal unmatched + decision statuses; stale stays orthogonal."""
        kpis = build_affiliate_match_queue_kpis(
            eligible_count=6,
            status_counts={"APPROVED": 3, "REJECTED": 2, "OVERRIDDEN": 1},
            stale_count=6,
        )
        self.assertEqual(kpis["eligible_publications"], 6)
        self.assertEqual(kpis["unmatched_count"], 0)
        self.assertEqual(kpis["approved_count"], 3)
        self.assertEqual(kpis["rejected_count"], 2)
        self.assertEqual(kpis["overridden_count"], 1)
        self.assertEqual(kpis["needs_review_count"], 0)
        self.assertEqual(kpis["stale_count"], 6)
        partitioned = (
            kpis["unmatched_count"]
            + kpis["needs_review_count"]
            + kpis["approved_count"]
            + kpis["rejected_count"]
            + kpis["overridden_count"]
        )
        self.assertEqual(partitioned, kpis["eligible_publications"])
        self.assertIn("overridden_count", AffiliateProductMatchQueueKpis.model_fields)


if __name__ == "__main__":
    unittest.main()
