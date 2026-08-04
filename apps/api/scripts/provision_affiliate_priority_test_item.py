from __future__ import annotations

import argparse
from datetime import UTC, datetime
import json
from pathlib import Path
import sys
from uuid import UUID

from sqlalchemy import select, update

API_ROOT = Path(__file__).resolve().parents[1]
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from src.db.session import get_session_factory
from src.enums import PlatformAccountStatus, PublishTargetPlatform
from src.growth_intelligence.services.growth_score_service import (
    GrowthScoreService,
    STALE_MEASUREMENT_SECONDS,
)
from src.models.affiliate import AffiliateProduct, AffiliateProductMatch
from src.models.analytics import PublicationGrowthAssessment, PublicationMetricSnapshot
from src.models.publish import PlatformAccount, PlatformPublication


TEST_SCORE_VERSION = "GROWTH_SCORE_OPERATOR_TEST_V1"
TEST_GROWTH_SCORE = 80.0
TEST_AFFILIATE_FIT_SCORE = 80.0


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Provision or restore one explicit PRIORITY opportunity test fixture."
    )
    parser.add_argument("--publication-id", required=True, type=UUID)
    parser.add_argument("--restore", action="store_true")
    return parser.parse_args()


def _load_context(db, publication_id: UUID):
    publication = db.get(PlatformPublication, publication_id)
    if publication is None:
        raise ValueError(f"Publication not found: {publication_id}")
    account = db.get(PlatformAccount, publication.platform_account_id)
    product_match = db.scalar(
        select(AffiliateProductMatch).where(
            AffiliateProductMatch.platform_publication_id == publication.id,
            AffiliateProductMatch.is_current.is_(True),
            AffiliateProductMatch.decision_status.in_(["APPROVED", "OVERRIDDEN"]),
            AffiliateProductMatch.selected_product_id.is_not(None),
        )
    )
    product = db.get(AffiliateProduct, product_match.selected_product_id) if product_match else None
    snapshots = list(
        db.scalars(
            select(PublicationMetricSnapshot)
            .where(PublicationMetricSnapshot.platform_publication_id == publication.id)
            .order_by(PublicationMetricSnapshot.observed_at.asc(), PublicationMetricSnapshot.id.asc())
        )
    )
    current_assessment = db.scalar(
        select(PublicationGrowthAssessment).where(
            PublicationGrowthAssessment.platform_publication_id == publication.id,
            PublicationGrowthAssessment.is_current.is_(True),
        )
    )
    return publication, account, product_match, product, snapshots, current_assessment


def _validate_test_candidate(publication, account, product_match, product, snapshots, assessment) -> None:
    if publication.platform != PublishTargetPlatform.FACEBOOK_REELS or not publication.external_reel_id:
        raise ValueError("The test candidate must be a confirmed Facebook Reel")
    if account is None or account.status != PlatformAccountStatus.ACTIVE or account.is_on_hold:
        raise ValueError("The Facebook Page must be active and not on hold")
    metadata = account.metadata_json or {}
    scopes = set(metadata.get("facebook_verified_publish_scopes") or [])
    tasks = set(metadata.get("facebook_page_tasks") or [])
    if (
        metadata.get("facebook_publish_capability_verified") is not True
        or "pages_manage_posts" not in scopes
        or "CREATE_CONTENT" not in tasks
    ):
        raise ValueError("The Facebook Page capability has not been OAuth-verified")
    if product_match is None or product is None or not product.is_active or product.availability_status == "OUT_OF_STOCK":
        raise ValueError("A current approved, available affiliate product match is required")
    if not snapshots or assessment is None:
        raise ValueError("Current metric evidence and a Growth Score assessment are required")
    age_seconds = (datetime.now(UTC) - snapshots[-1].observed_at).total_seconds()
    if age_seconds > STALE_MEASUREMENT_SECONDS:
        raise ValueError("The latest metric snapshot is stale; collect metrics before provisioning the fixture")
    if assessment.input_fingerprint_sha256 != GrowthScoreService.input_fingerprint(snapshots):
        raise ValueError("The current Growth Score fingerprint does not match metric evidence")


def provision(db, publication_id: UUID) -> dict:
    publication, account, product_match, product, snapshots, current_assessment = _load_context(db, publication_id)
    _validate_test_candidate(
        publication, account, product_match, product, snapshots, current_assessment
    )
    match_metadata = dict(product_match.metadata_json or {})
    fixture_metadata = dict(match_metadata.get("operator_priority_test_fixture") or {})
    original_fit_score = fixture_metadata.get("original_affiliate_fit_score", product_match.selected_fit_score)
    original_assessment_id = fixture_metadata.get(
        "original_growth_assessment_id", str(current_assessment.id)
    )
    provisioned_at = datetime.now(UTC)
    match_metadata["operator_priority_test_fixture"] = {
        "active": True,
        "provisioned_at": provisioned_at.isoformat(),
        "original_affiliate_fit_score": original_fit_score,
        "original_growth_assessment_id": original_assessment_id,
        "automatic_posting": False,
    }
    product_match.selected_fit_score = TEST_AFFILIATE_FIT_SCORE
    product_match.metadata_json = match_metadata

    fingerprint = GrowthScoreService.input_fingerprint(snapshots)
    test_assessment = db.scalar(
        select(PublicationGrowthAssessment).where(
            PublicationGrowthAssessment.platform_publication_id == publication.id,
            PublicationGrowthAssessment.score_version == TEST_SCORE_VERSION,
            PublicationGrowthAssessment.input_fingerprint_sha256 == fingerprint,
        )
    )
    if test_assessment is None:
        test_assessment = PublicationGrowthAssessment(
            workspace_id=publication.workspace_id,
            platform_publication_id=publication.id,
            score_version=TEST_SCORE_VERSION,
            input_fingerprint_sha256=fingerprint,
        )
        db.add(test_assessment)
    db.execute(
        update(PublicationGrowthAssessment)
        .where(PublicationGrowthAssessment.platform_publication_id == publication.id)
        .values(is_current=False)
    )
    test_assessment.latest_metric_snapshot_id = snapshots[-1].id
    test_assessment.created_by_job_id = None
    test_assessment.status = "READY"
    test_assessment.confidence = "MEDIUM"
    test_assessment.growth_score = TEST_GROWTH_SCORE
    test_assessment.snapshot_count = len(snapshots)
    test_assessment.observation_hours = current_assessment.observation_hours
    test_assessment.measurement_age_seconds = max(
        0, int((provisioned_at - snapshots[-1].observed_at).total_seconds())
    )
    test_assessment.score_breakdown_json = {
        "view_velocity": 28.0,
        "view_acceleration": 20.0,
        "engagement_quality": 16.0,
        "publication_freshness": 8.0,
        "data_quality": 8.0,
    }
    test_assessment.evidence_json = [
        "operator_test_fixture:true",
        f"original_growth_assessment_id:{original_assessment_id}",
        "automatic_posting:false",
    ]
    test_assessment.input_snapshot_ids_json = [str(snapshot.id) for snapshot in snapshots]
    test_assessment.is_current = True
    test_assessment.metadata_json = {
        "operator_test_fixture": True,
        "provisioned_at": provisioned_at.isoformat(),
        "original_growth_assessment_id": original_assessment_id,
        "auto_placement": False,
        "combined_with_affiliate_fit": False,
    }
    db.commit()
    db.refresh(test_assessment)
    return {
        "action": "provisioned",
        "platform_publication_id": str(publication.id),
        "external_reel_id": publication.external_reel_id,
        "page_display_name": account.display_name,
        "product_name": product.name,
        "growth_score": test_assessment.growth_score,
        "affiliate_fit_score": product_match.selected_fit_score,
        "recommendation": "PRIORITY",
        "automatic_posting": False,
        "restore_command": (
            "python scripts/provision_affiliate_priority_test_item.py "
            f"--publication-id {publication.id} --restore"
        ),
    }


def restore(db, publication_id: UUID) -> dict:
    publication, account, product_match, product, _snapshots, current_assessment = _load_context(db, publication_id)
    if product_match is None:
        raise ValueError("Current product match was not found")
    match_metadata = dict(product_match.metadata_json or {})
    fixture_metadata = dict(match_metadata.get("operator_priority_test_fixture") or {})
    if not fixture_metadata:
        raise ValueError("This publication does not have an operator PRIORITY test fixture")
    original_assessment_id = UUID(str(fixture_metadata["original_growth_assessment_id"]))
    original_assessment = db.get(PublicationGrowthAssessment, original_assessment_id)
    if original_assessment is None or original_assessment.platform_publication_id != publication.id:
        raise ValueError("The original Growth Score assessment could not be restored")
    db.execute(
        update(PublicationGrowthAssessment)
        .where(PublicationGrowthAssessment.platform_publication_id == publication.id)
        .values(is_current=False)
    )
    original_assessment.is_current = True
    product_match.selected_fit_score = fixture_metadata.get("original_affiliate_fit_score")
    match_metadata["operator_priority_test_fixture"] = {
        **fixture_metadata,
        "active": False,
        "restored_at": datetime.now(UTC).isoformat(),
    }
    product_match.metadata_json = match_metadata
    db.commit()
    return {
        "action": "restored",
        "platform_publication_id": str(publication.id),
        "external_reel_id": publication.external_reel_id,
        "page_display_name": account.display_name if account else None,
        "product_name": product.name if product else None,
        "growth_assessment_id": str(original_assessment.id),
        "affiliate_fit_score": product_match.selected_fit_score,
    }


def main() -> None:
    args = _args()
    db = get_session_factory()()
    try:
        result = restore(db, args.publication_id) if args.restore else provision(db, args.publication_id)
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
